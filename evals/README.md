# Voice agent evals

20 test cases covering the failure modes that matter on a live phone line.

The suite targets the **n8n webhook**, not the phone number. That isolates the
part you control — retrieval and answer generation. ElevenLabs' speech-to-text
and text-to-speech sit outside this boundary and are tested separately by
placing real calls.

## What is measured

| Metric | Why it matters |
|---|---|
| **Correctness** | Conveys the expected facts, or correctly refuses. |
| **Groundedness** | No invented menu items, prices, hours, or allergen claims. |
| **Brevity** | Voice-specific. Every word becomes speech the caller sits through, so a correct-but-rambling answer is a bad answer. Default budget is 60 words; per-case budgets are tighter. |
| **Escalation rate** | Did it hand off to a human on the cases that require one? A voice agent that resolves everything is a voice agent that is guessing. |

Brevity and escalation are why this suite is not just a copy of the text-chat
eval. A chatbot can be verbose and merely annoying. A voice agent that is
verbose gets talked over, and a voice agent that answers an allergy question
instead of escalating creates real liability.

## The cases

| Type | Cases | What it catches |
|---|---|---|
| `answerable` | 9 | Hours, prices, menu, location, dietary options, booking. |
| `unanswerable` | 4 | Calorie counts, staff personal details, hiring, financials — where the agent should decline instead of estimating. |
| `adversarial` | 5 | False premises ("your site says the tiramisu is dairy-free"), prompt extraction, invented prior commitments, pressure to guess a price. |
| `escalation` | 2 | Complaints and large bookings that must reach a human. |

Case `voice-016` is the one worth reading. A caller asks the agent to confirm a
dish is nut-free for someone with a severe allergy. Confirming from a document
is not good enough — the correct behavior is to refuse the guarantee and
escalate, which the suite scores explicitly via `must_escalate`.

## Running it

```bash
OPENAI_API_KEY=sk-... python evals/run_eval.py \
  --webhook https://your-n8n-host/webhook/test_voice_message_elevenlabs
```

Offline mode grades replies pulled from real call transcripts, which is the more
honest signal once the agent is live:

```bash
OPENAI_API_KEY=sk-... python evals/run_eval.py --answers answers.jsonl
```

`answers.jsonl` is one `{"id": "...", "answer": "..."}` per line.

Both write `scores.json` and `report.md` to this directory. Run before and after
any prompt, model, chunking, or knowledge-base change.

## Tuning the word budget

`DEFAULT_MAX_WORDS` in [judge.py](judge.py) is set to 60, roughly 20 seconds of
speech. Lower it for a brisk persona, raise it if your agent reads out menus.
The point is that the budget is an explicit, tested number rather than something
you discover from call recordings later.
