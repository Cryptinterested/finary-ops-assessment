# Raising the bar, how I run the team this quarter

- **Today:** launch runs, check outputs, pick up whatever the agent couldn't close. No clear line on whose case type is whose. No check on whether the last rule change actually helped
- **Raising the bar means:** clear ownership for each person (per speciality), a morning that starts with judgment instead of discovery, and a rule that nothing ships on a guess

## Ownership

- Each of the five owns one case type, start to finish: its backlog age, whether its outcomes have a written reason, and sign-off on any change to its rules
- `compliance_file`, `withdrawal_hold`, and `sync_break` each get a named owner and priority (depending on Tier)
- `alert_triage` rotates weekly across all five, everyone still touches it, but one person is accountable at a time

## Governance

- Nothing goes live, a new rule, a new limit, a new version of the agent's instructions, without two things: a before/after check on the failure rate, run on enough failures to mean something, and sign-off from that case type's owner
- This applies to me too. I can ship changes directly, which is exactly why the check has to be real, not a formality
- The alternative: finding out a rule change made things worse the way `sync_break`'s last update did, weeks later, by accident

## Rhythm

- The morning stops being "launch runs and see what happens."
- It's a ten-minute check, the same four numbers every day, for each owner's case type: number of risk cases, how old is the backlog, how many cases are stuck past normal, and how many outcomes have a real reason written down
- Anything past the line gets a name attached to it that morning

## The bar

- Stated simply: **no client-facing failure stays silent**
- Not "we respond fast when a client calls." We know before they have to call, because the numbers above are checked every morning, by the person who owns them, against limits anyone can verify
- The real change this quarter: from five people reacting to whatever surfaces, to five people who each know exactly which numbers are theirs, and what "normal" looks like, before anything goes wrong
