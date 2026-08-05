"""
Mock Interview pool — atomic blocks and the three-stage escalation chain.

This module is the code equivalent of the "MI Details New" sheet:

    Date | Trainer | Batch | Sub Module | Start | End | Assigned to |
    Status | AE Status | Taken by Faculty | Remarks

and in particular of the cascade buried in those last four columns:

    Stage 1  Extended AE   Status = Accepted / Rejected
    Stage 2  Core AE       AE Status = "Taken by <core AE>"
    Stage 3  Faculty       Taken by Faculty = Yes

A session nobody picks up falls one rung at a time until a trainer holds it.

Two rules matter more than anything else here:

  * A Mock Interview block is ATOMIC. CMIS stores a two-hour MI as four
    consecutive 30-minute rows; the sheet stores it as one row with
    Start 16:00 and End 18:00, assigned to exactly one person. We merge back
    to the sheet's shape before anything is allocated, so a single MI is
    never split across two people.

  * Every stage sees the stage above it. A Core AE opening this tab can see
    what the Extended AEs have and haven't taken — that visibility is the
    whole point of an escalation ladder.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import text

import db

MI_POOL_TABLE = "mi_pool_claim"

# Stage labels, in ladder order.
STAGE_EXT = "Extended AE"
STAGE_CORE = "Core AE"
STAGE_FACULTY = "Faculty"

STATE_OPEN = "Open"
STATE_CLAIMED = "Claimed"


# ---------------------------------------------------------------------------
# Block merging — the "don't split a 1-hour MI across two people" rule
# ---------------------------------------------------------------------------
def _slot_start_end(slot: str) -> tuple[str, str]:
    """('11:00 AM - 11:30 AM') -> ('11:00 AM', '11:30 AM')."""
    s = str(slot or "")
    if "-" in s:
        a, b = s.split("-", 1)
        return a.strip(), b.strip()
    return s.strip(), s.strip()


def _to_minutes(t: str) -> int:
    """'11:00 AM' -> 660. Returns a large sentinel when unparseable so bad
    rows sort to the end instead of silently merging with something else."""
    if not t:
        return 10 ** 6
    ts = pd.to_datetime(str(t).strip(), format="%I:%M %p", errors="coerce")
    if pd.isna(ts):
        ts = pd.to_datetime(str(t).strip(), errors="coerce")
    if pd.isna(ts):
        return 10 ** 6
    return int(ts.hour) * 60 + int(ts.minute)


def merge_mi_blocks(cmis_rows: pd.DataFrame) -> list[dict]:
    """Collapse consecutive 30-minute CMIS Mock Interview rows into whole
    sessions — one dict per real interview.

    Rows chain into the same block when the trainer, date, batch and module
    all match AND the previous row's end time is this row's start time. That
    contiguity check is what stops two genuinely separate interviews for the
    same batch on the same day (say 10:00-11:00 and 15:00-16:00) from being
    glued into one four-hour phantom.

    Each block carries `member_slots`: the original 30-minute strings it was
    built from. Claims fan back out across those, so the underlying tables
    end up identical to what claiming each slot by hand would have written —
    the merge is a presentation and allocation concern, not a storage one.
    """
    if cmis_rows is None or cmis_rows.empty:
        return []

    d = cmis_rows.copy()
    d["_date"] = pd.to_datetime(d["s_date"]).dt.date
    d[["_start", "_end"]] = d["slot_time"].apply(
        lambda s: pd.Series(_slot_start_end(s))
    )
    d["_start_min"] = d["_start"].map(_to_minutes)
    d = d.sort_values(
        ["email_id", "_date", "batch_code", "c_alias", "_start_min"], kind="stable"
    )

    blocks: list[dict] = []
    run: list[dict] = []

    def flush() -> None:
        if not run:
            return
        first, last = run[0], run[-1]
        span = (
            f"{first['_start']} - {last['_end']}"
            if len(run) > 1
            else str(first["slot_time"])
        )
        start_min = first["_start_min"]
        end_min = _to_minutes(last["_end"])
        dur = end_min - start_min if end_min > start_min else 30 * len(run)
        bd = first["_date"]
        batch = first.get("batch_code") or ""
        trainer = f"{first.get('f_name') or ''} {first.get('l_name') or ''}".strip()
        blocks.append({
            "mi_key": f"{bd}|{span}|{batch}",
            "date": bd,
            "slot_time": span,
            "member_slots": [str(r["slot_time"]) for r in run],
            "start_min": start_min,
            "duration_minutes": int(dur),
            "batch_code": first.get("batch_code"),
            "c_alias": first.get("c_alias"),
            "trainer_email": first.get("email_id"),
            "trainer_name": trainer,
           "program_name": first.get("program_name"),
            "class_link": first.get("class_link"),
            "slot_count": len(run),
        })

    prev: dict | None = None
    for _, row in d.iterrows():
        r = row.to_dict()
        if prev is not None:
            same_class = (
                r["email_id"] == prev["email_id"]
                and r["_date"] == prev["_date"]
                and (r.get("batch_code") or "") == (prev.get("batch_code") or "")
                and (r.get("c_alias") or "") == (prev.get("c_alias") or "")
            )
            if not (same_class and prev["_end"] == r["_start"]):
                flush()
                run = []
        run.append(r)
        prev = r
    flush()

    blocks.sort(key=lambda b: (b["date"], b["start_min"], b["trainer_name"]))
    return blocks


@st.cache_data(ttl=300, show_spinner=False)
def get_mi_blocks(from_date: date, to_date: date) -> list[dict]:
    """Every Mock Interview in range as whole, unsplit blocks."""
    return merge_mi_blocks(db.get_all_mock_interview_sessions(from_date, to_date))


# ---------------------------------------------------------------------------
# Stage claims (Core AE + Faculty rungs)
# ---------------------------------------------------------------------------
_POOL_COLS = [
    "id", "mi_key", "claim_role", "claimed_by_email", "session_date", "slot_time",
    "member_slots", "batch_code", "c_alias", "trainer_email", "trainer_name",
    "program_name", "duration_minutes", "status", "remarks", "claimed_on",
    "updated_on",
]


@st.cache_data(ttl=60, show_spinner=False)
def get_pool_claims(from_date: date, to_date: date) -> pd.DataFrame:
    """All Core AE / Faculty stage rows in range.

    A missing table is treated as an empty result rather than an exception:
    the Sessions tab shouldn't die because create_mi_pool.sql hasn't been run
    on this environment yet.
    """
    sql = text(
        f"""
        SELECT {', '.join(_POOL_COLS)}
        FROM {MI_POOL_TABLE}
        WHERE session_date BETWEEN :a AND :b
        """
    )
    try:
        with db.app_engine().connect() as conn:
            return pd.read_sql(sql, conn, params={"a": from_date, "b": to_date})
    except Exception:
        return pd.DataFrame(columns=_POOL_COLS)


def upsert_pool_claim(
    block: dict,
    claim_role: str,
    claimed_by_email: str,
    status: str = "Selected",
    remarks: str | None = None,
) -> None:
    """Record (or update) one stage claim for a whole MI block.

    Keyed on (mi_key, claim_role), so a person changing their mind is an
    update and re-running anything is idempotent.
    """
    members = block.get("member_slots") or []
    payload = {
        "k": block["mi_key"],
        "cr": claim_role,
        "by": claimed_by_email,
        "d": block["date"],
        "st": block["slot_time"],
        "ms": "|".join(str(m) for m in members),
        "bc": block.get("batch_code"),
        "ca": block.get("c_alias"),
        "te": block.get("trainer_email"),
        "tn": block.get("trainer_name"),
        "pn": block.get("program_name"),
        "dm": block.get("duration_minutes"),
        "status": status,
        "rem": remarks,
    }
    with db.app_engine().begin() as conn:
        conn.execute(
            text(
                f"""
                INSERT INTO {MI_POOL_TABLE}
                    (mi_key, claim_role, claimed_by_email, session_date, slot_time,
                     member_slots, batch_code, c_alias, trainer_email, trainer_name,
                     program_name, duration_minutes, status, remarks)
                VALUES
                    (:k, :cr, :by, :d, :st, :ms, :bc, :ca, :te, :tn, :pn, :dm,
                     :status, :rem)
                ON DUPLICATE KEY UPDATE
                    claimed_by_email = VALUES(claimed_by_email),
                    member_slots     = VALUES(member_slots),
                    trainer_email    = VALUES(trainer_email),
                    trainer_name     = VALUES(trainer_name),
                    program_name     = VALUES(program_name),
                    duration_minutes = VALUES(duration_minutes),
                    status           = VALUES(status),
                    remarks          = VALUES(remarks),
                    updated_on       = NOW()
                """
            ),
            payload,
        )


def release_pool_claim(mi_key: str, claim_role: str) -> None:
    """Drop a stage claim entirely, putting the block back where it was."""
    try:
        with db.app_engine().begin() as conn:
            conn.execute(
                text(
                    f"DELETE FROM {MI_POOL_TABLE} "
                    f"WHERE mi_key = :k AND claim_role = :cr"
                ),
                {"k": mi_key, "cr": claim_role},
            )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# The ladder itself
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def build_pool(from_date: date, to_date: date) -> pd.DataFrame:
    """One row per Mock Interview block, with its position on the ladder.

    Columns added on top of the block fields:

        ext_ae, ext_status        stage 1 (mock_interview_assignment)
        core_ae, core_status      stage 2 (mi_pool_claim, core_ae)
        faculty, faculty_status   stage 3 (mi_pool_claim, faculty)
        stage                     where it currently sits
        state                     Open | Claimed
        holder                    whoever holds it, '' when open
    """
    blocks = get_mi_blocks(from_date, to_date)
    if not blocks:
        return pd.DataFrame()

   # Stage 1 — Extended AE assignments. A saved assignment may cover only
    # PART of a merged pool block (e.g. the block is 12:30-02:30 but only the
    # 12:30-01:00 slice was free to pick, so that's what got saved). Matching
    # on the exact span string therefore misses those, which is why some
    # decided MIs showed "—" here. Instead we key each assignment by every
    # 30-minute sub-slot it spans, on (date, batch, sub-slot), and a block
    # matches if ANY of its member_slots has an assignment.
    ext_by_subslot: dict[str, dict] = {}
    ext = db.get_mock_interview_assignments(None, from_date, to_date)
    if not ext.empty:
        for _, r in ext.iterrows():
            d = pd.to_datetime(r["session_date"]).date()
            batch = r["batch_code"] or ""
            s0, e0 = _slot_start_end(str(r["slot_time"]))
            m0, m1 = _to_minutes(s0), _to_minutes(e0)
            if m1 <= m0:
                m1 = m0 + 30
            # one entry per 30-min sub-slot the assignment covers
            for t in range(m0, m1, 30):
                sk = f"{d}|{batch}|{t}"
                cur = ext_by_subslot.get(sk)
                # A 'Selected' row always wins over a 'Not Selected' one, so a
                # block someone actually took never looks abandoned just
                # because a second, stale row exists for it.
                if cur is None or (str(r["status"]) == "Selected"):
                    ext_by_subslot[sk] = {
                        "ae": r["extended_ae_email"], "status": str(r["status"]),
                        "source": str(r.get("source") or ""),
                        "remarks": r.get("remarks"),
                    }
    # Stages 2 and 3.
    claims = get_pool_claims(from_date, to_date)
    core_by_key: dict[str, dict] = {}
    fac_by_key: dict[str, dict] = {}
    if not claims.empty:
        for _, r in claims.iterrows():
            bucket = core_by_key if r["claim_role"] == "core_ae" else fac_by_key
            bucket[r["mi_key"]] = {
                "by": r["claimed_by_email"], "status": str(r["status"]),
                "remarks": r.get("remarks"),
            }

    rows: list[dict] = []
    for b in blocks:
        k = b["mi_key"]
        c = core_by_key.get(k, {})
        f = fac_by_key.get(k, {})

        # Find the Extended AE assignment by ANY sub-slot this block covers.
        # A 'Selected' sub-slot wins over a 'Not Selected' one.
        e = {}
        _bd = b["date"]
        _batch = b.get("batch_code") or ""
        for _ms in b.get("member_slots", [b["slot_time"]]):
            _s0, _e0 = _slot_start_end(str(_ms))
            _m0, _m1 = _to_minutes(_s0), _to_minutes(_e0)
            if _m1 <= _m0:
                _m1 = _m0 + 30
            for _t in range(_m0, _m1, 30):
                _hit = ext_by_subslot.get(f"{_bd}|{_batch}|{_t}")
                if _hit and (not e or _hit.get("status") == "Selected"):
                    e = _hit

        ext_status = e.get("status", "")
        core_status = c.get("status", "")
        fac_status = f.get("status", "")

        # Walk the ladder from the bottom rung up: whoever most recently
        # accepted holds it; otherwise it sits open at the rung just below
        # the last person who passed.
        #
        # "Rejected" is treated exactly like "Not Selected" here -- both mean
        # that rung's person isn't taking it, so the interview opens to the
        # next rung down. The two labels differ only in the audit trail
        # (declined-from-start vs. took-then-dropped); the cascade behaviour
        # is identical.
        _ext_declined = ext_status in ("Not Selected", "Rejected")
        _core_declined = core_status in ("Not Selected", "Rejected")
        if fac_status == "Selected":
            stage, state, holder = STAGE_FACULTY, STATE_CLAIMED, f.get("by", "")
        elif core_status == "Selected":
            stage, state, holder = STAGE_CORE, STATE_CLAIMED, c.get("by", "")
        elif ext_status == "Selected":
            stage, state, holder = STAGE_EXT, STATE_CLAIMED, e.get("ae", "")
        elif _core_declined:
            stage, state, holder = STAGE_FACULTY, STATE_OPEN, ""
        elif _ext_declined:
            stage, state, holder = STAGE_CORE, STATE_OPEN, ""
        else:
            stage, state, holder = STAGE_EXT, STATE_OPEN, ""

        rows.append({
            **b,
            "ext_ae": e.get("ae", ""),
            "ext_status": ext_status,
            "ext_source": e.get("source", ""),
            "core_ae": c.get("by", ""),
            "core_status": core_status,
            "faculty": f.get("by", ""),
            "faculty_status": fac_status,
            "remarks": c.get("remarks") or f.get("remarks") or e.get("remarks") or "",
            "stage": stage,
            "state": state,
            "holder": holder,
        })

    return pd.DataFrame(rows)


def clear_pool_caches() -> None:
    """Invalidate only what a pool write can possibly have changed."""
    for fn in (get_pool_claims, get_mi_blocks, build_pool):
        try:
            fn.clear()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
_SHOW_OPTIONS = [
    "Everything",
    "Open — needs someone",
    "Open @ Extended AE",
    "Open @ Core AE",
    "Open @ Faculty",
    "Extended AE claimed sessions",
    "Core AE claimed sessions",
    "Handed to faculty",
    "Mine",
]


def _apply_show_filter(df: pd.DataFrame, show: str, email: str) -> pd.DataFrame:
    if df.empty or show == "Everything":
        return df
    me = (email or "").lower()
    if show == "Open — needs someone":
        return df[df["state"] == STATE_OPEN]
    if show == "Open @ Extended AE":
        return df[(df["state"] == STATE_OPEN) & (df["stage"] == STAGE_EXT)]
    if show == "Open @ Core AE":
        return df[(df["state"] == STATE_OPEN) & (df["stage"] == STAGE_CORE)]
    if show == "Open @ Faculty":
        return df[(df["state"] == STATE_OPEN) & (df["stage"] == STAGE_FACULTY)]
    if show == "Extended AE claimed sessions":
        return df[df["ext_status"] == "Selected"]
    if show == "Core AE claimed sessions":
        return df[df["core_status"] == "Selected"]
    if show == "Handed to faculty":
        return df[df["faculty_status"] == "Selected"]
    if show == "Mine":
        return df[df["holder"].str.lower() == me]
    return df

# ---------------------------------------------------------------------------
# Card rendering
#
# Deliberately the SAME visual language as the Sessions tab (.slot-head,
# .scard, .pill). The earlier st.data_editor grid was replaced because it
# had three problems at once: thirteen columns squeezed past the right edge
# and collided with Streamlit's own toolbar, most of those columns were "—"
# for a freshly-loaded pool, and the canvas grid ignores the app's CSS theme
# so it rendered dark inside a light page.
# ---------------------------------------------------------------------------
_STAGE_PILL = {
    STAGE_EXT: ("pill-avail", "Extended AE"),
    STAGE_CORE: ("pill-lock", "Core AE"),
    STAGE_FACULTY: ("pill-mine", "Faculty"),
}


def _who(email: str) -> str:
    """'pulak@anudip.org' -> 'pulak' — full addresses make the cards noisy."""
    return str(email or "").split("@")[0]


def _card_html(b: dict, me: str) -> str:
    """One Mock Interview as a session card."""
    day = pd.to_datetime(b["date"]).strftime("%a, %d %b")
    mins = int(b.get("duration_minutes") or 0)
    dur = f"{mins // 60}h {mins % 60:02d}m" if mins else ""

    holder = str(b.get("holder") or "")
    is_open = b["state"] == STATE_OPEN
    if is_open:
        tone = "scard-avail"
        who = "<span class='pill pill-avail'>◷ Open</span>"
    elif holder.lower() == me:
        tone = "scard-mine"
        who = "<span class='pill pill-mine'>★ Yours</span>"
    else:
        tone = "scard-lock"
        who = f"<span class='pill pill-lock'>🔒 {_who(holder)}</span>"

    pill_cls, pill_txt = _STAGE_PILL.get(b["stage"], ("pill-avail", b["stage"]))
    stage = f"<span class='pill {pill_cls}'>{pill_txt}</span>"

    bits = [x for x in (dur, f"<b>{b.get('batch_code') or ''}</b>",
                        b.get("c_alias") or "", b.get("program_name") or "") if x]

    # Only show a rung once someone has actually acted on it — a wall of
    # em-dashes was most of what made the old grid unreadable.
    trail = []
    if b.get("ext_status"):
        mark = "✓" if b["ext_status"] == "Selected" else "✗"
        trail.append(f"{mark} Ext: {_who(b['ext_ae'])}")
    if b.get("core_status"):
        mark = "✓" if b["core_status"] == "Selected" else "✗"
        trail.append(f"{mark} Core: {_who(b['core_ae'])}")
    if b.get("faculty_status"):
        trail.append(f"✓ Faculty: {_who(b['faculty'])}")
    trail_html = (
        f"<div class='scard-sub' style='opacity:.8'>{' &nbsp;·&nbsp; '.join(trail)}</div>"
        if trail else ""
    )

    return (
        f"<div class='scard {tone}'>"
        f"<div class='scard-top'>🕑 {day} &nbsp;·&nbsp; {b['slot_time']} {stage} {who}</div>"
        f"<div class='scard-sub'>{' &nbsp;·&nbsp; '.join(bits)}</div>"
        f"{trail_html}</div>"
    )


# ---------------------------------------------------------------------------
# Spreadsheet-style rendering
#
# Reproduces the "MI Details New" sheet the team already works from, column
# for column:
#
#   Date | Day | Trainer Name | Batch Code | Sub Module | Class Link |
#   Start Time | End Time | Assigned to | Status | AE Status |
#   Taken by Faculty | Remarks
#
# The three status columns map straight onto the escalation ladder this
# module already models:
#   Status            stage 1, the assigned Extended AE  -> Accepted/Rejected
#   AE Status         stage 2, a Core AE                 -> "Taken by <name>"
#   Taken by Faculty  stage 3, the trainer               -> Yes/No
# ---------------------------------------------------------------------------
def _esc(v) -> str:
    """Minimal HTML escape -- these values come from CMIS/user input and go
    straight into an st.markdown(unsafe_allow_html=True) table."""
    s = "" if v is None else str(v)
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def _status_cell(block: dict) -> str:
    """Column M 'Status' -- what the assigned Extended AE did with it.

    A claimed interview shows "Taken by <name>" (the person who holds it),
    matching the Google Sheet's wording exactly -- whether it was
    auto-assigned and accepted, or picked up from the pool by a different
    AE. The sheet doesn't distinguish those two; it just names the holder,
    so neither do we.
    """
    st_ = str(block.get("ext_status") or "")
    if st_ == "Selected":
        who = _who(block.get("ext_ae")) or "Extended AE"
        return f"<span class='mi-cell mi-takenby'>Taken by {_esc(who)}</span>"
    if st_ == "Rejected":
        return "<span class='mi-cell mi-rejected'>Rejected</span>"
    if st_ == "Not Selected":
        return "<span class='mi-cell mi-notsel'>Not Selected</span>"
    if st_ == "Pending":
        return "<span class='mi-cell mi-open'>Pending</span>"
    return "<span class='mi-cell mi-open'>—</span>"


def _ae_status_cell(block: dict) -> str:
    """Column N 'AE Status' -- the Core AE rung. The sheet writes a literal
    'Taken by <name>' here, so we do the same rather than inventing a
    different vocabulary for the same thing."""
    cs = str(block.get("core_status") or "")
    if cs == "Selected":
        who = _who(block.get("core_ae")) or "Core AE"
        return f"<span class='mi-cell mi-takenby'>Taken by {_esc(who)}</span>"
    if cs == "Not Selected":
        return "<span class='mi-cell mi-resched'>Passed on</span>"
    return ""


def _faculty_cell(block: dict) -> str:
    """Column O 'Taken by Faculty' -- Yes/No, exactly as the sheet has it."""
    fs = str(block.get("faculty_status") or "")
    if fs == "Selected":
        return "<span class='mi-cell mi-yes'>Yes</span>"
    if fs == "Not Selected":
        return "<span class='mi-cell mi-no'>No</span>"
    return ""


def _join_cell(block: dict) -> str:
    # Only show the link once the interview is actually Selected.
    st_ = str(block.get("ext_status") or block.get("status") or "")
    if st_ != "Selected":
        return "<span class='mi-cell'>—</span>"
    link = (block.get("class_link") or "").strip()
    if not link:
        return "<span class='mi-cell'>—</span>"
    href = link if link.startswith("http") else f"https://{link}"
    return (
        f"<input class='mi-link' type='text' readonly value='{_esc(href)}' "
        f"onclick='this.select()' title='Click to select, then Ctrl+C'/> "
        f"<a class='mi-join' href='{_esc(href)}' target='_blank' rel='noopener'>Open</a>"
    )
def _sheet_table_html(view: pd.DataFrame, me: str) -> str:
    """The whole pool as one spreadsheet-style table."""
    cols = ["Date", "Day", "Trainer Name", "Batch Code", "Sub Module",
            "Start Time", "End Time", "Assigned to", "Status", "Meeting Link",
            "AE Status", "Taken by Faculty", "Remarks"]
    head = "".join(f"<th>{c}</th>" for c in cols)
    rows = []
    for _, r in view.iterrows():
        b = r.to_dict()
        d = pd.to_datetime(b["date"])
        start, end = _slot_start_end(b.get("slot_time") or "")
        assigned = _who(b.get("ext_ae")) or "—"
        rows.append(
            "<tr>"
            f"<td>{d.strftime('%d %b %Y')}</td>"
            f"<td>{d.strftime('%a')}</td>"
            f"<td>{_esc(b.get('trainer_name'))}</td>"
            f"<td>{_esc(b.get('batch_code'))}</td>"
            f"<td>{_esc(b.get('c_alias'))}</td>"
            f"<td>{_esc(start)}</td>"
            f"<td>{_esc(end)}</td>"
            f"<td>{_esc(assigned)}</td>"
            f"<td>{_status_cell(b)}</td>"
            f"<td>{_join_cell(b)}</td>"
            f"<td>{_ae_status_cell(b)}</td>"
            f"<td>{_faculty_cell(b)}</td>"
            f"<td class='mi-wrap'>{_esc(b.get('remarks'))}</td>"
            "</tr>"
        )
    return (
        "<div class='mi-sheet-wrap'><table class='mi-sheet'>"
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table></div>"
    )


def _viewer_busy_marks(email: str, role: str, from_date, to_date) -> set:
    """Every (date, half-hour-start-minute) the viewer is already committed
    to that week -- their own CMIS teaching slots plus any evaluation
    sessions they've claimed. Used to hide Mock Interviews from the pool
    picker when the viewer isn't actually free at that time.

    Slot-level, not day-level: a person teaching 2-4 PM is still free for a
    10 AM-12 PM interview that same day, so only the overlapping half-hours
    count as busy -- matching how the allocator checks conflicts.
    """
    marks: set = set()

    # Own CMIS teaching slots.
    try:
        own = db.get_member_own_slots(email, from_date, to_date)
        for _, r in own.iterrows():
            d = pd.to_datetime(r["s_date"]).date()
            a, b = _slot_start_end(r.get("slot_time") or "")
            sm, em = _to_minutes(a), _to_minutes(b)
            if em <= sm:
                em = sm + 30
            for m in range(sm, em, 30):
                marks.add((d, m))
    except Exception:
        pass  # a failed lookup shouldn't blank the whole pool -- just skip

    # Claimed evaluation sessions (observing someone else -- also a real
    # commitment at that time).
    try:
        sel = db.get_selections_for_role(role, email, from_date, to_date)
        if not sel.empty:
            live = sel[sel["status"].isin(["Selected", "Confirmed"])]
            for _, r in live.iterrows():
                d = pd.to_datetime(r["session_date"]).date()
                a, b = _slot_start_end(r.get("slot_time") or "")
                sm, em = _to_minutes(a), _to_minutes(b)
                if em <= sm:
                    em = sm + 30
                for m in range(sm, em, 30):
                    marks.add((d, m))
    except Exception:
        pass

    # Calendar-tab overrides (ae_slot_task): an evaluation/training/project/
    # other set on the Calendar tab lives HERE, not in the selection tables.
    # This is the source behind the "via Evaluation" badge -- and it was the
    # gap: an evaluation added as a Calendar override wasn't being seen as
    # busy, so a Mock Interview overlapping it still showed in the picker.
    # Any override that isn't itself a mock_interview means the person is
    # committed at that time.
    try:
        tasks = db.get_slot_tasks(email, from_date, to_date)
        if not tasks.empty:
            for _, r in tasks.iterrows():
                if str(r.get("task_type") or "") == "mock_interview":
                    continue
                d = pd.to_datetime(r["session_date"]).date()
                a, b = _slot_start_end(r.get("slot_time") or "")
                sm, em = _to_minutes(a), _to_minutes(b)
                if em <= sm:
                    em = sm + 30
                for m in range(sm, em, 30):
                    marks.add((d, m))
    except Exception:
        pass

    return marks


def _interview_overlaps_busy(row: dict, busy: set) -> bool:
    """True if this interview's time span collides with any busy half-hour."""
    d = pd.to_datetime(row["date"]).date()
    start = int(row.get("start_min") or 0)
    a, b = _slot_start_end(row.get("slot_time") or "")
    end = _to_minutes(b)
    if end <= start:
        end = start + 30
    return any((d, m) in busy for m in range(start, end, 30))


