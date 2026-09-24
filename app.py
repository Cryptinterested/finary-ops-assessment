"""
Ops Control — Finary
A Streamlit dashboard built on the real agent-activity export (job_id.csv + events.csv).

Nothing here is frozen to one dataset's numbers. Every threshold — normal-pace
ceilings, SLA days, ownership, which outcomes count as a "problem" — is computed
live from whichever events.csv / job_id.csv is loaded, or set as an adjustable
policy in the sidebar. Load a different (longer, newer, bigger) export and every
number on screen recomputes from that export, not from July–September 2026.
"""

import io
import os
from datetime import timedelta

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Ops Control — Finary", layout="wide", page_icon="🛠️")

LOGO_PATH = "finary_logo.jpeg" if os.path.exists("finary_logo.jpeg") else None

# Logo in the top-left corner, on every page, from the very first screen.
if LOGO_PATH:
    st.logo(LOGO_PATH)

# ============================================================================
# Simple lock screen — nothing else on the page renders until the code is
# typed correctly. One field, one word, easy for anyone to use.
# ============================================================================
ACCESS_CODE = "finary27"

if "unlocked" not in st.session_state:
    st.session_state["unlocked"] = False


def _check_code():
    st.session_state["unlocked"] = st.session_state.get("code_box", "").strip() == ACCESS_CODE


