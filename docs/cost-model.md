# Cost model

What a voice agent costs per call, and the escalation rate at which it stops
paying for itself. The formula is the durable part; unit prices are a snapshot
and should be re-checked against current vendor pricing before you quote anyone.

## Cost per call

```
cost_per_call
  = call_minutes × elevenlabs_conversational_rate      # STT + TTS + turn-taking
  + turns × (retrieval_tokens + generation_tokens) × token_rate
  + turns × embedding_tokens × embedding_rate           # query embedding
  + qdrant_hosting / calls_per_month                    # fixed, amortized
```

Voice inverts the usual economics. In a text chatbot, tokens dominate. Here
**conversational minutes dominate and tokens are rounding error** — which means
the lever that actually controls cost is answer length, not model choice.

That is why the [eval suite](../evals/) scores brevity as a first-class metric
alongside correctness. A 120-word answer is not just annoying, it is roughly
twice the TTS bill of a 60-word answer that says the same thing.

### Worked example

Assumptions, all stated so you can replace them:

| Input | Value | Source |
|---|---|---|
| Calls/month | 1,000 | Volume assumption |
| Average call length | 2.5 min | Inbound FAQ and ordering calls |
| Turns per call | 4 | Question, answer, follow-up, close |
| Retrieved context | ~1,200 tokens/turn | Top-4 chunks |
| Generated answer | ~80 tokens/turn | 60-word budget from the eval suite |
| Qdrant | Small managed instance | Fixed monthly |

Per call: **2.5 conversational minutes** plus roughly **5,100 tokens** across
four turns. At 1,000 calls that is 2,500 minutes and 5.1M tokens per month.

Token cost at small-tier pricing is a few dollars. Conversational minutes are
the bill. Multiply 2,500 by your current per-minute rate — that single term will
be the overwhelming majority of the total.

## The number that decides everything

Not cost per call. **Cost per successfully handled call:**

```
effective_cost = total_monthly_cost / (calls × (1 − escalation_rate))
```

An escalated call costs you twice: the agent's minutes *and* the human's time.
At the 75% automation rate this build achieved, 250 of every 1,000 calls still
reach a person, and those 250 carry both costs.

```
monthly_saving
  = calls × (1 − escalation_rate) × handle_minutes / 60 × loaded_hourly_rate
  − monthly_running_cost
```

Escalation rate is the sensitivity that matters. Moving from 25% to 40% does not
cost you 15% of the saving — it removes 15% of the calls from the automated side
*and* adds them to the human side, so the swing is roughly double.

## When this stops being worth it

Be able to say when the answer is no:

| Condition | Why it breaks |
|---|---|
| **Under ~200 calls/month** | Fixed vector-store hosting and build time dominate. A good voicemail-to-text flow is cheaper. |
| **Escalation rate above ~50%** | You are paying for both the agent and the human on most calls. Fix retrieval coverage before scaling. |
| **Answers routinely exceed the word budget** | Minutes are the bill. Verbose answers can double cost without improving resolution — check `brevity_pass_rate` in the eval report. |
| **Safety-critical questions dominate** | Allergies, medical, legal, financial advice. Correct behavior is escalation, so automation rate is capped low by design. See eval case `voice-016`. |
| **Highly variable or frequently changing knowledge** | Re-indexing cost and staleness risk climb; wrong answers on a phone line are expensive in a way wrong answers in a chat window are not. |

## Scaling

| Calls/month | Conversational minutes | Tokens | Dominant cost |
|---|---|---|---|
| 200 | 500 | 1.0M | Qdrant hosting (fixed) |
| 1,000 | 2,500 | 5.1M | Conversational minutes |
| 5,000 | 12,500 | 25M | Conversational minutes |
| 20,000 | 50,000 | 102M | Conversational minutes, by a wide margin |

At every realistic volume the answer is the same: **optimize minutes, not
models**. Switching to a cheaper LLM saves rounding error. Cutting mean answer
length by 20 words saves real money.

## Measuring it in production

Log per-call duration, turn count, token usage, and whether the call escalated.
Escalation rate is the metric to put on a dashboard — it drives both halves of
the saving calculation, and it degrades quietly as your menu, hours, and
policies drift away from what is in the vector store.
