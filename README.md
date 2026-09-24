# Finary Ops Assessment

A take-home exercise for an operations role at Finary: two short written pieces and one working tool, built on eight weeks of real (synthetic) data describing how an AI agent handles Finary's regulated case volume, with a five-person team reviewing and approving its work.

The brief (`brief.md`) is deliberately under-specified — no schema for the data, no fixed list of decisions to make. Figuring out what's missing, and saying so, is part of the exercise.

## Live app

🔗 **https://finary-ops-assessment.streamlit.app/**

Password-gated. Ask for the access code.

## Key files

| File | What it is |
|---|---|
| `brief.md` | The assignment brief, as given. |
| `PLAN.md` | Working notes — data exploration, raw findings, and how they map to the decisions below. Not a deliverable, but the reasoning behind everything else here. |
| `MISSION_1.md` | **Mission 1** (2 pages max): how operations should run six months from now, four decisions defended with real numbers, and what I built. |
| `MISSION_2.md` | **Mission 2** (1 page max): how I'd run the team of five this quarter — ownership, governance, rhythm. |
| `MEMO.md` | 300-word memo to the five, dated Monday of week one. |
| `app.py` | The tool: a Streamlit dashboard, built on the real data, kept in lockstep with `MISSION_1.md` so the two can't quietly drift apart. |
| `job_id.csv` / `events.csv` | The two source tables — one row per case, and the full step-by-step event log behind it. |
| `requirements.txt` | Python dependencies. |
| `what_i_did.txt` | A running log of my own prompting steps building this with Claude Code. |

## What the data actually showed

- **Five stuck points nobody had flagged.** Two automated hand-offs quietly stopped firing (`captured→analysing`, `approved→executing`), and three states are dead ends with zero recorded recovery (`failed_analysis`, `execution_failed`, `execution_ambiguous`). 200 cases sit in one of these five right now, waiting 20–200× longer than normal.
- **888 `executed` cases — 69% of all volume, the ones that actually touch a client or partner's account — carry zero written reason.**
- **One case type's last rule update made things measurably worse:** `sync_break` v4 vs v3, a confirmed regression, not noise.
- **A real example, found in the data, not invented:** client `C618763`'s compliance case has sat unopened for over six weeks — matches the brief's own line about "a compliance file stalled with nobody chasing it," word for word.

## The four decisions (Mission 1)

1. Risk cases (`compliance_file`, `withdrawal_hold`) jump the queue, in two tiers.
2. Every case type gets a named owner, and a deadline the data sets — not a round number.
3. Version changes are tracked continuously, with a real gate: at least 10 failures on each side before a rate is trusted. Roll back or fix.
4. A real, specific reason required at execution — not the generic placeholder the system already logs and hides today.

## Running it locally

```bash
python3 -m venv finary-env
source finary-env/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Drop `job_id.csv` and `events.csv` in the sidebar to load the real data — both are required together, or it falls back to sample data with a clear flag saying so.

## On assumptions

No schema was given for the two tables, on purpose. Every definition used in the tool and the docs — what counts as "risky," "stuck," "done," or "owner" — is inferred from the shape of the data, not a given fact, and is adjustable live in the tool's **⚙️ Grown-up settings** rather than hardcoded. `MISSION_1.md` flags the load-bearing judgment calls as they come up.