def _week_day_strip(date_from: date, date_to: date, key: str):
    """Horizontal 'next 7 days' filter strip: an 'All days' pill plus one
    pill per day in [date_from, date_to]. Returns the selected date, or
    None for 'All days'.

    Purely a display filter on top of the fixed 7-day window this tab
    already fetches -- it doesn't change the window itself, and it's a
    self-contained duplicate of the same helper in app.py (mi_pool.py is
    imported BY app.py, so importing back from app.py here would be
    circular).
    """
    days = [date_from + timedelta(days=i) for i in range((date_to - date_from).days + 1)]
    state_key = f"_daystrip_{key}"
    if state_key not in st.session_state:
        st.session_state[state_key] = None

    cols = st.columns(len(days) + 1)
    with cols[0]:
        if st.button(
            "All", key=f"{state_key}_all", use_container_width=True,
            type="primary" if st.session_state[state_key] is None else "secondary",
        ):
            st.session_state[state_key] = None
    for i, d in enumerate(days):
        with cols[i + 1]:
            is_sel = st.session_state[state_key] == d
            if st.button(
                d.strftime("%a %d"), key=f"{state_key}_{i}", use_container_width=True,
                type="primary" if is_sel else "secondary",
            ):
                st.session_state[state_key] = d

    return st.session_state[state_key]