if not st.session_state["unlocked"]:
    st.markdown("<div style='height:8vh'></div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        st.write("Type the code to open the dashboard.")
        st.text_input("Code", type="password", key="code_box", on_change=_check_code, label_visibility="collapsed", placeholder="Enter the code…")
        if st.session_state.get("code_box") and not st.session_state["unlocked"]:
            st.error("That's not the code — try again.")
    st.stop()

# ============================================================================
# Loading — accepts events.csv alone (derives the snapshot) or both files.
# Nothing dataset-specific here: no state names, actor names, or numbers.
# ============================================================================
@st.cache_data(show_spinner=False)
def load_events(file_bytes: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(file_bytes), parse_dates=["at"])
    return df.sort_values("at").reset_index(drop=True)


def _definition_from_actor(actor: str):
    if isinstance(actor, str) and actor.startswith("capture:"):
        return actor.split(":", 1)[1]
    if isinstance(actor, str) and actor.startswith("agent:"):
        return actor.split(":", 1)[1].split("@")[0]
    return None


@st.cache_data(show_spinner=False)
def derive_jobs(events: pd.DataFrame) -> pd.DataFrame:
    """Rebuild the job_id.csv snapshot from events.csv alone: a job's `state` is
    always the `to_state` of its last event, `version` the version embedded in
    its last `agent:<definition>@v<n>` actor string. `subject` (client id) is
    NOT recoverable from events.csv alone — that needs job_id.csv too."""
    ev = events.copy()
    last = ev.groupby("job_id").tail(1).set_index("job_id")
    first_capture = ev.loc[ev["to_state"].notna()].groupby("job_id")["at"].min()

    ev["definition_guess"] = ev["actor"].map(_definition_from_actor)
    definition = ev.dropna(subset=["definition_guess"]).groupby("job_id")["definition_guess"].first()

    agent_ev = ev[ev["actor"].astype(str).str.startswith("agent:")].copy()
    agent_ev["version_guess"] = agent_ev["actor"].str.split("@v").str[-1]
    version = agent_ev.groupby("job_id")["version_guess"].first()

    entry_state_counts = ev["to_state"].value_counts()
    # "runs" ~ how many times a job (re)entered whichever state is entered most
    # often right after the very first event (proxy for "analysis attempts")
    first_step_state = ev.groupby("job_id").nth(1)["to_state"] if len(ev) else pd.Series(dtype=object)
    common_second_state = first_step_state.mode().iloc[0] if len(first_step_state) else None
    runs = (ev.loc[ev["to_state"] == common_second_state].groupby("job_id").size()
            if common_second_state else pd.Series(dtype=int))

    user_ev = ev[ev["actor"].astype(str).str.startswith("user:")].groupby("job_id").tail(1).set_index("job_id")

    last_reason = last["reason"]

    jobs = pd.DataFrame({
        "state": last["to_state"],
        "last_change_at": last["at"],
        "created_at": first_capture,
        "definition": definition,
        "version": version,
        "runs": runs,
        "reviewer": user_ev["actor"] if not user_ev.empty else pd.Series(dtype=object),
        "review": user_ev["to_state"] if not user_ev.empty else pd.Series(dtype=object),
        "reviewed_at": user_ev["at"] if not user_ev.empty else pd.Series(dtype="datetime64[ns]"),
        "last_reason": last_reason,
    })
    jobs["runs"] = jobs["runs"].fillna(0).astype(int)
    jobs["subject"] = pd.NA
    jobs.index.name = "job_id"
    return jobs.reset_index()


@st.cache_data(show_spinner=False)
def load_jobs_csv(file_bytes: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(file_bytes))
    for c in ("created_at", "last_change_at", "reviewed_at", "executed_at"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def human_touched_ids(events: pd.DataFrame) -> set:
    return set(events.loc[events["actor"].astype(str).str.startswith("user:"), "job_id"])


# ============================================================================
# Sidebar — data
# ============================================================================
st.sidebar.title("🛠️ Ops Control")
st.sidebar.caption("Add your own files below, or leave them empty to look at the sample data.")
st.sidebar.subheader("📁 Your files")
jobs_up = st.sidebar.file_uploader("job_id.csv", type="csv", key="jobs_up")
events_up = st.sidebar.file_uploader("events.csv", type="csv", key="events_up")


def _local(path):
    return path if os.path.exists(path) else None


events_path, jobs_path = _local("events.csv"), _local("job_id.csv")

# We only switch to your data once BOTH files are uploaded. Anything less —
# one file, or neither — and we use the default sample data instead, so the
# dashboard never mixes an upload with a leftover file that doesn't match it.
using_uploaded_data = (events_up is not None) and (jobs_up is not None)

if using_uploaded_data:
    events_bytes = events_up.read()
    jobs_bytes = jobs_up.read()
else:
    events_bytes = open(events_path, "rb").read() if events_path else None
    jobs_bytes = open(jobs_path, "rb").read() if jobs_path else None
    if (events_up is not None) != (jobs_up is not None):
        st.sidebar.warning("Add the other file too — we need both before we switch to your data.")

if events_bytes is None or jobs_bytes is None:
    st.title("🛠️ Ops Control")
    st.warning("👈 Add **both files** in the boxes on the left: `job_id.csv` and `events.csv`.")
    st.stop()

events = load_events(events_bytes)
jobs = load_jobs_csv(jobs_bytes)
jobs_source = "your upload" if using_uploaded_data else "sample data"

have_subject = jobs["subject"].notna().any()
htouched = human_touched_ids(events)
jobs["human_touched"] = jobs["job_id"].isin(htouched)

# ============================================================================
# Data window — worked out from whichever data is loaded (yours, or the
# sample). Every computed number in the app is only as meaningful as this
# window, so it's shown right where we say which data is active.
# ============================================================================
data_start, data_end = events["at"].min(), events["at"].max()
span_days = max((data_end - data_start).days, 1)
now = data_end + timedelta(days=7) + timedelta(hours=12)

WINDOW_TXT = (f"**{data_start.date()} → {data_end.date()}** "
              f"({span_days} days, about {span_days/7:.1f} weeks) · **{len(jobs):,}** cases · **{len(events):,}** things that happened")

if using_uploaded_data:
    st.sidebar.success(f"✅ Using the files you uploaded\n\n{WINDOW_TXT}")
else:
    st.sidebar.info(f"ℹ️ Using the default sample data\n\n{WINDOW_TXT}")

st.sidebar.caption(f"📅 Today's date, for this report: **{now.date()}** — used to work out how old each case is, "
                    f"and whether it's past its deadline.")

# ============================================================================
# State graph — derived from events.csv, not assumed. A state is "open"
# (still moving) if it's ever a `from_state`; "terminal" if it's only ever a
# `to_state`. This is exactly how finding A's scheduler/executor gaps and the
# failed_analysis dead-end were originally found — generalized to any data.
# ============================================================================
from_states = set(events["from_state"].dropna()) - {""}
to_states = set(events["to_state"].dropna())
structurally_open = from_states
structurally_terminal = sorted(to_states - from_states)

def _keyword_hint(states, keywords):
    return sorted(s for s in states if any(k in s.lower() for k in keywords))


with st.sidebar.expander("⚙️ Grown-up settings (optional)"):
    st.caption("We've already picked sensible defaults. Only change these if you know why.")

    problem_hint = _keyword_hint(structurally_terminal, ["fail", "reject", "declin", "ambig", "error", "block", "stall"])
    problem_states = st.multiselect(
        "Which endings count as 'something went wrong'?",
        structurally_terminal, default=problem_hint)

    unresolved_hint = _keyword_hint(structurally_terminal, ["fail", "could not", "unresolved", "stall", "ambig"])
    unresolved_terminal = st.multiselect(
        "Which endings actually still need someone to look at them?",
        structurally_terminal, default=unresolved_hint)

    definitions = sorted(jobs["definition"].dropna().unique().tolist())
    risk_hint = _keyword_hint(definitions, ["withdraw", "compliance", "payment", "transfer", "fund", "kyc", "aml"])
    risk_defs = st.multiselect(
        "Which case types involve real money or compliance risk?", definitions, default=risk_hint)

    ceiling_pctl = st.select_slider(
        "How strict should 'stuck' mean?", options=[50, 75, 90, 95, 99, 100], value=90,
        help="For example: 90 means we flag a case once it's slower than 90% of all the normal cases we've seen. "
             "100 means we only flag it once it's slower than every single one — the strictest, safest setting. "
             "This is what drives every number on 🛠️ What to fix first.")

    escalate_hours_deadend = st.number_input(
        "Hours to wait before flagging a dead end", value=48, min_value=1,
        help="Some outcomes have no 'normal speed' to compare to, so this is a plain choice, not a calculation.")

    min_failures_gate = st.number_input(
        "How many failures needed before we trust a comparison?", value=10, min_value=1,
        help="A rate built on very few failures can be misleading, no matter how many total cases back it.")

    reason_vocab = sorted(set(jobs["last_reason"].dropna().unique().tolist()))
    generic_hint = _keyword_hint(reason_vocab, ["every step", "n/a", "not specified", "no reason", "default", "auto-generated", "placeholder", "unspecified"])
    generic_reasons = st.multiselect(
        "Which written 'reasons' are really just a generic placeholder, not a real explanation?",
        reason_vocab, default=generic_hint,
        help="Text that's identical for every case in that outcome doesn't tell us why THIS case ended that way. "
             "Excluded from the reason-coverage counts on 📝 Did we explain why?")

open_states = structurally_open | set(unresolved_terminal)
done_states = set(structurally_terminal) - set(unresolved_terminal)

# ============================================================================
# Dwell-time ceilings — computed per state from the loaded data itself.
# ============================================================================
@st.cache_data(show_spinner=False)
def compute_dwell(events: pd.DataFrame):
    ev = events.sort_values(["job_id", "at"]).copy()
    ev["next_at"] = ev.groupby("job_id")["at"].shift(-1)
    ev["dwell_h"] = (ev["next_at"] - ev["at"]).dt.total_seconds() / 3600
    return ev.dropna(subset=["dwell_h"])


dwell = compute_dwell(events)


@st.cache_data(show_spinner=False)
def dwell_ceiling(dwell: pd.DataFrame, state: str, pctl: int):
    d = dwell.loc[dwell["to_state"] == state, "dwell_h"]
    if d.empty:
        return np.nan, 0
    return float(d.quantile(pctl / 100)), int(len(d))


def ceiling_for_state(state: str):
    if state in unresolved_terminal:
        return escalate_hours_deadend, 0  # no historical exits possible — policy value
    return dwell_ceiling(dwell, state, ceiling_pctl)


# ============================================================================
# Ownership — computed from who already reviews the most of each case type;
# the single highest-volume case type rotates instead of one fixed owner.
# ============================================================================
@st.cache_data(show_spinner=False)
def compute_ownership(events: pd.DataFrame, jobs: pd.DataFrame):
    reviewers = sorted({a.split(":", 1)[1] for a in events["actor"].astype(str) if a.startswith("user:")})
    ue = events[events["actor"].astype(str).str.startswith("user:")].merge(
        jobs[["job_id", "definition"]], on="job_id", how="left")
    top_owner = {}
    if len(ue):
        xtab = ue.groupby(["definition", "actor"]).size().unstack(fill_value=0)
        top_owner = xtab.idxmax(axis=1).str.split(":", n=1).str[1].to_dict()
    vol = jobs["definition"].value_counts()
    rotating_def = vol.idxmax() if len(vol) else None
    return reviewers, top_owner, rotating_def


reviewers, top_owner_map, rotating_def = compute_ownership(events, jobs)


def owner_for(definition: str, now: pd.Timestamp) -> str:
    if definition == rotating_def and reviewers:
        return f"{reviewers[now.isocalendar()[1] % len(reviewers)]} (rotating — highest volume)"
    return top_owner_map.get(definition, "unassigned")


# ============================================================================
# SLA — computed per case type from its own review-latency p90, tightened for
# anything flagged as money/compliance risk. Not a fixed day count.
# ============================================================================
@st.cache_data(show_spinner=False)
def compute_sla_days(jobs: pd.DataFrame, risk_defs: list):
    rv = jobs.dropna(subset=["reviewed_at", "created_at"]).copy()
    rv["latency_days"] = (rv["reviewed_at"] - rv["created_at"]).dt.total_seconds() / 86400
    p90 = rv.groupby("definition")["latency_days"].quantile(0.9)
    sla = {}
    for d in jobs["definition"].dropna().unique():
        base = p90.get(d, np.nan)
        base = 10.0 if pd.isna(base) else base
        days = np.ceil(base) + 1
        if d in risk_defs:
            days = max(1, np.ceil(days * 0.6))
        sla[d] = int(days)
    return sla


sla_map = compute_sla_days(jobs, risk_defs)


def business_days(start, end) -> float:
    if pd.isna(start) or pd.isna(end) or end <= start:
        return 0.0
    return float(np.busday_count(start.date(), end.date()))


V_OVERVIEW = "📊 Overview"
V_HOME = "🏠 Start here"
V_FIX = "🛠️ What to fix first"
V_TODAY = "🚨 What's wrong right now"
V_BACKLOG = "📋 Cases waiting"
V_REASON = "📝 Did we explain why?"
V_VERSION = "🔄 Did the last change help?"
V_SPEED = "⏱️ How fast do we check things?"
V_CASE = "🔍 Look up one case"
V_CLIENT = "👤 Follow one client"
V_TEAM = "🧑‍💼 Check one team member"
# V_TEAM is deliberately left out of VIEW_BLURBS/🏠 Start here's tour — it's
# reachable from the sidebar menu, just not advertised as a front-door page.
ALL_VIEWS = [V_OVERVIEW, V_HOME, V_FIX, V_TODAY, V_BACKLOG, V_REASON, V_VERSION, V_SPEED, V_CASE, V_CLIENT, V_TEAM]
VIEW_BLURBS = {
    V_OVERVIEW: ("📊", "Overview", "The big picture: how many cases, how many events, how the team and the robot helper are doing, over the whole period."),
    V_HOME: ("🏠", "Start here", "A quick tour of every page, in plain words."),
    V_FIX: ("🛠️", "What to fix first", "The tool's top picks: the biggest problems, and what to do about them."),
    V_TODAY: ("🚨", "What's wrong right now", "A fast, no-detail glance at every stuck point, worst first — the full story is on 🛠️ What to fix first."),
    V_BACKLOG: ("📋", "Cases waiting", "Every case that isn't finished yet, so nothing piles up unseen."),
    V_REASON: ("📝", "Did we explain why?", "Checks whether we wrote down WHY a case ended the way it did."),
    V_VERSION: ("🔄", "Did the last change help?", "When we change the robot's instructions, did things get better or worse?"),
    V_SPEED: ("⏱️", "How fast do we check things?", "How long people take to review a case, normally and on a bad day."),
    V_CASE: ("🔍", "Look up one case", "Type in one case's ID and see everything that happened, step by step."),
    V_CLIENT: ("👤", "Follow one client", "Pick a person, see their case(s), and watch the story unfold."),
}

def _go_to(target: str):
    st.session_state["view_choice"] = target


if "view_choice" not in st.session_state:
    st.session_state["view_choice"] = V_HOME

st.sidebar.subheader("📍 Where to go")
view = st.sidebar.radio("Go to", ALL_VIEWS, label_visibility="collapsed", key="view_choice")

# ============================================================================
# Shared computations
# ============================================================================
not_done = jobs[jobs["state"].isin(open_states)].copy()
not_done["idle_hours"] = (now - not_done["last_change_at"]).dt.total_seconds() / 3600
not_done["age_days"] = (now - not_done["created_at"]).dt.total_seconds() / 86400
not_done["owner"] = not_done["definition"].map(lambda d: owner_for(d, now))
not_done["sla_days"] = not_done["definition"].map(lambda d: sla_map.get(d, 10))
not_done["age_bdays"] = not_done.apply(lambda r: business_days(r["created_at"], now), axis=1)
not_done["past_sla"] = not_done["age_bdays"] > not_done["sla_days"]

ceil_cache = {s: ceiling_for_state(s) for s in not_done["state"].unique()}
not_done["ceiling_h"] = not_done["state"].map(lambda s: ceil_cache[s][0])
not_done["ceiling_n"] = not_done["state"].map(lambda s: ceil_cache[s][1])
not_done["past_ceiling"] = not_done["idle_hours"] > not_done["ceiling_h"]

# High risk = a compliance_file/withdrawal_hold case, and either:
#   - nobody's ever looked at it, and it's already stuck past normal, in ANY open state; or
#   - the agent itself dropped it (failed_analysis/awaiting_human) — that counts even if a
#     person already looked at it once and it ended up stuck again.
# One definition, used everywhere (📋 Cases waiting's bold rows, 🛠️ Decision 1's count) so
# the two pages can't quietly disagree on the same question.
DECISION1_STATES = ["failed_analysis", "awaiting_human"]
not_done["high_risk"] = not_done["definition"].isin(risk_defs) & (
    ((~not_done["human_touched"]) & not_done["past_ceiling"].fillna(False))
    | not_done["state"].isin(DECISION1_STATES)
)


def bold_style(df: pd.DataFrame, mask: pd.Series):
    def _fn(row):
        return ["font-weight: bold; background-color: rgba(220,38,38,0.10)" if mask.loc[row.name] else "" for _ in row]
    return df.style.apply(_fn, axis=1)


def has_real_reason(reason_series: pd.Series, generic_reasons) -> pd.Series:
    """True only for a non-blank reason that isn't one of the known generic
    placeholders (⚙️ Grown-up settings) — e.g. 'every step applied' says
    what happened, not why THIS case ended that way. Shared by Decision 4's
    card and 📝 Did we explain why? so they can't disagree."""
    cleaned = reason_series.fillna("").str.strip()
    return (cleaned != "") & (~cleaned.isin(set(generic_reasons)))


VERDICT_ACTIONS = {
    "regressed (confirmed)": "Roll back to the previous version now, and fix the rules before shipping it again.",
    "regressed (small sample, watch)": "Don't roll back yet — not enough failures to be sure. Keep tracking.",
    "no change": "No action needed.",
    "improved (small sample)": "Looks better, but on a thin sample — keep tracking before calling it settled.",
    "improved": "Keep it live.",
    "not yet updated": "Nothing to compare yet.",
}


def compute_version_verdicts(jobs: pd.DataFrame, problem_states, min_failures_gate: int) -> pd.DataFrame:
    """One row per case type: its latest version change (if any), whether it
    helped or hurt, and the recommended action — track failures continuously,
    then either roll back to the older version or flag it to be fixed. Shared
    by Decision 3's summary card and 🔄 Did the last change help? — computed
    once, so the two can't disagree on the same question."""
    vt = jobs.dropna(subset=["version"]).copy()
    vt["version"] = pd.to_numeric(vt["version"], errors="coerce")
    vt["failed"] = vt["state"].isin(problem_states)

    rows = []
    for defn, g in vt.groupby("definition"):
        by_v = g.groupby("version").agg(n=("job_id", "size"), fail=("failed", "sum")).reset_index().sort_values("version")
        by_v["rate"] = (by_v["fail"] / by_v["n"] * 100).round(1)
        if len(by_v) == 1:
            rows.append({"case type": defn, "versions": f"v{by_v.iloc[0]['version']:g} only",
                         "detail": f"n={int(by_v.iloc[0]['n'])}, rate {by_v.iloc[0]['rate']}%",
                         "verdict": "not yet updated", "prev_v": None, "cur_v": by_v.iloc[0]["version"]})
            continue
        prev, cur = by_v.iloc[-2], by_v.iloc[-1]
        delta = cur["rate"] - prev["rate"]
        low = min(prev["fail"], cur["fail"]) < min_failures_gate
        if delta > 0:
            verdict = "regressed (small sample, watch)" if low else "regressed (confirmed)"
        elif delta < 0:
            verdict = "improved (small sample)" if low else "improved"
        else:
            verdict = "no change"
        rows.append({"case type": defn, "versions": f"v{prev['version']:g} → v{cur['version']:g}",
                     "detail": f"{prev['rate']}% (n={int(prev['n'])}, {int(prev['fail'])} fail) → {cur['rate']}% (n={int(cur['n'])}, {int(cur['fail'])} fail)",
                     "verdict": verdict, "prev_v": prev["version"], "cur_v": cur["version"]})

    order = {"regressed (confirmed)": 0, "regressed (small sample, watch)": 1, "no change": 2,
             "improved (small sample)": 3, "improved": 4, "not yet updated": 5}
    res = pd.DataFrame(rows)
    if len(res):
        res["_s"] = res["verdict"].map(order)
        res = res.sort_values("_s").drop(columns="_s")
        res["action"] = res["verdict"].map(VERDICT_ACTIONS)
    return res


def render_flow_board(jid: str):
    """Visual, left-to-right board of every step a job went through: one colored
    card per event. Blue = automated, green = a human acted, red = the case is
    still open and stuck past its ceiling, amber = still open but not yet stuck."""
    hist = events[events["job_id"] == jid].sort_values("at").reset_index(drop=True)
    if hist.empty:
        st.info("No events found for this job.")
        return
    jrow = jobs[jobs["job_id"] == jid].iloc[0]
    is_still_open = jrow["state"] in open_states
    n = len(hist)

    if n > 12:
        st.caption(f"{n} steps — showing the board in two rows for readability.")
        rows_of_cols = [st.columns(6), st.columns(n - 6)]
        col_iter = [c for row in rows_of_cols for c in row]
    else:
        col_iter = st.columns(n)

    for i, (_, ev) in enumerate(hist.iterrows()):
        with col_iter[i]:
            is_human = str(ev["actor"]).startswith("user:")
            is_last = i == n - 1
            lag_txt = ""
            if i > 0:
                lag_h = (ev["at"] - hist.loc[i - 1, "at"]).total_seconds() / 3600
                lag_txt = f"\n\n⏳ +{lag_h:.1f}h after previous"
            body = (f"**Step {i+1} · `{ev['to_state']}`**\n\n"
                    f"{'🧑 human' if is_human else '🤖 automated'} — `{ev['actor']}`\n\n"
                    f"{ev['at'].strftime('%Y-%m-%d %H:%M')}\n\n"
                    f"_{ev['reason'] or 'no reason logged'}_" + lag_txt)
            if is_last and is_still_open:
                idle_h = (now - ev["at"]).total_seconds() / 3600
                ceil_h, _ = ceiling_for_state(jrow["state"])
                past = (not pd.isna(ceil_h)) and idle_h > ceil_h
                box = st.error if past else st.warning
                box(body + f"\n\n⏱ **idle {idle_h/24:.1f} days**" + (" — past normal ceiling" if past else ""))
            elif is_human:
                st.success(body)
            else:
                st.info(body)
    st.caption(f"Current status: `{jrow['state']}`" + (" (still open)" if is_still_open else " (finished)"))

    # Headline lag: first step -> the point execution actually started (not the
    # per-step lags already shown on each card). Matched by name rather than a
    # hardcoded state, so it still works if a differently-named export is loaded.
    exec_hits = hist[hist["to_state"].str.contains("execut", case=False, na=False)]
    first_at = hist["at"].iloc[0]
    if len(exec_hits):
        lag_h = (exec_hits["at"].iloc[0] - first_at).total_seconds() / 3600
        st.info(f"⏱ **First step to start of execution: {lag_h/24:.1f} days** ({lag_h:.0f} hours) — "
                f"everything that happened before the mechanical execution step itself.")
    else:
        st.caption(f"This case hasn't reached execution yet — currently at `{jrow['state']}` — "
                   f"so a first-step-to-execution lag isn't available.")


stuck_by_state = {s: not_done[(not_done["state"] == s) & (not_done["past_ceiling"] == True)]  # noqa: E712
                   for s in open_states if s in not_done["state"].values}

# ============================================================================
# VIEW: Overview — the big picture, computed live over the whole analysed window
# ============================================================================
if view == V_OVERVIEW:
    st.title("📊 Overview")
    st.caption("The big picture, computed live from whatever's loaded. Nothing here is a fixed number.")

    oldest = jobs["created_at"].min()
    x_days = max((data_end - oldest).days, 1)
    weeks = x_days / 7

    with st.container(border=True):
        st.markdown(f"#### 📅 The past {x_days} days, at a glance")
        st.caption("From the oldest case in job_id.csv to the most recent event.")

        n_closed = int(jobs["state"].isin(done_states).sum())
        n_clients_txt, n_clients_help = "—", "`subject` (client id) isn't available — load job_id.csv to see this."
        if have_subject:
            n_clients_txt = f"{int(jobs['subject'].dropna().nunique()):,}"
            n_clients_help = "Unique `subject` values in job_id.csv over the whole period."

        row1 = st.columns(4)
        row1[0].metric("Days looked at", x_days)
        row1[1].metric("Events logged", f"{len(events):,}", help="Every step, by a person or by the robot helper.")
        row1[2].metric("Jobs (cases)", f"{len(jobs):,}")
        row1[3].metric("Distinct clients treated", n_clients_txt, help=n_clients_help)

        row2 = st.columns(4)
        row2[0].metric("Events per job", f"{len(events) / len(jobs):.2f}" if len(jobs) else "—",
                        help="On average, how many steps a case goes through before it's done.")
        row2[1].metric("New jobs per week", f"{len(jobs) / weeks:.0f}")
        row2[2].metric("Jobs closed per week", f"{n_closed / weeks:.0f}", help=f"{n_closed:,} finished cases, spread over {weeks:.1f} weeks.")
        pct_completed = (n_closed / len(jobs) * 100) if len(jobs) else 0
        row2[3].metric("% of jobs completed", f"{pct_completed:.0f}%",
                        help=f"{n_closed:,} of {len(jobs):,} jobs have reached a finished state, success or failure.")

        # Success vs failure, using the same done_states/problem_states split as the
        # rest of the dashboard (configurable in ⚙️ Grown-up settings) — not a new rule.
        success_states = done_states - set(problem_states)
        failure_states = done_states & set(problem_states)
        n_success = int(jobs["state"].isin(success_states).sum())
        n_failure = int(jobs["state"].isin(failure_states).sum())
        pct_success = (n_success / len(jobs) * 100) if len(jobs) else 0
        pct_failure = (n_failure / len(jobs) * 100) if len(jobs) else 0

        row3 = st.columns(4)
        row3[0].metric("% completed, success only", f"{pct_success:.0f}%",
                        help=f"{n_success:,} jobs finished in a non-problem state ({', '.join(sorted(success_states)) or '—'}).")
        row3[1].metric("% completed, failure only", f"{pct_failure:.0f}%",
                        help=f"{n_failure:,} jobs finished in a 'problem' state ({', '.join(sorted(failure_states)) or '—'}), "
                             f"per the list set in ⚙️ Grown-up settings.")
        row3[2].metric("Open cases", f"{len(not_done):,}", help="Cases not yet in a finished state — same set as 📋 Cases waiting.")
        row3[3].metric("Avg age of open cases", f"{not_done['age_days'].mean():.1f}d" if len(not_done) else "—",
                        help="Average days since creation, for cases still open today.")

    jobs_wk = jobs.copy()
    jobs_wk["week"] = jobs_wk["created_at"].dt.isocalendar().week
    wk_new = jobs_wk.groupby("week").size().sort_index()
    half = max(len(wk_new) // 2, 1)
    new_first, new_second = wk_new.iloc[:half].mean(), wk_new.iloc[half:].mean()

    stuck_all = jobs[jobs["state"].isin(open_states)].copy()
    stuck_all["week"] = stuck_all["created_at"].dt.isocalendar().week
    wk_stuck = stuck_all.groupby("week").size().sort_index()
    halfs = max(len(wk_stuck) // 2, 1)
    stuck_first, stuck_second = wk_stuck.iloc[:halfs].mean(), wk_stuck.iloc[halfs:].mean()

    with st.container(border=True):
        st.markdown("#### 📉 Getting better or worse?")
        st.caption("First half of the period compared to the second half.")
        c7, c8 = st.columns(2)
        with c7:
            arrow = "📈 Yes" if new_second > new_first else ("📉 No" if new_second < new_first else "➡️ Flat")
            st.metric("New jobs, growing?", arrow, f"{new_first:.0f}/week → {new_second:.0f}/week", delta_color="off")
        with c8:
            arrow2 = "📈 Yes" if stuck_second > stuck_first else ("📉 No" if stuck_second < stuck_first else "➡️ Flat")
            st.metric("Stuck jobs, growing?", arrow2, f"{stuck_first:.0f}/week → {stuck_second:.0f}/week", delta_color="off",
                      help="Cases still open, grouped by the week they were created.")

    ue = events[events["actor"].astype(str).str.startswith("user:")]
    jobs_per_user_series = ue.groupby("actor")["job_id"].nunique()
    avg_per_user = jobs_per_user_series.mean() if len(jobs_per_user_series) else 0
    n_agents = events.loc[~events["actor"].astype(str).str.startswith("user:"), "actor"].nunique()

    with st.container(border=True):
        st.markdown("#### 🧑‍🤝‍🧑 The team behind it")
        st.caption("People, and the automated programs working alongside them.")
        c9, c10, c11 = st.columns(3)
        c9.metric("Jobs treated per user (avg)", f"{avg_per_user:.0f}")
        c10.metric("Users (the team)", len(reviewers))
        c11.metric("Agents (automated programs)", n_agents,
                   help="Every distinct automated actor: the robot helpers, the scheduler, the executor, and the intake feeds.")

# ============================================================================
# VIEW: Home — a plain-word guide to everything else
# ============================================================================
elif view == V_HOME:
    if LOGO_PATH:
        st.image(LOGO_PATH, width=64)
    st.title("👋 Welcome!")
    st.write(
        "This dashboard looks at everything our robot helper did — "
        f"**{len(jobs):,} cases**, over about **{span_days} days**. "
        "It finds the cases that got stuck. It finds the ones nobody wrote a reason for. "
        "It finds the ones where a change to the robot's instructions made things worse."
    )
    st.write("**The goal is simple: no problem should ever stay hidden. If something's wrong, we want to know before a client has to tell us.**")
    st.write("### 🧭 Click a page below, or pick one on the left. Here's what each one does:")

    # Each card is made of two layers: the container below holds the real,
    # fully-wrapped text (icon/title/description — nothing is ever cut off,
    # since none of it lives inside a button label). An invisible button is
    # placed on top of that exact same frame via CSS, so a click anywhere on
    # the card fires the navigation. This relies on Streamlit's internal DOM
    # markers (not part of its public API), so it could stop working on a
    # future Streamlit upgrade — the underlying navigation itself doesn't
    # depend on this trick and stays correct either way.
    home_cols = st.columns(3)
    card_css = []
    for i, v in enumerate([x for x in ALL_VIEWS if x not in (V_HOME, V_TEAM)]):
        icon, name, blurb = VIEW_BLURBS[v]
        marker = f"home-card-{i}"
        with home_cols[i % 3]:
            with st.container(border=True):
                st.markdown(f"<span class='{marker}' style='display:none'></span>", unsafe_allow_html=True)
                st.markdown(f"<div style='font-size:2.2rem;text-align:center'>{icon}</div>", unsafe_allow_html=True)
                st.markdown(f"**{name}**")
                st.write(blurb)
                st.button("→", key=f"go_{v}", on_click=_go_to, args=(v,), width="stretch")
        card_css.append(f"""
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.{marker}) {{
            position: relative; cursor: pointer;
            transition: box-shadow .15s ease;
        }}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.{marker}):hover {{
            box-shadow: 0 2px 12px rgba(0,0,0,0.18);
        }}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.{marker}) div[data-testid="stButton"] {{
            position: absolute; inset: 0; z-index: 5;
        }}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.{marker}) div[data-testid="stButton"] button {{
            width: 100%; height: 100%; cursor: pointer;
            background: transparent !important; border: none !important;
            box-shadow: none !important;
            display: flex; align-items: flex-end; justify-content: flex-end;
            padding: 0 0.9rem 0.7rem 0;
            font-size: 1.4rem; color: rgba(128,128,128,0.55);
        }}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.{marker}) div[data-testid="stButton"] button:hover {{
            color: rgba(59,130,246,0.9);
        }}
        """)
    st.markdown(f"<style>{''.join(card_css)}</style>", unsafe_allow_html=True)

    st.divider()
    st.write("### 🎨 What the colors mean, everywhere on this dashboard")
    cc1, cc2, cc3, cc4 = st.columns(4)
    with cc1:
        st.info("🔵 Blue\n\nA computer did this step")
    with cc2:
        st.success("🟢 Green\n\nA person did this, or it's all good")
    with cc3:
        st.warning("🟡 Amber\n\nStill waiting, but that's okay for now")
    with cc4:
        st.error("🔴 Red\n\nStuck, or something's wrong")

# ============================================================================
# VIEW: What to fix first (generated, not hardcoded)
# ============================================================================
elif view == V_FIX:
    st.title("🛠️ What to fix first")

    st.write("##### Why this page exists")
    st.markdown(
        "- **What we want:** know about a problem *before* a client has to tell us.\n"
        "- **Our approach:** look at how long things normally take, then flag anything far outside that. "
        "Not a guess, worked out from the real history every time.\n"
        "- **What we watch for:** cases stuck much longer than normal, cases nobody wrote a reason for, "
        "and cases sitting past their deadline."
    )
    # Reason-coverage stat, computed once here so both the summary section below
    # and the detailed box further down can use the same numbers without disagreeing.
    exec_states = [s for s in done_states if s not in problem_states]
    worst_state, worst_pct, worst_n, reason_others = None, None, None, ""
    if exec_states:
        cov = jobs[jobs["state"].isin(exec_states)].copy()
        cov["has_reason"] = has_real_reason(cov["last_reason"], generic_reasons)
        by_state = cov.groupby("state").agg(n=("job_id", "size"), pct_with_reason=("has_reason", "mean"))
        by_state["pct_with_reason"] = (by_state["pct_with_reason"] * 100).round(0)
        by_state_sorted = by_state.sort_values(["pct_with_reason", "n"], ascending=[True, False])
        worst_state = by_state_sorted.index[0]
        worst_pct = by_state_sorted.iloc[0]["pct_with_reason"]
        worst_n = int(by_state_sorted.iloc[0]["n"])
        reason_others = ", ".join(f"`{s}`={int(r.pct_with_reason)}%" for s, r in by_state.drop(worst_state).iterrows())

    past_sla_n = int(not_done["past_sla"].sum())
    total_stuck = sum(len(g) for g in stuck_by_state.values())
    n_problem_points = sum(1 for g in stuck_by_state.values() if len(g))
    sla_list = ", ".join(f"`{d}`={days}bd" for d, days in sla_map.items())

    st.write("##### The four decisions, right now")
    n_high_risk = int(not_done["high_risk"].sum())
    n_risk = int(jobs["definition"].isin(risk_defs).sum())
    risk_pct = (n_risk / len(jobs) * 100) if len(jobs) else 0
    risk_defs_txt = " or ".join(f"`{d}`" for d in risk_defs) if risk_defs else "(none flagged in ⚙️ Grown-up settings)"

    # Tier 2: risk cases that already finished, but in a "problem" outcome — same
    # done/problem split used everywhere else (⚙️ Grown-up settings), not a new rule.
    failure_states_d1 = done_states & set(problem_states)
    tier2_jobs = jobs[jobs["definition"].isin(risk_defs) & jobs["state"].isin(failure_states_d1)]
    n_tier2 = len(tier2_jobs)
    failure_states_txt = ", ".join(f"`{s}`" for s in sorted(failure_states_d1)) or "—"

    with st.container(border=True):
        st.markdown("**Decision 1 — Risk cases jump the queue**")
        st.markdown(f"🎯 **Trigger: {risk_defs_txt}**")
        st.markdown(f"**Tier 1, still open:** {n_high_risk} cases need attention right now. Same number, "
                    f"same cases, as the bold rows on **📋 Cases waiting**: either nobody's looked at them "
                    f"yet and they're already stuck, or the agent itself dropped them "
                    f"(`failed_analysis`/`awaiting_human`), seen or not.")
        st.markdown(f"**Tier 2, completed with failure:** {n_tier2} cases already finished in a problem "
                    f"state ({failure_states_txt}). Closed doesn't mean nothing to check.")
        st.caption(f"Out of {n_risk} risk cases ({risk_pct:.0f}% of all volume) overall. Full detail in the "
                   f"cards below; for a fast, no-detail glance, use **🚨 What's wrong right now** instead.")

    with st.container(border=True):
        st.markdown("**Decision 2 — Owner and deadline**")
        owner_lines = "; ".join(f"`{d}` → {owner_for(d, now)}" for d in definitions)
        st.markdown(f"**Who owns what, right now:** {owner_lines}. Computed from who already reviews the most "
                    f"of each case type; the highest-volume type rotates weekly instead of sitting with one person.")
        st.write(f"{past_sla_n} cases already past their deadline ({sla_list}). "
                 f"Full detail on **📋 Cases waiting**.")

    version_res = compute_version_verdicts(jobs, problem_states, min_failures_gate)
    confirmed = version_res[version_res["verdict"] == "regressed (confirmed)"] if len(version_res) else version_res
    n_regressed = len(confirmed)
    n_watch = int((version_res["verdict"] == "regressed (small sample, watch)").sum()) if len(version_res) else 0
    with st.container(border=True):
        st.markdown("**Decision 3 — Track version failures, then act: roll back or fix**")
        st.write(f"{n_regressed} case type(s) confirmed regressed, {n_watch} more flagged to watch "
                 f"(too few failures to be sure), out of {len(version_res)} tracked.")
        for _, r in confirmed.iterrows():
            st.markdown(f"🔴 **`{r['case type']}`:** roll back from v{r['cur_v']:g} to v{r['prev_v']:g}, "
                        f"or fix v{r['cur_v']:g}'s rules before it ships to more cases.")
        st.caption("Full picture on **🔄 Did the last change help?**")

    with st.container(border=True):
        st.markdown("**Decision 4 — A real reason at execution, not a boilerplate one**")
        if worst_state is not None:
            st.write(f"Only {worst_pct:.0f}% of {worst_n:,} `{worst_state}` cases have a reason on file — "
                     f"the majority of everything that actually reaches a client or partner, with zero "
                     f"record of why. Every failure gets a label; the riskiest, most consequential actions "
                     f"get nothing. In a regulated business, that's backwards. "
                     f"Full picture on **📝 Did we explain why?**")
        else:
            st.write("No finished cases to check yet.")

    # Real example, not hypothetical — only shows up if this specific case exists in
    # whatever's loaded, so it degrades gracefully (and silently) on other data.
    spotlight_id = "J00414"
    if spotlight_id in jobs["job_id"].values:
        srow = jobs[jobs["job_id"] == spotlight_id].iloc[0]
        idle_days = (now - srow["last_change_at"]).total_seconds() / 86400
        subj = srow["subject"] if have_subject and pd.notna(srow.get("subject")) else spotlight_id
        still_open = srow["state"] in open_states
        st.divider()
        st.write("##### A real example, not a hypothetical")
        st.markdown(
            f"- The brief doesn't name a client. This is a real match we found in the data.\n"
            f"- **Client {subj}** filed a `{srow['definition']}` case (`{spotlight_id}`).\n"
            f"- The robot helper couldn't decide, and sent it to a person (state: `{srow['state']}`).\n"
            f"- It's **{'still' if still_open else 'no longer'} sitting there**, {idle_days:.0f} days later.\n"
            f"- See its full story on **👤 Follow one client** or **🔍 Look up one case**."
        )
        if still_open:
            st.error(f"Client {subj}'s case is still untouched, {idle_days:.0f} days on.")

# ============================================================================
# VIEW 1 — Today's headline
# ============================================================================
elif view == V_TODAY:
    st.title("🚨 What's wrong right now")
    st.caption("The fast version: every stuck point in one glance, no explanations. For the full problem, the fix, "
               "and the exact cases behind each number, go to **🛠️ What to fix first**.")

    active = {s: g for s, g in stuck_by_state.items()}
    if not active:
        st.success("Nothing is currently past its computed ceiling.")
    else:
        ranked_active = sorted(
            active.items(),
            key=lambda kv: (-int(bool(kv[1]["high_risk"].any())), -len(kv[1])),
        )
        cols = st.columns(min(len(active), 4) or 1)
        for i, (s, g) in enumerate(ranked_active):
            ceil_h, ceil_n = ceil_cache[s]
            n_risk_here = int(g["high_risk"].sum())
            label = f"⚠️ Stuck in `{s}`" if n_risk_here else f"Stuck in `{s}`"
            with cols[i % len(cols)]:
                st.metric(label, len(g), help=f"Ceiling: {ceil_h:.1f}h (p{ceiling_pctl} of {ceil_n} clean cases)")
                if len(g):
                    st.caption(f"Oldest: {g['idle_hours'].max()/24:.1f} days idle" +
                               (f" · {n_risk_here} risk case(s)" if n_risk_here else ""))

    st.divider()
    st.subheader("Weekly trend for the largest stuck state")
    if active:
        biggest = max(active, key=lambda s: len(active[s]))
        trend = active[biggest].copy()
        trend["week"] = trend["created_at"].dt.isocalendar().week
        st.bar_chart(trend.groupby("week").size().rename(f"stuck `{biggest}` cases created that week"))

# ============================================================================
# VIEW 2 — Backlog
# ============================================================================
elif view == V_BACKLOG:
    st.title("📋 Cases waiting")
    st.caption(f"{len(not_done)} cases that aren't finished yet. "
               "Bold rows are high risk: a `compliance_file`/`withdrawal_hold` case that's either never been "
               "seen by a person and is already stuck, or one the agent itself gave up on "
               "(`failed_analysis`/`awaiting_human`), seen or not.")

    defs_opt = sorted(not_done["definition"].dropna().unique().tolist())
    states_opt = sorted(not_done["state"].dropna().unique().tolist())
    cf, cs = st.columns(2)
    f_def = cf.multiselect("Case type", defs_opt, placeholder="All case types")
    f_state = cs.multiselect("State", states_opt, placeholder="All states")

    vd = not_done.copy()
    if f_def:
        vd = vd[vd["definition"].isin(f_def)]
    if f_state:
        vd = vd[vd["state"].isin(f_state)]
    vd = vd.sort_values("idle_hours", ascending=False)

    disp = vd[["job_id", "definition", "state", "owner", "age_days", "idle_hours", "past_sla", "human_touched", "high_risk"]].copy()
    disp["age_days"], disp["idle_hours"] = disp["age_days"].round(1), disp["idle_hours"].round(1)
    disp = disp.rename(columns={"age_days": "age (days)", "idle_hours": "idle (hours)",
                                 "past_sla": "past SLA", "human_touched": "human-touched?", "high_risk": "high risk"})
    disp = disp.reset_index(drop=True)
    st.dataframe(bold_style(disp, disp["high risk"]), width="stretch", height=480)

    c1, c2, c3 = st.columns(3)
    c1.metric("Open cases (this filter)", len(vd))
    c2.metric("Past SLA", int(vd["past_sla"].sum()))
    c3.metric("High-risk (bold)", int(vd["high_risk"].sum()))

    st.divider()
    st.subheader("Weekly trend — created vs. closed")
    cw = jobs.copy()
    cw["week"] = cw["created_at"].dt.isocalendar().week
    dw = jobs[jobs["state"].isin(done_states)].copy()
    dw["week"] = dw["last_change_at"].dt.isocalendar().week
    st.line_chart(pd.DataFrame({"created": cw.groupby("week").size(), "closed": dw.groupby("week").size()}).fillna(0))

# ============================================================================
# VIEW 3 — Rationale coverage
# ============================================================================
elif view == V_REASON:
    st.title("📝 Did we explain why?")
    st.caption("For each finished outcome: does the record say why, in a case-specific way, or is it blank or "
                "just a generic placeholder? Generic text (⚙️ Grown-up settings) doesn't count as a real reason.")

    terminal = jobs[jobs["state"].isin(done_states)].copy()
    terminal["has_reason"] = has_real_reason(terminal["last_reason"], generic_reasons)

    # Headline first: the biggest bucket, picked the same way as Decision 4's
    # card (worst coverage, not just most cases), so the two can't disagree.
    by_state_r = terminal.groupby("state").agg(n=("job_id", "size"), pct=("has_reason", "mean")).reset_index()
    by_state_r["pct"] = (by_state_r["pct"] * 100).round(0)
    worst_row = by_state_r.sort_values(["pct", "n"], ascending=[True, False]).iloc[0] if len(by_state_r) else None

    if worst_row is not None:
        worst_state_r, worst_pct_r, worst_n_r = worst_row["state"], worst_row["pct"], int(worst_row["n"])
        st.metric(f"Worst outcome — `{worst_state_r}` — with a real, written reason",
                  f"{worst_pct_r:.0f}%", help=f"n = {worst_n_r} cases")
        if worst_pct_r < 50:
            st.error(f"**{worst_n_r} `{worst_state_r}` cases** end with no real explanation on file — blank, "
                     f"or just a generic placeholder. That's the biggest gap in the record.")

    st.divider()
    st.markdown("##### By outcome and case type, worst first")
    pivot = (terminal.groupby(["state", "definition"])["has_reason"].agg(["mean", "count"]).reset_index())
    pivot["mean"] = (pivot["mean"] * 100).round(0)
    pivot = pivot.rename(columns={"state": "outcome", "definition": "case type", "mean": "% with a real reason", "count": "n"})
    pivot = pivot.sort_values(["% with a real reason", "n"], ascending=[True, False]).reset_index(drop=True)
    st.dataframe(bold_style(pivot, pivot["% with a real reason"] < 50), width="stretch", hide_index=True)

    if worst_row is not None and worst_n_r:
        st.divider()
        missing = terminal[(terminal["state"] == worst_state_r) & (~terminal["has_reason"])].copy()
        st.markdown(f"##### The {len(missing)} `{worst_state_r}` cases with no real reason on file")
        st.caption("What's actually in the record for each one — blank, or the generic text that doesn't count.")
        missing["last_reason"] = missing["last_reason"].fillna("").str.strip().replace("", "(blank)")
        cols = ["job_id"] + (["subject"] if have_subject else []) + ["definition", "last_reason"]
        missing_disp = missing[cols].rename(columns={"definition": "case type", "last_reason": "what's on file"})
        st.dataframe(missing_disp.reset_index(drop=True), width="stretch", hide_index=True, height=320)

# ============================================================================
# VIEW 4 — Version watch
# ============================================================================
elif view == V_VERSION:
    st.title("🔄 Did the last change help?")
    st.caption(f"A version doesn't get trusted until its failure rate is compared against its predecessor "
               f"with at least {min_failures_gate} observed failures on each side.")

    res = compute_version_verdicts(jobs, problem_states, min_failures_gate)
    if len(res):
        icons = {"regressed (confirmed)": "🔴", "regressed (small sample, watch)": "🟠", "no change": "⚪",
                 "improved (small sample)": "🟡", "improved": "🟢", "not yet updated": "⚪"}
        for _, r in res.iterrows():
            with st.container(border=True):
                st.markdown(f"### {icons.get(r['verdict'],'⚪')} `{r['case type']}` — {r['versions']}")
                st.write(r["detail"])
                st.markdown(f"**Verdict:** {r['verdict']}  \n**Action:** {r['action']}")
    else:
        st.caption("No `version` field found on any case.")

# ============================================================================
# VIEW 5 — Review speed
# ============================================================================
elif view == V_SPEED:
    st.title("⏱️ How fast do we check things?")
    st.caption("Median vs. the tail — p90 and worst case are where client complaints start.")

    rv = jobs.dropna(subset=["reviewed_at", "created_at"]).copy()
    rv["latency_h"] = (rv["reviewed_at"] - rv["created_at"]).dt.total_seconds() / 3600
    if len(rv):
        st.subheader("By case type")
        by_def = rv.groupby("definition")["latency_h"].agg(median="median", p90=lambda s: s.quantile(0.9), worst="max", n="count").round(1)
        st.dataframe(by_def, width="stretch")

        st.subheader("By weekday the case was created")
        rv["weekday"] = rv["created_at"].dt.day_name()
        order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        st.bar_chart(rv.groupby("weekday")["latency_h"].median().reindex(order))
    else:
        st.caption("No reviewed cases found in this data.")

# ============================================================================
# VIEW 6 — Case lookup
# ============================================================================
elif view == V_CASE:
    st.title("🔍 Look up one case")
    st.caption("Any `job_id` (or `subject`, if job_id.csv was loaded).")

    if len(not_done[not_done["high_risk"]]):
        default = not_done.loc[not_done["high_risk"], "idle_hours"].idxmax()
        default = not_done.loc[default, "job_id"]
    elif len(not_done):
        default = not_done.loc[not_done["idle_hours"].idxmax(), "job_id"]
    else:
        default = jobs["job_id"].iloc[0]

    query = st.text_input("job_id or subject", value=default)
    matches = jobs[jobs["job_id"] == query]
    if matches.empty and have_subject:
        matches = jobs[jobs["subject"] == query]

    if matches.empty:
        st.warning("No case found with that id.")
    else:
        for _, row in matches.iterrows():
            jid = row["job_id"]
            hist = events[events["job_id"] == jid].sort_values("at").reset_index(drop=True)

            is_risky = jid not in htouched and row.get("definition") in risk_defs and row["state"] in open_states
            if is_risky:
                st.error(f"🔴 **HIGH RISK** — `{jid}` ({row['definition']}), never seen by a human, "
                         f"currently `{row['state']}`, idle since {row['last_change_at']}.")

            st.subheader(f"`{jid}` — {row.get('definition', '?')} · currently `{row['state']}`")
            hist["actor_kind"] = np.where(hist["actor"].astype(str).str.startswith("user:"), "🧑 human", "🤖 automated")
            hist["lag_str"] = hist["at"].diff().apply(lambda d: "—" if pd.isna(d) else f"{d.total_seconds()/3600:.1f}h later")
            for _, ev_row in hist.iterrows():
                st.markdown(f"**{ev_row['at']}** &nbsp;·&nbsp; {ev_row['actor_kind']} `{ev_row['actor']}` &nbsp;·&nbsp; "
                            f"`{ev_row['from_state'] or '—'}` → `{ev_row['to_state']}` &nbsp;·&nbsp; "
                            f"_{ev_row['reason'] or 'no reason logged'}_ &nbsp;·&nbsp; ({ev_row['lag_str']})")
            idle_h = (now - row["last_change_at"]).total_seconds() / 3600
            st.caption(f"Idle for {idle_h/24:.1f} days since last event ({row['last_change_at']}).")
            st.divider()

# ============================================================================
# VIEW 7 — Client lookup
# ============================================================================
elif view == V_CLIENT:
    st.title("👤 Follow one client")
    if not have_subject:
        st.warning("`subject` (client id) isn't available — load `job_id.csv` to use this view.")
    else:
        st.caption("Pick a client, see their job(s), and the full visual flow of events for the one you pick.")

        subs = sorted(jobs["subject"].dropna().unique().tolist())
        counts_all = jobs.dropna(subset=["subject"]).groupby("subject").size().sort_values(ascending=False)
        multi_all = counts_all[counts_all > 1]
        default_sub = "C618763" if "C618763" in subs else (multi_all.index[0] if len(multi_all) else (subs[0] if subs else None))

        if default_sub is None:
            st.info("No clients found in this data.")
        else:
            sel_client = st.selectbox("Client", subs, index=subs.index(default_sub))
            client_jobs = jobs[jobs["subject"] == sel_client].sort_values("created_at")

            if len(client_jobs) > 1:
                job_ids = client_jobs["job_id"].tolist()
                labels = {jid: f"{jid} — {client_jobs.loc[client_jobs['job_id'] == jid, 'definition'].iloc[0]} "
                               f"(`{client_jobs.loc[client_jobs['job_id'] == jid, 'state'].iloc[0]}`)"
                          for jid in job_ids}
                st.caption(f"This client has **{len(job_ids)} jobs** — pick one below.")
                sel_job = st.selectbox("Job", job_ids, format_func=lambda j: labels[j])
            else:
                sel_job = client_jobs["job_id"].iloc[0]
                st.caption(f"This client has one job: `{sel_job}`.")

            st.divider()
            render_flow_board(sel_job)

        st.divider()
        st.subheader("All clients with more than one case")
        st.caption("Repeats of the *same* case type are worth a second look.")
        counts = jobs.dropna(subset=["subject"]).groupby("subject").size().sort_values(ascending=False)
        multi = counts[counts > 1]
        st.metric("Clients with more than one case", len(multi))
        if len(multi):
            rows = []
            for subj in multi.index:
                g = jobs[jobs["subject"] == subj].sort_values("created_at")
                defs = g["definition"].tolist()
                rows.append({"client": subj, "cases": len(g), "case types": ", ".join(defs),
                             "same issue twice?": "⚠️ yes" if len(set(defs)) < len(defs) else "no",
                             "job_ids": ", ".join(g["job_id"].tolist())})
            res = pd.DataFrame(rows).sort_values("same issue twice?", ascending=False).reset_index(drop=True)
            st.dataframe(bold_style(res, res["same issue twice?"].str.contains("yes")), width="stretch", hide_index=True)
        else:
            st.caption("No repeat clients in this data.")

# ============================================================================
# VIEW — One team member, their numbers and their queue
# ============================================================================
elif view == V_TEAM:
    st.title("🧑‍💼 Check one team member")
    st.caption("Pick someone on the team. Their track record, then exactly what's on their plate today.")

    if not reviewers:
        st.caption("No team members found — no `user:` actors in events.csv.")
    else:
        person = st.selectbox("Team member", reviewers)
        person_tag = f"user:{person}"

        def _owner_plain(d):
            return owner_for(d, now).split(" (")[0]

        # Track record: cases this person personally reviewed, not case-type
        # ownership — "closed the most" means what they've actually handled.
        reviewed = jobs[jobs["reviewer"] == person_tag]
        closed = reviewed[reviewed["state"].isin(done_states)]
        success_states_p = done_states - set(problem_states)
        success_rate = (closed["state"].isin(success_states_p).mean() * 100) if len(closed) else None

        # Specialty: same "who reviews this case type the most" computation
        # behind owner_for (Decision 2) — not raw review counts, which just
        # tracks whoever handles the highest-volume case type. The rotating
        # type (`rotating_def`, today `alert_triage`) is left out on purpose:
        # everyone takes a turn on it, so it's shared work, not a specialty.
        owned_defs = [d for d in sorted(jobs["definition"].dropna().unique())
                      if d != rotating_def and _owner_plain(d) == person]
        specialty_txt = ", ".join(f"`{d}`" for d in owned_defs) if owned_defs else "—"

        # Backlog: same case-type ownership as Decision 2 / 📋 Cases waiting —
        # "attributed to them" means their queue going forward, not history.
        backlog_here = not_done[not_done["definition"].map(_owner_plain) == person]

        failure_states_p = done_states & set(problem_states)
        tier2_here = jobs[(jobs["definition"].map(_owner_plain) == person) &
                           jobs["definition"].isin(risk_defs) & jobs["state"].isin(failure_states_p)]
        tier1_here = backlog_here[backlog_here["high_risk"]]
        rest_here = backlog_here[~backlog_here["high_risk"]]

        st.caption(f"Specialty: {specialty_txt}" if specialty_txt != "—" else
                    "Specialty: — (doesn't currently own a case type outright)")

        # The same four numbers MISSION_2.md's Rhythm section names for the
        # daily ten-minute check, scoped to this person's owned case type(s).
        n_risk_here = len(tier1_here) + len(tier2_here)
        backlog_age = backlog_here["age_days"].mean() if len(backlog_here) else None
        n_stuck_here = int(backlog_here["past_ceiling"].sum()) if len(backlog_here) else 0
        closed_owned = jobs[(jobs["definition"].map(_owner_plain) == person) & jobs["state"].isin(done_states)]
        reason_pct = (has_real_reason(closed_owned["last_reason"], generic_reasons).mean() * 100) if len(closed_owned) else None

        st.markdown("##### Today's ten-minute check — the same four numbers, every day")
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Risk cases", n_risk_here, help="Tier 1 (still open) + Tier 2 (completed with failure) — Decision 1's definitions.")
        d2.metric("Backlog age", f"{backlog_age:.1f}d" if backlog_age is not None else "—",
                   help="Average age of their open cases, in days.")
        d3.metric("Stuck past normal", n_stuck_here,
                   help="Open cases slower than the ceiling for their state (⚙️ Grown-up settings — p90 by default).")
        d4.metric("Reason coverage", f"{reason_pct:.0f}%" if reason_pct is not None else "—",
                   help=f"n = {len(closed_owned)} of their case type's finished cases with a real, non-generic reason on file.")

        st.divider()
        c1, c2 = st.columns(2)
        c1.metric("Success rate, cases they've closed", f"{success_rate:.0f}%" if success_rate is not None else "—",
                   help=f"n = {len(closed)} of their reviewed cases that reached a finished state "
                        f"({', '.join(sorted(success_states_p)) or '—'} = success).")
        c2.metric("Backlog attributed to them", len(backlog_here),
                   help="Open cases whose case type they own right now — same ownership rule as Decision 2. "
                        "Doesn't include Tier 2, since those are already closed.")

        st.divider()
        st.markdown("##### Their queue, worst first — Tier 1, then Tier 2, then the rest")
        st.caption("Same Tier 1/Tier 2 definitions as Decision 1: Tier 1 is still open and already stuck or dropped; "
                    "Tier 2 is a risk case that finished in a problem state, already closed so it's not in the "
                    "backlog count above, but still worth a look.")

        open_cols = ["job_id"] + (["subject"] if have_subject else []) + ["definition", "state", "age_days", "idle_hours"]
        done_cols = ["job_id"] + (["subject"] if have_subject else []) + ["definition", "state"]

        parts = []
        for df_part, cols, label in [(tier1_here, open_cols, "Tier 1 — still open"),
                                      (tier2_here, done_cols, "Tier 2 — completed with failure"),
                                      (rest_here, open_cols, "Rest of backlog")]:
            if len(df_part):
                t = df_part[cols].copy()
                if "age_days" in t:
                    t["age_days"] = t["age_days"].round(1)
                if "idle_hours" in t:
                    t["idle_hours"] = t["idle_hours"].round(1)
                t.insert(0, "queue", label)
                parts.append(t)

        if parts:
            combined = pd.concat(parts, ignore_index=True, sort=False)
            st.dataframe(bold_style(combined, combined["queue"] == "Tier 1 — still open"),
                         width="stretch", hide_index=True, height=420)
        else:
            st.success("Nothing attributed to them right now — a clean queue.")


