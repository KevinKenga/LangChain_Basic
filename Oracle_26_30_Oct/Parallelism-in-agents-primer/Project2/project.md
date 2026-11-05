# Parallel Voting — Spam Judge Ensemble

A small LangGraph project that teaches the **reducer** — the rule that lets many
parallel branches safely write into one shared box of state.

## What we are doing and why

We take **one email** and ask **five independent "judges"** (five GPT-4o calls)
to classify it as `SPAM` or `NOT_SPAM`. All five run **at the same time**. Each
judge drops its vote into a single shared list. A final **tally** step counts the
votes and announces the majority decision.

Two things we are trying to achieve:

1. **Show why reducers exist.** Five judges writing to one `votes` box at once
   would normally crash LangGraph. A reducer (`append into a list`) is what makes
   it work. Remove it and the program stops with a clear error — that crash is
   the whole point of this example.
2. **Show a genuinely useful pattern.** Asking several models the same question
   and taking the majority (an *ensemble vote*) reduces the chance that one bad
   answer decides the outcome. This is a real production technique, not a toy.

We use **five** judges on purpose — an **odd** number means a yes/no vote can
never end in a tie.

## The idea in one picture

```
              ┌──► judge 1 ─┐
              ├──► judge 2 ─┤
   START ─────┼──► judge 3 ─┼──► tally ──► END
              ├──► judge 4 ─┤
              └──► judge 5 ─┘
   (fan-out: all vote at once)   (fan-in: count the votes)
```

Every judge writes its vote to the **same** shared box. That is exactly the
situation a reducer is built for.

## The files — you run only one

```
run.py                ← the ONLY file you run
  └── graph.py               the workflow (state + reducer, judges, tally, wiring)
        ├── llm.py           the GPT-4o call each judge makes
        └── sample_email.py  the email being voted on
```

| File                | Motive                               | What's inside                                                                                                                                                                     |
| ------------------- | ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `run.py`          | The launcher — the one file you run | Loads the email, runs the voting graph once, prints the votes and the final decision                                                                                              |
| `graph.py`        | The workflow (the concept)           | The`State` with the **reducer**, the five judge nodes, the tally node, and the fan-out / fan-in wiring. The reducer line has a comment showing how to reproduce the crash |
| `llm.py`          | The GPT-4o call, kept separate       | One function`classify_email()` — one judge's opinion. Uses a small temperature so judges can sometimes disagree                                                                |
| `sample_email.py` | The input data                       | Three emails (borderline, clearly spam, clearly not). The demo runs on the borderline one so the vote actually matters                                                            |

## How to run

```bash
pip3 install langgraph openai python-dotenv
```

Create a `.env` file next to `run.py` (no quotes, no spaces):

```
OPENAI_API_KEY=sk-your-key-here
```

Then run just the one file:

```bash
python3 run.py
```

## What output to expect

The five votes print as they arrive. Because the judges run in parallel, they may
print **in any order** — that is normal and worth pointing out. Then the tally and
the decision:

```
============================================================
 PARALLEL VOTING  —  5 judges classify one email
============================================================

Email under review:

Hi there! Your free trial ends in 3 days. Upgrade now and get 40% off ...

Votes coming in (in parallel):
   judge 3 voted: NOT_SPAM
   judge 1 voted: SPAM
   judge 5 voted: NOT_SPAM
   judge 2 voted: NOT_SPAM
   judge 4 voted: SPAM

   tally: {'NOT_SPAM': 3, 'SPAM': 2}  ->  decision: NOT_SPAM
============================================================
 FINAL DECISION: NOT_SPAM
 (took 3.10s for all 5 judges together)
============================================================
```

Your exact votes will vary run to run — the borderline email plus a non-zero
temperature means the judges won't always agree. That disagreement is *why* the
vote is interesting.

## The reducer lesson (the takeaway)

- `votes: Annotated[list, add]` in `graph.py` is the reducer. It says: when many
  judges write to `votes` in the same round, **append them all into a list**.
- Delete the reducer (make it a plain `votes: list`) and re-run. LangGraph stops:
  `InvalidUpdateError: At key 'votes': Can receive only one value per step.`
  That is LangGraph telling you: *five values arrived for one box in one round and
  you never told me how to combine them.*
- Put the reducer back and it works again.

Rule to remember: **the moment two or more parallel branches write to the same
state key, you need a reducer to say how their values combine.**