@st.fragment
def render_mi_pool_tab(user: dict, role: str) -> None:
    """The Mock Interview escalation pool.

    Everyone sees the same ladder; what differs is which rung you can act on.
    """
    email = user["email"]
    me = email.lower()
    st.markdown("### 🎯 Mock Interview Pool")
    st.caption(
        "Unselected Mock Interviews cascade down: **Extended AE → Core AE → "
        "Faculty**. Each interview is one whole block — a 2-hour MI is never "
        "split between two people."
    )

    # Fixed rolling 7-day window (today .. today+6), nationwide, no
    # user-editable range anymore — this tab now IS the single Mock
    # Interview entry point (old "My Mock Interviews" + old MI Pool are both
    # folded in here).
    today = date.today()
    date_from = today
    date_to = today + timedelta(days=6)
    st.caption(f"Showing {date_from} → {date_to} (next 7 days), all trainers nationwide.")

    # Auto-assignment has been REMOVED. The pool below is built directly from
    # the nationwide CMIS candidate list plus whatever manual claims already
    # exist in mock_interview_assignment / mi_pool_claim — nothing here
    # writes an assignment on anyone's behalf.

    with st.spinner("Building the Mock Interview pool…"):
        pool = build_pool(date_from, date_to)

    if pool.empty:
        st.info(f"No Mock Interview sessions in CMIS for {date_from} → {date_to}.")
        return

    st.markdown("###### 📅 Jump to a day")
    picked_day = _week_day_strip(date_from, date_to, key="mi_pool")
    if picked_day is not None:
        pool = pool[pool["date"] == picked_day]
        if pool.empty:
            st.info(f"No Mock Interview sessions on {picked_day.strftime('%a, %d %b')}.")
            return

    # ---- headline counts -------------------------------------------------
    open_ext = int(((pool["state"] == STATE_OPEN) & (pool["stage"] == STAGE_EXT)).sum())
    open_core = int(((pool["state"] == STATE_OPEN) & (pool["stage"] == STAGE_CORE)).sum())
    open_fac = int(((pool["state"] == STATE_OPEN) & (pool["stage"] == STAGE_FACULTY)).sum())
    held_ext = int((pool["ext_status"] == "Selected").sum())
    held_core = int((pool["core_status"] == "Selected").sum())
    held_fac = int((pool["faculty_status"] == "Selected").sum())

    st.markdown(
        f"""<div class="stat-row">
          <div class="stat stat-total"><div class="stat-num">{len(pool):,}</div>
            <div class="stat-lbl">Interviews</div></div>
          <div class="stat stat-avail"><div class="stat-num">{open_ext + open_core + open_fac:,}</div>
            <div class="stat-lbl">◷ Open</div></div>
          <div class="stat stat-claim"><div class="stat-num">{held_ext:,}</div>
            <div class="stat-lbl">✓ Extended AE</div></div>
          <div class="stat stat-mine"><div class="stat-num">{held_core + held_fac:,}</div>
            <div class="stat-lbl">★ Core AE / Faculty</div></div>
        </div>""",
        unsafe_allow_html=True,
    )

    if open_core:
        st.warning(f"**{open_core}** interview(s) passed over by an Extended AE — waiting on a Core AE.")
    if open_fac:
        st.error(f"**{open_fac}** interview(s) reached the bottom of the ladder and need a trainer.")

    # ---- filters ---------------------------------------------------------
    # Default to "Everything" for all roles: a claimed interview should stay
    # visible in the sheet-style table (with "Taken by <name>" in its Status
    # column), not disappear the instant someone claims it. The old per-role
    # "Open @ ..." defaults hid claimed rows, which read as the row being
    # deleted. People can still narrow to just-open rows via the Show filter.
    default_show = "Everything"

    f1, f2, f3 = st.columns(3)
    with f1:
        show = st.selectbox("Show", _SHOW_OPTIONS,
                            index=_SHOW_OPTIONS.index(default_show), key="mi_pool_show")
    with f2:
        trainers = ["All trainers"] + sorted(
            t for t in pool["trainer_name"].dropna().unique().tolist() if t)
        pick_trainer = st.selectbox("Trainer", trainers, key="mi_pool_trainer")
    with f3:
        modules = ["All modules"] + sorted(
            m for m in pool["c_alias"].dropna().unique().tolist() if m)
        pick_module = st.selectbox("Sub module", modules, key="mi_pool_module")

    view = _apply_show_filter(pool, show, email)
    if pick_trainer != "All trainers":
        view = view[view["trainer_name"] == pick_trainer]
    if pick_module != "All modules":
        view = view[view["c_alias"] == pick_module]
    view = view.sort_values(["date", "start_min", "trainer_name"]).reset_index(drop=True)

    if view.empty:
        st.info("Nothing matches these filters.")
        return

    st.markdown(
        """<div class="help-strip">
          <span><b>Tip:</b> pick the interviews you're taking below the table, then act on them.</span>
          <span class="legend">
            <span class="lg lg-avail">◷ Open</span>
            <span class="lg lg-mine">★ Yours</span>
            <span class="lg lg-lock">🔒 Someone else's</span>
          </span>
        </div>""",
        unsafe_allow_html=True,
    )

    # ---- spreadsheet-style table ----------------------------------------
    # Same shape as the "MI Details New" sheet the team already reads, so
    # nobody has to learn a second layout for the same information.
    PER_PAGE = 25
    pages = max(1, (len(view) + PER_PAGE - 1) // PER_PAGE)
    p1, p2 = st.columns([1, 4])
    with p1:
        page = st.number_input("Page", 1, pages, 1, key="mi_pool_page")
    with p2:
        st.caption(f"Page {int(page)} of {pages} · {len(view):,} interview(s)")

    lo = (int(page) - 1) * PER_PAGE
    chunk = view.iloc[lo:lo + PER_PAGE].reset_index(drop=True)

    st.markdown(_sheet_table_html(chunk, me), unsafe_allow_html=True)

    # ---- pick rows to act on --------------------------------------------
    # A checkbox per row would put a widget inside every table cell, which
    # Streamlit can't do -- so selection lives just under the table instead,
    # labelled the same way the rows read.
    def _row_label(b: dict) -> str:
        d = pd.to_datetime(b["date"]).strftime("%d %b")
        return (f"{d} · {b.get('slot_time') or ''} · "
                f"{b.get('trainer_name') or 'Unknown'} · {b.get('batch_code') or ''}")

    # Only rows still OPEN (nobody holds them yet) can be acted on. Claimed
    # rows stay VISIBLE in the table above -- so everyone sees "Taken by
    # <name>" -- but drop out of the picker, since there's nothing left to
    # do with them.
    actionable = chunk[chunk["state"] == STATE_OPEN] if "state" in chunk.columns else chunk

    # Slot-level availability filter: an Extended AE only sees interviews in
    # the picker where they're actually FREE -- no own teaching and no
    # claimed evaluation overlapping that time. (A person teaching 2-4 PM
    # can still take a 10-12 interview the same day; only real time
    # collisions are hidden.) Core AE / admin aren't filtered this way --
    # they're triaging the whole pool, not taking interviews themselves.
    if role == "extended_ae" and not actionable.empty:
        busy = _viewer_busy_marks(email, role, date_from, date_to)
        if busy:
            actionable = actionable[
                ~actionable.apply(lambda r: _interview_overlaps_busy(r.to_dict(), busy), axis=1)
            ]
    label_by_key = {r["mi_key"]: _row_label(r.to_dict()) for _, r in actionable.iterrows()}
    if not label_by_key:
        if role == "extended_ae":
            st.caption("Nothing open for you to take on this page — the interviews here "
                       "are either already taken, or clash with your own training/evaluation.")
        else:
            st.caption("Every interview on this page is already taken — nothing open to act on here.")
        return
    picked_keys = st.multiselect(
        "Select interviews to act on",
        options=list(label_by_key.keys()),
        format_func=lambda k: label_by_key.get(k, k),
        key=f"mi_pool_pick_{int(page)}",
    )

    picked = [r.to_dict() for _, r in actionable.iterrows() if r["mi_key"] in picked_keys]
    if not picked:
        st.caption("Nothing selected yet.")
        return

    st.markdown(f"**{len(picked)}** interview(s) selected.")

    # ---- actions, gated by role -----------------------------------------
    if role not in ("extended_ae", "core_ae", "admin"):
        st.info("Your role can view the pool but not claim from it.")
        return

    acted = False

    if role == "admin":
        # Admin never "claims" an interview as themselves -- an admin login
        # isn't a real Extended AE / Core AE / Faculty identity, so claiming
        # would just leave interviews owned by "admin@..." with nobody
        # actually accountable for them. Instead, admin ASSIGNS each picked
        # interview to whichever real team member should own it.
        roles_df = db.get_user_roles()
        ext_members, core_members = [], []
        if not roles_df.empty:
            name_by = dict(zip(roles_df["email"], roles_df["name"]))
            ext_members = sorted(
                roles_df.loc[roles_df["role"] == "extended_ae", "email"].tolist()
            )
            core_members = sorted(
                roles_df.loc[roles_df["role"] == "core_ae", "email"].tolist()
            )
        else:
            name_by = {}

        def _label(e: str) -> str:
            nm = name_by.get(e, e.split("@")[0])
            return f"{nm}  ({e})"

        st.markdown("##### \U0001F464 Hand to Extended AE")
        if not ext_members:
            st.caption("No Extended AE accounts found in user_roles.")
        else:
            c1, c2 = st.columns([3, 1])
            with c1:
                pick_ext = st.selectbox(
                    "Extended AE", ext_members, format_func=_label,
                    key="mi_admin_pick_ext", label_visibility="collapsed",
                )
            with c2:
                if st.button("Assign", use_container_width=True, key="mi_admin_assign_ext"):
                    try:
                        for b in picked:
                            db.upsert_mock_interview_assignment(
                                pick_ext, b["date"], b["slot_time"], b.get("batch_code"),
                                b.get("c_alias"), b.get("trainer_email"),
                               b.get("trainer_name"), b.get("program_name"),
                                class_link=b.get("class_link"),
                                status="Selected", source="admin_assign",
                            )
                        acted = True
                    except Exception as exc:
                        st.error(f"Could not assign: {exc}")

        st.markdown("##### \U0001F9D1\u200D\U0001F4BC Hand to Core AE")
        if not core_members:
            st.caption("No Core AE accounts found in user_roles.")
        else:
            c1, c2 = st.columns([3, 1])
            with c1:
                pick_core = st.selectbox(
                    "Core AE", core_members, format_func=_label,
                    key="mi_admin_pick_core", label_visibility="collapsed",
                )
            with c2:
                if st.button("Assign", use_container_width=True, key="mi_admin_assign_core"):
                    try:
                        for b in picked:
                            upsert_pool_claim(b, "core_ae", pick_core, status="Selected")
                        acted = True
                    except Exception as exc:
                        if "mi_pool_claim" in str(exc) or "doesn't exist" in str(exc).lower():
                            st.error(
                                "The **mi_pool_claim** table is missing. Run "
                                "`create_mi_pool.sql` against the Anudip_AE_Team "
                                "database, then try again."
                            )
                        else:
                            st.error(f"Could not assign: {exc}")

        st.markdown("##### \U0001F393 Hand to Faculty")
        st.caption(
            "Sends each selected interview straight to its own trainer -- "
            "no picker needed, the trainer running the class is already known."
        )
        if st.button("Assign to Faculty", use_container_width=True, key="mi_admin_assign_faculty"):
            try:
                for b in picked:
                    upsert_pool_claim(
                        b, "faculty", b.get("trainer_email") or "",
                        status="Selected", remarks=f"Assigned to faculty by {email} (admin)",
                    )
                acted = True
            except Exception as exc:
                if "mi_pool_claim" in str(exc) or "doesn't exist" in str(exc).lower():
                    st.error(
                        "The **mi_pool_claim** table is missing. Run "
                        "`create_mi_pool.sql` against the Anudip_AE_Team "
                        "database, then try again."
                    )
                else:
                    st.error(f"Could not assign: {exc}")

    else:
        # Extended AE / Core AE: unchanged self-claim behaviour.
        can_ext = role == "extended_ae"
        can_core = role == "core_ae"
        buttons = []
        if can_ext:
            buttons += [("✅ Claim as Extended AE", "ext_take")]
        if can_core:
            buttons += [("✅ Take as Core AE", "core_take"),
                        ("👤 Hand to faculty", "core_pass")]

        cols = st.columns(len(buttons))
        for col, (label, action) in zip(cols, buttons):
            with col:
                if not st.button(label, use_container_width=True, key=f"mi_btn_{action}"):
                    continue
                try:
                    for b in picked:
                        if action == "ext_take":
                            db.upsert_mock_interview_assignment(
                                email, b["date"], b["slot_time"], b.get("batch_code"),
                                b.get("c_alias"), b.get("trainer_email"),
                             b.get("trainer_name"), b.get("program_name"),
                                class_link=b.get("class_link"),
                                status="Selected", source="pool",
                            )
                        elif action == "core_take":
                            upsert_pool_claim(b, "core_ae", email, status="Selected")
                        else:
                            # Passing at the Core AE rung is what drops it to
                            # Faculty; the trainer running the class then owns it.
                            upsert_pool_claim(b, "core_ae", email, status="Not Selected")
                            upsert_pool_claim(
                                b, "faculty", b.get("trainer_email") or "",
                                status="Selected", remarks=f"Handed to trainer by {email}",
                            )
                    acted = True
                except Exception as exc:
                    if "mi_pool_claim" in str(exc) or "doesn't exist" in str(exc).lower():
                        st.error(
                            "The **mi_pool_claim** table is missing. Run "
                            "`create_mi_pool.sql` against the Anudip_AE_Team "
                            "database, then try again."
                        )
                    else:
                        st.error(f"Could not save: {exc}")

    with st.expander("Release a claim (put it back in the pool)"):
        st.caption("Removes the selected interviews from whichever rung holds them.")
        if st.button("🔓 Release selected", use_container_width=True, key="mi_btn_release"):
            for b in picked:
                release_pool_claim(b["mi_key"], "faculty")
                release_pool_claim(b["mi_key"], "core_ae")
            acted = True

    if acted:
        clear_pool_caches()
        for fn in (db.get_mock_interview_assignments,):
            try:
                fn.clear()
            except Exception:
                pass
        st.success("Saved.")
        st.rerun(scope="fragment")
