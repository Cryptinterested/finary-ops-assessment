# Operations, six months out, and the thing I built

What's striking from reading the data:
- **Five places where a case should move forward, and doesn't:**
    - Two broken hand-offs (automated steps that used to move cases forward on their own, and stopped):
        - `captured`→`analysing` (the scheduler's job, 76 alert_triage cases stuck, should take under 3h, some stuck 7–34 days)
        - `approved`→`executing` (the executor's job, 45 cases across all types, should take under 8h, some stuck 61.8 days)
    - Three dead ends (states with zero recorded recovery, no case in the data has ever moved on from them)
        - `failed_analysis` (53 cases)
        - `execution_failed` (17 cases)
        - `execution_ambiguous` (9 cases)
- **Most cases have no written reason:** 69% of all cases go all the way through and reach a client. None say why the agent did what it did
- **Nobody checks whether a change to the agent's rules made things better or worse:** Today it's a coin flip, and we need to track

None of this shows up by watching the agent work — only by reading the full history, case by case, and asking where it stopped moving. **The fix is simple to state: make quiet failures loud.**

> **One real example, not a guess.** Client **C618763** filed a compliance case on August 6th. The agent said it needed a person to decide, and queued it for review. Nobody has opened it since. **46 days and counting**, exactly the brief's own description: *"a compliance file stalled with nobody chasing it."*

## Four decisions

**1. Risk cases jump the queue**
- **Trigger: `compliance_file` or `withdrawal_hold`** are direct client money or compliance exposure. Nothing else sets this off, it's our top priority
- **Tier 1, still open:** unseen and already stuck, or the agent dropped it (`failed_analysis`/`awaiting_human`). 24 cases meet that bar currently, out of 313 risk cases overall. C618763's is one of them
- **Tier 2, completed with failure:** a trigger case that finished `rejected` instead of succeeding, despite smooth approval. 9 cases right now, each reviewed and the reason noted so a repeat shows as a pattern
- Both tiers go first in the owner's queue, not folded into the general backlog (as it seems to be today)

**2. Give every case type an owner, and a deadline the data sets**
- The fix that would have caught C618763's case, well before day 45
- **Owners, computed:** from who already reviews the most of each type: `compliance_file`→camille.naval, `withdrawal_hold`→theo.brissac, `sync_break`→samir.oueslati, `alert_triage`→rotates weekly (too high-volume for one)
- **Deadlines:**, from normal review time, tightened for risk types: `compliance_file`/`withdrawal_hold` get **3 business days**, `alert_triage`/`sync_break` get **5**. 240 cases are already past deadline. Goal: lower the bar every two months. Next target: `compliance_file`/`withdrawal_hold` get **2 business days**, `alert_triage`/`sync_break` get **4**.

**3. Track version failures continuously, then act: roll back or fix**
- Ownership includes signing off on rule changes for the case type you own. No version is trusted until checked against the one before it, with at least 10 failures on each side: `withdrawal_hold`'s last update looked worse (3.5% → 5.0%), but only 4 failures each time (cases shrank)
- The moment a version is confirmed worse, the action is immediate: roll back. Right now `sync_break` v4 is confirmed regressed against v3, roll back or fix; `withdrawal_hold` is flagged to watch, too thin to act on yet

**4. Require a real reason at execution**
- Every failure already gets a label. `executed` cases (888 of them), 69% of everything, the ones that actually touch a client or partner's account, get nothing. In a regulated business, that's backwards
- Simpler than it sounds: the system already logs a generic reason for every step ("every step applied"), it's just hidden from the record for executed cases. Stop hiding it, and require a real, specific line instead of the boilerplate before execution completes. We can turn this on ourselves, no Engineering project needed

## Month one

- **Week 1:**
    - Check the agent proposing for `compliance_file`/`withdrawal_hold` and assign cases (24) straight to a person from day one
    - Fix the two broken automated actors: `scheduler` and `executor` and trigger reassessment on the three dead ends (`failed_analysis`, `execution_failed`, `execution_ambiguous`) if fails a second time, human assignement 
- **Week 2:** Set the deadlines and name an owner for each case type (introduction of the business days caps and owner per speciality)
- **Week 3:** Turn on the required reason at execution
- **Week 4:** The dashboard (tool built) goes live as the team's morning tool. The rule-change check applies to everything shipped from here on

## Six months out

- **Risk** cases go straight to a person, first in every queue, and no stuck point sits silent for a month, alerts catch it the same day
- Every case has an age, an owner (by speciality), and a deadline that moves with the data
- Every rule change is checked before it's trusted
- The record explains most of what the agent does
- The five spend mornings on judgment calls effectively flagged

## What I built

A Streamlit dashboard, run on the real 8 week export. It needs both `job_id.csv` and `events.csv` to switch to real data and provide analysis:
- Opens on a data **Overview**, then **What to fix first**: each decision above, its finding, and today's live number
- Decision 1's Tier 1 count is the same bold rows shown on **Cases waiting**; Tier 2 sits alongside it on the same card. "Stuck" is itself a setting (90% today), adjustable
- The full backlog against decision 2's deadlines, plus every case type's rule change history with real failure counts
- Which cases have a *real* written reason, by outcome, blank or a generic placeholder both count as no reason, so exposing the boilerplate later can't fake a fix. Every case still missing one, listed by `job_id`
- **Check one team member** pick anyone on the five and see their success rate, specialty case type (the rotating one, `alert_triage`) doesn't count as a specialty, and their own queue in Tier 1 / Tier 2 / rest order
- A full timeline for any single case, including `J00414`, C618763's, called out by name

**What I want it to tell the five, first thing Monday:** the backlog didn't get big overnight, and it won't fix itself. Five specific things broke quietly. They're fixable this week, and here's how we'll know if it happens again

## Next, and what I left out

- **Next:** get the alerts and deadlines live, then watch a full week of real use before tightening anything
- **Left out on purpose:** redesigning how the agent itself thinks. The data points at broken process steps, not bad judgment (a second month problem at the earliest)
- **Also left out:** the money cost to clients. This export has no dollar figures, so I won't guess at one. But this can have real impact
