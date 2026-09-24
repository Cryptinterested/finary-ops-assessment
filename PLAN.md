# Plan — Finary Ops Assignment

## 0. The ask

- **Mission 1** (2 pages max): how operations run in 6 months, what I'd do in month 1 to start. A small number of decisions, defended. Plus one thing built on the real data, for the five, Monday morning.
- **Mission 2** (1 page max): how I run the team of five — ownership, governance, rhythm — as the work changes this quarter. Plus a 300-word memo, dated Monday of week 1, to the five.
- **Tool**: one Python app, graphical interface (Streamlit, agreed), built on `job_id.csv` + `events.csv`.

The brief is deliberately under-specified. Where I've had to assume, I say so.

## 1. The data

Two files, linked by `job_id`:

- **`job_id.csv`** (1,285 rows) — one row per case, latest snapshot: `definition` (alert_triage / sync_break / withdrawal_hold / compliance_file), `version`, `subject` (client id), `state`, timestamps, `runs`, `reviewer`, `review`, `last_reason`.
- **`events.csv`** (6,901 rows) — full history, one row per status change: `at, job_id, actor, from_state, to_state, reason`.

No schema was provided. Reconstructed state machine, from the transition counts:

```
captured → analysing → proposed → approved → executing → executed
                    ↘ awaiting_human → closed_by_hand
                    ↘ failed_analysis
         ↘ closed_at_source
proposed ↘ sent_back → analysing        (reviewer asks for a second look)
         ↘ retry_requested → analysing  (source data changed mid-review)
         ↘ rejected
executing ↘ execution_failed / execution_ambiguous
```

`actor` says who/what did each step. Four automated patterns, one human:

| actor | role | automated? |
|---|---|---|
| `capture:<definition>` | brings a case in from the source feed | yes |
| `scheduler` | picks up a waiting case, starts work | yes |
| `agent:<definition>@v<n>` | the AI agent, tagged with its version | yes |
| `executor` | carries out an approved action | yes |
| `user:<name>` | one of the five | **no — only human actor** |

83.5% of all events (5,763 of 6,901) are automated; 16.5% (1,138) are human. `job_id.csv` is fully derivable from `events.csv` — a case's `state` always equals the `to_state` of its last event, confirmed with zero mismatches across all 1,285 cases. Same for `version`: `job_id.csv`'s version column matches the version embedded in `events.csv`'s `agent:<definition>@v<n>` actor string, zero mismatches. **Version is per-definition, not global** — the agent is really four independently-versioned mini-programs, one per case type, not one system with one version number.

## 2. Findings

**A — Five automated hand-offs/dead-ends are silently failing, not just running slow. 254 cases (19.8% of all 1,285) are stuck; 174 of those (68.5%) have never been touched by a human.**

| Broken step | Normal pace | Stuck cases | How stuck |
|---|---|---|---|
| `captured → analysing` (scheduler) | never over 3h, in 1,164 clean cases | 76, `alert_triage` only | 7–34 days; started week 34, now 18–34%/week and rising |
| `approved → executing` (executor) | median ~4h, max 8h, in 888 clean cases | 45, all 4 case types | median 31.8 days, worst 61.8 days |
| `failed_analysis` (dead end) | — no recovery path exists | 53 cases | median idle 5.6 weeks, worst 8.9 weeks, nothing happens ever again |
| `execution_failed` (dead end) | — no recovery path exists | 17 cases | median idle ~8.5 weeks, same silent-gap pattern one step later in the process |
| `execution_ambiguous` (dead end) | — no recovery path exists | 9 cases | same pattern; gateway timeouts nobody follows up on |

Plus 36 `awaiting_human` and 18 `proposed` cases still waiting on a first look. The three "dead end" rows are structurally identical to `failed_analysis`: once reached, no case in the data has ever moved on from them — but unlike `captured`/`failed_analysis`/`awaiting_human`, these three (`approved`, `execution_failed`, `execution_ambiguous`) always already went through human approval, which is why the never-touched count (174) is smaller than the full stuck count (254). None of this is a slow tail — the scheduler and executor both have a hard, consistent ceiling in the data (3h / 8h) that the stuck cases blow through by 20–200x.

**B — The backlog compounds weekly, it doesn't sit still.**
Open cases (captured + proposed + awaiting_human) grew net almost every week: +24, +17, −4, +4, +15, +31, +27, +20 → 130 by the end (60% over 14 days old); the fuller 254-count from finding A is the real number. At ~15–20 net new/week, unaddressed, this clears 500+ within six months.

**C — No written rationale for the majority outcome, and it's not tracked as a gap today.**
888 `executed` cases (69% of all cases, the ones that touch a client or partner) carry a blank `last_reason`. Every other outcome gets exactly one canned label (`could not decide`, `closed by hand`...) — a tag, not a reason. The riskiest, most client-facing group has the least explanation.

**D — Four independently-versioned mini-programs, and nothing tracks whether an update helps or hurts. This is not tracked anywhere in the system — I computed it by hand from raw outcomes.**

