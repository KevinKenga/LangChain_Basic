# Subagents Demo: Supervisor + 3 Subagents (LangGraph)

## What is a subagent? (10 words)

**A main agent hands focused tasks to helper agents with separate context.**

Concretely:
- The **supervisor** plans the work and decides who does each step. It does not do the work itself.
- A **subagent** gets only two things from the supervisor: a task instruction and the exact data that step needs. It runs with its own system prompt, returns a result, and stops.
- A subagent never sees the supervisor's prompt or the other subagents' prompts. That is the "separate context" part.

---

## Scenario

Kestrel Logistics is hiring a Data Engineer. HR has two PDFs:

| PDF | Contains |
|-----|----------|
| `job_description.pdf` | Must-have and good-to-have skills, budget, notice period |
| `candidate_resume.pdf` | The candidate's experience, skills, notice period |

Goal: **decide whether to shortlist or reject the candidate**, and write a short note for the hiring manager.

---

## The agents

| Agent | Receives | Does | Returns |
|-------|----------|------|---------|
| **Supervisor** | Goal + first 150 characters of each finished result | Picks the next subagent and writes its task | `{"next": ..., "instruction": ...}` |
| **1. Extractor** | Task + both PDFs | Pulls out facts from the job and the resume | JOB facts + CANDIDATE facts |
| **2. Analyst** | Task + extractor's facts (not the PDFs) | Compares the facts | Matches, gaps, fit score |
| **3. Writer** | Task + analyst's analysis (not the facts, not the PDFs) | Writes the decision | Note starting with "Decision: ..." |

---

## Flow

```
START
  -> supervisor  decides: extractor
  -> extractor   reads PDFs, returns facts         -> back to supervisor
  -> supervisor  decides: analyst
  -> analyst     gets facts, returns analysis      -> back to supervisor
  -> supervisor  decides: writer
  -> writer      gets analysis, returns note       -> back to supervisor
  -> supervisor  decides: FINISH
END
```

How LangGraph builds this (`app/supervisor.py`):
1. `START -> supervisor` is a fixed edge.
2. `supervisor -> ?` is a **conditional edge**. `route()` reads `state["next"]` and sends the graph to that subagent, or to `END` on `FINISH`.
3. `extractor -> supervisor`, `analyst -> supervisor` and `writer -> supervisor` are fixed edges, so every subagent reports back.

**Guardrail:** the supervisor is an LLM, so it could pick the wrong subagent or return bad JSON. The code checks its choice against the correct order. If the choice is wrong, the code uses the correct step and logs `LLM choice accepted: False`.

---

## Project layout

```
subagents_demo/
├── README.md
├── requirements.txt
├── .env.example
├── main.py                 # run this
├── data/
│   ├── generate_pdfs.py    # creates the 2 PDFs
│   └── pdfs/
└── app/
    ├── llm.py              # one call_llm() helper
    ├── subagents.py        # extractor, analyst, writer
    └── supervisor.py       # supervisor node + graph wiring
```

---

## Run it

```bash
cd subagents_demo
pip install -r requirements.txt
cp .env.example .env                 # add OPENAI_API_KEY
python data/generate_pdfs.py         # creates the 2 PDFs (once)
python main.py                       # runs the supervisor + subagents
```

Expected output (times will differ):

```
=== FLOW ===
1. SUPERVISOR -> extractor (900 ms) [LLM choice accepted: True]
     task: Extract the key requirements from the job description and the candidate's details from the resume.
2.   EXTRACTOR  received: the 2 PDFs  output: 1100 chars (3000 ms)
3. SUPERVISOR -> analyst   (800 ms) [LLM choice accepted: True]
     task: Compare the job requirements with the candidate's profile.
4.   ANALYST    received: extractor   output: 900 chars (2500 ms)
5. SUPERVISOR -> writer    (700 ms) [LLM choice accepted: True]
     task: Write a shortlist or reject note for the hiring manager.
6.   WRITER     received: analyst     output: 600 chars (1800 ms)
7. SUPERVISOR -> FINISH    (600 ms) [LLM choice accepted: True]

=== EXTRACTOR OUTPUT === ...
=== ANALYST OUTPUT === ...
=== WRITER OUTPUT ===
Decision: Shortlist ...
```

The candidate matches on Spark, AWS, Airflow and Redshift. The gaps are no dbt, only basic Kafka, and a 60-day notice period against the preferred 30. The writer should mention these.

---

## Points to make in class

1. **Separate context:** in the `received:` column, the writer never gets the PDFs. It works only from the analyst's output.
2. **The supervisor doesn't do the work:** it sees only 150-character previews of each result. Its job is to decide and delegate.
3. **Control always returns to the supervisor** after every subagent. That is why the flow log alternates supervisor, subagent, supervisor.
4. **Subagent vs parallel agents:** in the previous NimbusDesk project, 4 agents ran at the same time. Here the subagents run one after another, because each needs the previous one's output.

## Try this

- Make `ORDER` in `app/supervisor.py` an empty check (always accept the LLM's choice) and see whether the supervisor still picks the right order.
- Add a 4th subagent, `interviewer`, that writes 5 interview questions from the analysis. Add it to `ORDER`, add its node, and add one line to the supervisor's system prompt.
