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

    # Stage 1 — Extended AE auto-assignments, keyed the same way blocks are.
    ext_by_key: dict[str, dict] = {}
    ext = db.get_mock_interview_assignments(None, from_date, to_date)
    if not ext.empty:
        for _, r in ext.iterrows():
            d = pd.to_datetime(r["session_date"]).date()
            k = f"{d}|{r['slot_time']}|{r['batch_code'] or ''}"
            cur = ext_by_key.get(k)
            # A 'Selected' row always wins over a 'Not Selected' one, so a
            # block someone actually took never looks abandoned just because
            # a second, stale row exists for it.
            if cur is None or (str(r["status"]) == "Selected"):
                ext_by_key[k] = {
                    "ae": r["extended_ae_email"], "status": str(r["status"]),
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
        e = ext_by_key.get(k, {})
        c = core_by_key.get(k, {})
        f = fac_by_key.get(k, {})

        ext_status = e.get("status", "")
        core_status = c.get("status", "")
        fac_status = f.get("status", "")

        # Walk the ladder from the bottom rung up: whoever most recently
        # accepted holds it; otherwise it sits open at the rung just below
        # the last person who passed.
        if fac_status == "Selected":
            stage, state, holder = STAGE_FACULTY, STATE_CLAIMED, f.get("by", "")
        elif core_status == "Selected":
            stage, state, holder = STAGE_CORE, STATE_CLAIMED, c.get("by", "")
        elif ext_status == "Selected":
            stage, state, holder = STAGE_EXT, STATE_CLAIMED, e.get("ae", "")
        elif core_status == "Not Selected":
            stage, state, holder = STAGE_FACULTY, STATE_OPEN, ""
        elif ext_status == "Not Selected":
            stage, state, holder = STAGE_CORE, STATE_OPEN, ""
        else:
            stage, state, holder = STAGE_EXT, STATE_OPEN, ""

        rows.append({
            **b,
            "ext_ae": e.get("ae", ""),
            "ext_status": ext_status,
            "core_ae": c.get("by", ""),
            "core_status": core_status,
            "faculty": f.get("by", ""),
            "faculty_status": fac_status,
            "remarks": c.get("remarks") or f.get("remarks") or "",
            "stage": stage,
            "state": state,
            "holder": holder,
        })

    return pd.DataFrame(rows)


def clear_pool_caches() -> None:
    """Invalidate only what a pool write can possibly have changed."""
    for fn in (get_pool_claims, get_mi_blocks):
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

    # Own date range. This used to read st.session_state['shared_from'], which
    # the Sessions tab only sets AFTER four possible early returns -- so if a
    # Core AE had no faculty mapped, or no sessions in range, this tab was
    # permanently stuck on "open the Sessions tab first".
    today = date.today()
    d1, d2, d3 = st.columns(3)
    with d1:
        date_from = st.date_input("From", value=today, key="mi_from")
    with d2:
        date_to = st.date_input("To", value=today + timedelta(days=13), key="mi_to")
    if date_to < date_from:
        st.warning("‘To’ is before ‘From’ — widen the range.")
        return

    # Make sure allocation has actually run for this window. Without this the
    # pool read straight from an empty assignment table and every row showed
    # "Extended AE / Open / —", which looked like the allocator was broken.
    try:
        db.ensure_mock_interviews_assigned(date_from, date_to, cap_per_week=3)
    except Exception as exc:
        st.warning(f"Auto-assignment did not run: {exc}")

    with st.spinner("Building the Mock Interview pool…"):
        pool = build_pool(date_from, date_to)

    if pool.empty:
        st.info(f"No Mock Interview sessions in CMIS for {date_from} → {date_to}.")
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
    default_show = {
        "extended_ae": "Open @ Extended AE",
        "core_ae": "Open @ Core AE",
    }.get(role, "Open — needs someone")

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
          <span><b>Tip:</b> tick the interviews you're taking, then act on them below.</span>
          <span class="legend">
            <span class="lg lg-avail">◷ Open</span>
            <span class="lg lg-mine">★ Yours</span>
            <span class="lg lg-lock">🔒 Someone else's</span>
          </span>
        </div>""",
        unsafe_allow_html=True,
    )

    # ---- paginated cards, grouped by day --------------------------------
    PER_PAGE = 20
    pages = max(1, (len(view) + PER_PAGE - 1) // PER_PAGE)
    p1, p2 = st.columns([1, 4])
    with p1:
        page = st.number_input("Page", 1, pages, 1, key="mi_pool_page")
    with p2:
        st.caption(f"Page {int(page)} of {pages} · {len(view):,} interview(s)")

    lo = (int(page) - 1) * PER_PAGE
    chunk = view.iloc[lo:lo + PER_PAGE].reset_index(drop=True)

    picked_keys: list[str] = []
    shown_day = None
    for i, b in chunk.iterrows():
        blk = b.to_dict()
        if blk["date"] != shown_day:
            st.markdown(
                f"<div class='slot-head'>📅 "
                f"{pd.to_datetime(blk['date']).strftime('%A, %d %b %Y')}</div>",
                unsafe_allow_html=True,
            )
            shown_day = blk["date"]

        c1, c2 = st.columns([5, 1.1])
        with c1:
            st.markdown(_card_html(blk, me), unsafe_allow_html=True)
        with c2:
            trainer = str(blk.get("trainer_name") or "")[:14]
            if st.checkbox("Take", key=f"mi_take_{blk['mi_key']}",
                           help=f"{blk['slot_time']} · {trainer}"):
                picked_keys.append(blk["mi_key"])

    picked = [r.to_dict() for _, r in chunk.iterrows() if r["mi_key"] in picked_keys]
    if not picked:
        st.caption("Nothing ticked yet.")
        return

    st.markdown(f"**{len(picked)}** interview(s) ticked.")

    # ---- actions, gated by role -----------------------------------------
    can_ext = role in ("extended_ae", "admin")
    can_core = role in ("core_ae", "admin")
    if not (can_ext or can_core):
        st.info("Your role can view the pool but not claim from it.")
        return

    acted = False
    buttons = []
    if can_ext:
        buttons += [("✅ Claim as Extended AE", "ext_take"),
                    ("↩️ Pass to Core AE", "ext_pass")]
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
                    if action in ("ext_take", "ext_pass"):
                        db.upsert_mock_interview_assignment(
                            email, b["date"], b["slot_time"], b.get("batch_code"),
                            b.get("c_alias"), b.get("trainer_email"),
                            b.get("trainer_name"), b.get("program_name"),
                            status="Selected" if action == "ext_take" else "Not Selected",
                            source="pool",
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
        st.caption("Removes the ticked interviews from whichever rung holds them.")
        if st.button("🔓 Release ticked", use_container_width=True, key="mi_btn_release"):
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
        st.rerun()