| Case type | Versions | Failure rate | Verdict |
|---|---|---|---|
| `alert_triage` | v6 → v7 | 9.5% (40/423) → 6.4% (11/173) | improved, real |
| `sync_break` | v3 → v4 | 9.9% (13/131) → 11.0% (27/245) | **regressed, real** — failures nearly doubled |
| `withdrawal_hold` | v3 → v4 | 3.5% (4/115) → 5.0% (4/80) | regressed on paper, **likely noise** — same 4 failures, smaller pool |
| `compliance_file` | v2 only | — | not yet updated |

1 confirmed win, 1 confirmed regression, 1 uncertain, 1 untested — and today every one of these just looks like "the version number went up." No dashboard, no log, no check compares before vs. after.

**E — Review latency has a fat tail, and that's where client complaints start.**
Median 47–49h across all case types (fine). p90 ~3.5 days, worst 8 days. Cases created Tue/Wed wait longest (~53h vs 41–47h other days) — weekend pileup. The tail, not the median, is the risk.

**F — What's fine, so it's not a decision:** reviewer load is balanced (192–245 each, no silo by case type); retries mostly work (~75% of 2nd/3rd attempts still reach `executed`).

**G — Steps-per-case average is 5.37; the honest floor is ~5.07, not 4.**
A clean run takes 6 steps minimum (captured→...→executed), and that's 69% of all cases — so 4 isn't achievable without changing the process itself. What is fixable: only 8.9% of cases (115) hit a rework loop, but when they do, steps jump from 5.0 to 8.75. Two distinct causes, both worst in `alert_triage`: `sent_back` (81×, reviewer quality issue) and `retry_requested` (47×, timing issue tied to finding E — source data moves while a case waits).

**Watch, not a headline:** 6 of 1,279 clients have 2 jobs (none concurrent — 8 weeks is too short a window to see real concentration), but 2 of those 6 are the *same* issue recurring a month apart (`C603848`, `C754614`, both `sync_break`). Not enough to build a decision on; enough to make visible before it becomes one.

## 3. Mission 1 — the decisions

Four, to fit "a small number" in 2 pages. (D and G's material folds into decision 2 as supporting detail rather than standing alone — flag if you'd rather keep version-checking as its own headline, `sync_break`'s regression is a clean example.)

1. **Fix all five broken hand-offs/dead-ends in week 1, each alerted at a threshold computed live from the data, not a number hand-picked once and left to go stale:**
   - alert if a case sits in `captured` past its computed ceiling — **~3 hours** as of this export, the observed max across 1,164 normal cases, so past it is provably abnormal, not slow;
   - alert if `approved` past its computed ceiling — **~8 hours** as of this export, same logic, across 888 clean executions;
   - `failed_analysis`, `execution_failed`, and `execution_ambiguous` have *no* recovery path today — none of these is an alert on an existing step, all three are new: auto-escalate to the case-type owner if idle past a policy threshold (**48 hours** by default), since right now nothing happens to any of these cases, ever.
   The tool recomputes the first two ceilings from whatever data is loaded — they move as the process does, instead of freezing at today's numbers. *(A)*
2. **Named owner per case type, with an SLA the data computes, not a round number I picked:** 254 open cases get tracked (not just the 130 in "backlog" states). Each case type's SLA is its own p90 review latency plus a buffer, tightened for case types flagged as money/compliance risk — as of this export that's `compliance_file`/`withdrawal_hold` at **3 business days**, `alert_triage`/`sync_break` at **5**, both above the data's own ~3.5-day p90 so the SLA flags genuine outliers, not normal cases. Ownership also covers version sign-off, with a specific gate: **no version change reaches full traffic until its failure rate is compared against the prior version with at least 10 observed failures on each side** — a policy choice, not a computed one, because `withdrawal_hold`'s v4 shows exactly why a case-count gate isn't enough: 80 cases (past any reasonable case-count minimum) but only 4 failures on each side, still too few to trust a rate from. Below the gate, the rate is noise, not signal, and shouldn't drive a rollback or a rollout decision. *(A, B, D, G)*
3. **Require a one-line written reason at execution, not just on failure** — a required field that blocks the execution step from completing without it, not a style guideline. `executed` is the biggest bucket and has zero record today; mine and ship this myself, no Engineering project needed. *(C)*
4. **The tool is the daily operating surface**, enforcing the thresholds above in real time, recomputed from whatever's loaded — backlog age against decision 2's SLAs, the five hand-off/dead-end alerts from decision 1, rationale coverage, version regressions past the 10-failure gate — replacing "hear about it when a client calls." *(A, B, E)*

**Six months out:** exceptions get an age and an owner the same day, not weeks later, against thresholds that move with the data instead of going stale; every version change is checked before/after, not trusted blindly; the record explains the majority outcome, not just the failures. **Month one:** fix the five hand-offs/dead-ends, ship the dashboard, ship the written-reason rule, set ownership and age limits.

**What I built** = the tool (§5), pointed at the real 8-week data — this is what's in front of the five Monday morning, led with finding A since it was actively getting worse, silently, the whole time.

**Left out:** redesigning the agent's own prompting/model (data doesn't call for it, basics come first); estimating client financial impact (no money-amount data in this export).

