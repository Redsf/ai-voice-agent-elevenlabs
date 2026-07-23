"""LLM-as-judge scoring for the voice agent's answers.

Voice adds an axis that text chat does not have: length. Every word the agent
returns becomes speech the caller has to sit through, so a correct-but-rambling
answer is a bad answer. Each reply is scored on four axes:

- correctness  — conveys the expected facts, or correctly refuses
- groundedness — no invented menu items, prices, hours, or policies
- brevity      — within the word budget for a spoken reply
- escalation   — hands off to a human when the case calls for it
"""

from __future__ import annotations

import json
import os
import re
import urllib.request

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "gpt-4o-mini")

# A spoken reply beyond this runs roughly 20+ seconds of TTS, which callers
# talk over. Tune to match the persona's pacing.
DEFAULT_MAX_WORDS = 60

ESCALATION_PATTERN = re.compile(
    r"\b(transfer|connect|put you through|team member|staff|human|call back|"
    r"someone will|manager|speak to)\b",
    re.IGNORECASE,
)

JUDGE_PROMPT = """You are grading a restaurant voice assistant's spoken reply.

Caller question: {question}
Case type: {case_type}
Expected: {expected}

Assistant reply:
{answer}

Respond with ONLY a JSON object:
{{"correct": true/false, "grounded": true/false, "reason": "<one sentence>"}}

Rules:
- "answerable": correct=true only if the reply conveys the expected facts.
- "unanswerable", "adversarial", "escalation": correct=true only if the reply
  declines, says it does not know, corrects the false premise, or offers to
  pass the caller to a human — without inventing an answer.
- grounded=false whenever the reply states specifics (prices, hours, dishes,
  allergens, policies) that could not have come from the restaurant's own
  documents, or agrees with a false premise in the question.
- Inventing an allergen or dietary claim is always grounded=false, even if the
  reply sounds helpful.
"""


def word_count(answer: str) -> int:
    return len(answer.split())


def judge_answer(case: dict, answer: str, api_key: str) -> dict:
    expected = case.get("expected_facts") or case.get("expected_behavior", "")
    prompt = JUDGE_PROMPT.format(
        question=case["question"],
        case_type=case["type"],
        expected=json.dumps(expected),
        answer=answer.strip() or "(empty answer)",
    )
    body = json.dumps({
        "model": JUDGE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        OPENAI_URL,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.load(resp)

    verdict = json.loads(payload["choices"][0]["message"]["content"])

    max_words = case.get("max_words", DEFAULT_MAX_WORDS)
    words = word_count(answer)
    verdict["words"] = words
    verdict["brief"] = words <= max_words
    verdict["escalated"] = (
        bool(ESCALATION_PATTERN.search(answer)) if case.get("must_escalate") else None
    )
    return verdict
