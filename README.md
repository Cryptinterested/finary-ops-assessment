# Finary Ops Assessment

A take-home assessment: two short written pieces and one working app, built on real (synthetic) data

## Live app

🔗 **https://finary-ops-assessment.streamlit.app/**

Password-gated. Ask for the access code.

## Key files

This repo has several files that show my process, but only four are the actual deliverables: **`MISSION_1.md`**, **`MISSION_2.md`**, **`MEMO.md`**, and **the tool** (`app.py`). Everything else here is supporting material — useful for following the reasoning, not something to grade on its own.

**The deliverables:**

| File | What it is |
|---|---|
| `MISSION_1.md` | **Mission 1**: how operations should run six months from now, four decisions defended with real numbers, and what I built |
| `MISSION_2.md` | **Mission 2**: how I'd run the team of five this quarter, ownership, governance, rhythm |
| `MEMO.md` | The 300-word memo required alongside Mission 2, dated Monday of week one |
| `app.py` | **The tool**: a Streamlit dashboard, built on the real data, kept in lockstep with `MISSION_1.md` |

**Supporting material — shows the logic, not separately graded:**

| File | What it is |
|---|---|
| `PLAN.md` | Working notes: data exploration, raw findings, and how they map to the decisions above |
| `what_i_did.txt` | A running log of my own prompting steps building this |
| `requirements.txt` | Python dependencies |

`job_id.csv` / `events.csv` (the two source tables) and the assignment brief itself are intentionally left out of this repo — not mine to publish.

## What the data actually showed

- **Five stuck points nobody had flagged:** two automated hand-offs quietly stopped firing (`captured→analysing`, `approved→executing`), and three states are dead ends with zero recorded recovery (`failed_analysis`, `execution_failed`, `execution_ambiguous`). 200+ cases sit in one of these five right now, waiting 20–200× longer than normal
- **888 `executed` cases, 69% of all volume, the ones that actually touch a client or partner's account, carry zero written reason**
- **One case type's last rule update made things measurably worse:** `sync_break` v4 vs v3, a confirmed regression, not noise
- **A real example, found in the data:** client `C618763`'s compliance case has sat unopened for over six weeks, matches the brief's own line about "a compliance file stalled with nobody chasing it," word for word

## The four decisions (Mission 1)

1. Risk cases (`compliance_file`, `withdrawal_hold`) jump the queue, in two tiers
2. Every case type gets a named owner (per speciality), and a deadline for the data sets
3. Version changes are tracked continuously, with a real gate: at least 10 failures on each side before a rate is trusted. Roll back or fix
4. A real, specific reason required at execution, not the generic placeholder the system already logs and hides today

## Running it locally

```bash
python3 -m venv finary-env
source finary-env/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Drop `job_id.csv` and `events.csv` in the sidebar to load the real data — both are required together, or it falls back to sample data with a clear flag saying so

## On assumptions

Every definition used in the tool and the docs, what counts as "risky," "stuck," "done," or "owner", is inferred from the shape of the data, and is adjustable live in the tool's **⚙️ Grown-up settings** rather than hardcoded. `MISSION_1.md` flags the load-bearing judgment calls as they come up