## 4. Mission 2 — the structure

- **Ownership:** each of the five owns one case type end to end (its backlog age, its rationale coverage, its version sign-off). `alert_triage`'s volume means shared/rotating ownership; the other three get a named owner.
- **Governance:** nothing ships — rule, threshold, or agent version — without the before/after check and the owner's sign-off.
- **Rhythm:** the dashboard replaces undirected "launch runs, check outputs" with a 10-minute check-in on three numbers — backlog age, stuck-case count, rationale coverage.
- **The bar:** "no client-facing failure stays silent," measured by the tool, not word of mouth.

**Memo** (300 words, Monday week 1, to the five as a teammate). The brief's actual ask: *"what this end of year means and what is changing for them."* Not an incident report — a year-end-framed message: brief look back at what this year's agent volume has meant (a few thousand regulated cases/month, most unexplained until now); plain statement of what's changing this quarter (named ownership, the dashboard, written reasons at execution); the hand-off fixes as one proof point among several, not the whole message. Ends forward-looking.
*Assumption: "end of year" read as a genuine forward-looking frame, not a specific calendar event — flag if that's wrong.*

## 5. The tool

`streamlit run app.py`. Accepts `job_id.csv` + `events.csv`, or `events.csv` alone (the tool rebuilds the snapshot itself, per §1's derivability check). Views, in the order they'd actually be used:

0. **Findings → decisions** (landing page) — one row per headline decision: finding, key number, the decision it drives. Kept in lockstep with Mission 1's final decision list, deliberately, so the tool and the written piece can't drift apart.
1. **Today's headline** — the five hand-off/dead-end alerts (A), each fired at its own live-computed threshold, not a vague "looks stuck": `captured`, `approved`, `failed_analysis`, `execution_failed`, `execution_ambiguous`, each with a count and how far past the line it is.
2. **Backlog** — all 254 not-yet-finished cases, weeks-since-touched, oldest first, filterable by case type/owner/state, flagged if never human-touched, and flagged red once past its decision-2 SLA (computed live per case type — as of this export, 3 business days for `compliance_file`/`withdrawal_hold`, 5 for `alert_triage`/`sync_break`); weekly created-vs-closed trend (B). Rows matching the `J00414` pattern — never human-touched **and** flagged as a risk case type **and** over the normal-pace ceiling from finding A — are shown **in bold**, so the highest-risk stalled cases can't be scrolled past.
3. **Rationale coverage** — share of each outcome with a real reason vs. blank, by case type, `executed` called out (C).
4. **Version watch — four mini-programs, side by side.** One panel per case type: every version, its failure rate *and* sample size, before/after delta, plain flag (improved / regressed-confirmed / regressed-watch / not yet updated), and a clear "under 10 observed failures — not enough data yet" marker per decision 2's gate rather than a false-confidence percentage. Sorted worst-first — directly answers "where do we improve" (D).
5. **Review speed** — median/p90/worst wait, by case type and by weekday created (E).
6. **Case lookup** — any `job_id` or `subject`: visual timeline of every step, actor, lag between steps, current status, idle time, flagged against the normal-pace baselines from finding A. A case matching the same high-risk pattern as the backlog view is called out **in bold** at the top of its timeline. (Built for the `J00414` story, works for any case.)
7. **Client lookup** — grouped by `subject`: multi-job clients, same-issue repeats flagged (the watch-for item).
8. **Rework tracker** — steps-per-case over time, rework share split `sent_back` vs `retry_requested`, by case type (G).

Built with `pandas` + Streamlit's native charts. No extra libraries needed at this size.

## 6. Assumptions

- `job_id.csv` + `events.csv` is the complete export.
- "Reaches a client" inferred from the brief's own examples (sync_break↔bank connection, withdrawal_hold↔blocked withdrawal, compliance_file↔stalled file) — no explicit field confirms this.
- `subject` (e.g. `C333859`) is assumed to be an existing, already-onboarded Finary client, not a prospect or a signup in progress — there's no field distinguishing client status, so this can't be confirmed from the data alone.
- "Now" for age calculations = 2026-09-21, a week after the data ends (2026-09-13) — ages are slightly conservative, not inflated.
- Streamlit, local, single-user — right for a Monday-morning tool, not a hardened service.
- Tool is read-only against the CSVs.

## 7. Next

1. ~~Explore and validate the data~~ — done.
2. Write Mission 1 (≤2 pages) and Mission 2 + memo (≤1 page + 300 words).
3. Build the Streamlit tool, screenshot it working.
4. Final check: tool and both written pieces tell the same story, same headline findings.

Will draft Mission 1/2 in plain Markdown first — fastest to iterate. Say if you want them exported to something else (PDF, doc, artifact) once the content's settled.
