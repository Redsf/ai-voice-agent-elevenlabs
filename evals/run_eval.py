"""Run the eval suite against the voice agent's n8n backend.

The suite targets the n8n webhook directly rather than placing real calls, so
it isolates the part you actually control: retrieval and answer generation.
ElevenLabs' speech-to-text and text-to-speech sit outside this boundary.

Two modes:

1. Live mode — POST each question to the Listen webhook and grade the reply.
       python evals/run_eval.py --webhook https://your-n8n/webhook/test_voice_message_elevenlabs
2. Offline mode — grade replies collected from real call transcripts.
       python evals/run_eval.py --answers answers.jsonl
   answers.jsonl format: one {"id": "...", "answer": "..."} per line.

Requires OPENAI_API_KEY for the judge model.
Outputs scores.json and report.md next to this file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

from judge import judge_answer

EVAL_DIR = Path(__file__).parent


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def ask_webhook(webhook_url: str, question: str) -> str:
    body = json.dumps({"question": question}).encode()
    req = urllib.request.Request(
        webhook_url, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.load(resp)
    if isinstance(payload, dict):
        return payload.get("answer") or payload.get("output") or json.dumps(payload)
    return str(payload)


def collect_answers(cases: list[dict], args: argparse.Namespace) -> dict[str, str]:
    if args.answers:
        return {row["id"]: row["answer"] for row in load_jsonl(Path(args.answers))}

    answers = {}
    for case in cases:
        print(f"  asking {case['id']} ...", file=sys.stderr)
        try:
            answers[case["id"]] = ask_webhook(args.webhook, case["question"])
        except Exception as exc:  # noqa: BLE001 - record the failure as the answer
            answers[case["id"]] = f"(request failed: {exc})"
    return answers


def summarize(results: list[dict]) -> dict:
    total = len(results)
    if not total:
        return {"total_cases": 0}

    escalation_cases = [r for r in results if r["verdict"]["escalated"] is not None]
    words = [r["verdict"]["words"] for r in results]

    return {
        "total_cases": total,
        "correctness": round(sum(1 for r in results if r["verdict"]["correct"]) / total, 3),
        "groundedness": round(sum(1 for r in results if r["verdict"]["grounded"]) / total, 3),
        "brevity_pass_rate": round(sum(1 for r in results if r["verdict"]["brief"]) / total, 3),
        "median_words": sorted(words)[len(words) // 2],
        "escalation_rate": (
            round(sum(1 for r in escalation_cases if r["verdict"]["escalated"]) / len(escalation_cases), 3)
            if escalation_cases
            else None
        ),
    }


def write_report(results: list[dict], summary: dict) -> None:
    lines = [
        "# Voice Agent Eval Report",
        "",
        f"- **Cases:** {summary['total_cases']}",
        f"- **Correctness:** {summary['correctness']:.0%}",
        f"- **Groundedness:** {summary['groundedness']:.0%}",
        f"- **Within word budget:** {summary['brevity_pass_rate']:.0%} (median {summary['median_words']} words)",
    ]
    if summary["escalation_rate"] is not None:
        lines.append(f"- **Escalated when required:** {summary['escalation_rate']:.0%}")
    lines += ["", "| Case | Type | Correct | Grounded | Words | Escalated | Note |", "|---|---|---|---|---|---|---|"]
    for r in results:
        v = r["verdict"]
        escalated = "—" if v["escalated"] is None else ("✅" if v["escalated"] else "❌")
        lines.append(
            f"| {r['id']} | {r['type']} | {'✅' if v['correct'] else '❌'} "
            f"| {'✅' if v['grounded'] else '❌'} | {v['words']}{'' if v['brief'] else ' ⚠️'} "
            f"| {escalated} | {v['reason']} |"
        )
    (EVAL_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--webhook", help="Listen webhook URL (live mode)")
    group.add_argument("--answers", help="Pre-collected answers JSONL (offline mode)")
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit("OPENAI_API_KEY is not set; the judge model needs it.")

    cases = load_jsonl(EVAL_DIR / "test_cases.jsonl")
    answers = collect_answers(cases, args)

    results = []
    for case in cases:
        answer = answers.get(case["id"])
        if answer is None:
            print(f"  skipping {case['id']}: no answer provided", file=sys.stderr)
            continue
        print(f"  judging {case['id']} ...", file=sys.stderr)
        results.append({
            "id": case["id"],
            "type": case["type"],
            "answer": answer,
            "verdict": judge_answer(case, answer, api_key),
        })

    summary = summarize(results)
    (EVAL_DIR / "scores.json").write_text(
        json.dumps({"summary": summary, "results": results}, indent=2), encoding="utf-8"
    )
    write_report(results, summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
