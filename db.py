"""
Database access layer.

Two connections:
  * CMIS  (read-only)  -> faculty sessions, from `upcoming_trainer_utilization_view`
  * appdb (read/write) -> the 5 Anudip_AE_Team tables:
        core_ae_faculty_map, extended_ae_session_selection,
        session_highlight_flags, user_roles, weekly_ae_summary

Uses SQLAlchemy engines with pooling. Credentials come from st.secrets.
All CMIS access is strictly SELECT — we never write there.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def _make_engine(section: str) -> Engine:
    cfg = st.secrets[section]
    pwd = quote_plus(str(cfg["password"]))  # escape @ : / * etc. in passwords
    user = quote_plus(str(cfg["user"]))
    url = (
        f"mysql+pymysql://{user}:{pwd}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['database']}?charset=utf8mb4"
    )
    return create_engine(url, pool_pre_ping=True, pool_recycle=1800, future=True)


@st.cache_resource
def cmis_engine() -> Engine:
    return _make_engine("cmis")


@st.cache_resource
def app_engine() -> Engine:
    return _make_engine("appdb")


# ---------------------------------------------------------------------------
# CMIS reads (faculty sessions)
# ---------------------------------------------------------------------------
CMIS_VIEW = "upcoming_trainer_utilization_view"


@st.cache_data(ttl=300, show_spinner=False)
def fetch_sessions_for_faculty(faculty_emails: tuple[str, ...], week_start: date, week_end: date) -> pd.DataFrame:
    """All CMIS sessions for the given faculty emails within [week_start, week_end]."""
    if not faculty_emails:
        return pd.DataFrame()
    placeholders = ", ".join(f":e{i}" for i in range(len(faculty_emails)))
    params: dict[str, Any] = {f"e{i}": e for i, e in enumerate(faculty_emails)}
    params["ws"] = week_start
    params["we"] = week_end
    sql = text(
        f"""
        SELECT s_date, m_code, f_name, l_name, time_duration, day_name,
               c_alias, slot_name, slot_time, batch_code, email_id,
               class_link, program_name
        FROM {CMIS_VIEW}
        WHERE email_id IN ({placeholders})
          AND s_date BETWEEN :ws AND :we
        ORDER BY s_date, slot_time
        """
    )
    with cmis_engine().connect() as conn:
        return pd.read_sql(sql, conn, params=params)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_sessions_all_for_faculty(faculty_emails: tuple[str, ...], from_date: date | None = None) -> pd.DataFrame:
    """
    EVERY CMIS session for these faculty — the full horizon the view holds
    (not just one week). Optionally bounded below by `from_date`.
    """
    if not faculty_emails:
        return pd.DataFrame()
    placeholders = ", ".join(f":e{i}" for i in range(len(faculty_emails)))
    params: dict[str, Any] = {f"e{i}": e for i, e in enumerate(faculty_emails)}
    where_date = ""
    if from_date is not None:
        where_date = " AND s_date >= :fd"
        params["fd"] = from_date
    sql = text(
        f"""
        SELECT s_date, m_code, f_name, l_name, time_duration, day_name,
               c_alias, slot_name, slot_time, batch_code, email_id,
               class_link, program_name
        FROM {CMIS_VIEW}
        WHERE email_id IN ({placeholders}){where_date}
        ORDER BY s_date, slot_time
        """
    )
    with cmis_engine().connect() as conn:
        return pd.read_sql(sql, conn, params=params)


@st.cache_data(ttl=300, show_spinner=False)
def cmis_date_bounds() -> tuple[date | None, date | None]:
    """Min/max session date available in the CMIS view."""
    sql = text(f"SELECT MIN(s_date) AS lo, MAX(s_date) AS hi FROM {CMIS_VIEW}")
    with cmis_engine().connect() as conn:
        df = pd.read_sql(sql, conn)
    if df.empty:
        return None, None
    lo, hi = df.iloc[0]["lo"], df.iloc[0]["hi"]
    return (pd.to_datetime(lo).date() if lo is not None else None,
            pd.to_datetime(hi).date() if hi is not None else None)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_sessions_all(week_start: date, week_end: date, limit: int = 5000) -> pd.DataFrame:
    """All CMIS sessions in the window (admin overview)."""
    sql = text(
        f"""
        SELECT s_date, m_code, f_name, l_name, day_name, c_alias,
               slot_time, batch_code, email_id, program_name
        FROM {CMIS_VIEW}
        WHERE s_date BETWEEN :ws AND :we
        ORDER BY s_date, slot_time
        LIMIT :lim
        """
    )
    with cmis_engine().connect() as conn:
        return pd.read_sql(sql, conn, params={"ws": week_start, "we": week_end, "lim": limit})


# ---------------------------------------------------------------------------
# App DB reads
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def get_user_roles() -> pd.DataFrame:
    with app_engine().connect() as conn:
        return pd.read_sql(text("SELECT email, name, role FROM user_roles"), conn)


@st.cache_data(ttl=60, show_spinner=False)
def get_core_ae_faculty_map() -> pd.DataFrame:
    with app_engine().connect() as conn:
        return pd.read_sql(
            text(
                "SELECT core_ae_email, faculty_1, faculty_2, faculty_3, faculty_4, faculty_5 "
                "FROM core_ae_faculty_map"
            ),
            conn,
        )


def faculty_emails_for_core(core_ae_email: str) -> list[str]:
    df = get_core_ae_faculty_map()
    rows = df[df["core_ae_email"] == core_ae_email]
    out: list[str] = []
    for _, r in rows.iterrows():
        for c in ("faculty_1", "faculty_2", "faculty_3", "faculty_4", "faculty_5"):
            v = r[c]
            if v and str(v).strip():
                out.append(str(v).strip())
    return sorted(set(out))


def list_core_ae_emails() -> list[str]:
    df = get_core_ae_faculty_map()
    return sorted(df["core_ae_email"].dropna().unique().tolist())


def get_selections(extended_ae_email: str | None, week_start: date, week_end: date) -> pd.DataFrame:
    where = "session_date BETWEEN :ws AND :we"
    params: dict[str, Any] = {"ws": week_start, "we": week_end}
    if extended_ae_email:
        where += " AND extended_ae_email = :eae"
        params["eae"] = extended_ae_email
    sql = text(
        f"""
        SELECT id, extended_ae_email, session_date, slot_time, module, batch_code, status
        FROM extended_ae_session_selection
        WHERE {where}
        """
    )
    with app_engine().connect() as conn:
        return pd.read_sql(sql, conn, params=params)


# ---------------------------------------------------------------------------
# App DB writes
# ---------------------------------------------------------------------------
def upsert_selection(
    extended_ae_email: str,
    session_date: date,
    slot_time: str,
    module: str | None,
    batch_code: str | None,
    status: str,
) -> None:
    """
    One selection row per (extended_ae, date, slot, batch). Update status if it
    exists, else insert. `status` in: Not Selected / Choosing / Selected / Confirmed.
    """
    with app_engine().begin() as conn:
        existing = conn.execute(
            text(
                """
                SELECT id FROM extended_ae_session_selection
                WHERE extended_ae_email = :eae AND session_date = :d
                  AND slot_time = :st AND (batch_code <=> :bc)
                LIMIT 1
                """
            ),
            {"eae": extended_ae_email, "d": session_date, "st": slot_time, "bc": batch_code},
        ).fetchone()
        if existing:
            conn.execute(
                text("UPDATE extended_ae_session_selection SET status = :s, updated_on = NOW() WHERE id = :id"),
                {"s": status, "id": existing[0]},
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO extended_ae_session_selection
                        (extended_ae_email, session_date, slot_time, module, batch_code, status)
                    VALUES (:eae, :d, :st, :mod, :bc, :s)
                    """
                ),
                {"eae": extended_ae_email, "d": session_date, "st": slot_time,
                 "mod": module, "bc": batch_code, "s": status},
            )


def set_highlight_flag(
    session_date: date,
    slot_time: str,
    batch_code: str | None,
    core_ae_email: str,
    extended_ae_email: str | None,
    is_highlighted: bool,
) -> None:
    with app_engine().begin() as conn:
        existing = conn.execute(
            text(
                """
                SELECT id FROM session_highlight_flags
                WHERE session_date = :d AND slot_time = :st
                  AND (batch_code <=> :bc) AND core_ae_email = :cae
                LIMIT 1
                """
            ),
            {"d": session_date, "st": slot_time, "bc": batch_code, "cae": core_ae_email},
        ).fetchone()
        if existing:
            conn.execute(
                text(
                    "UPDATE session_highlight_flags "
                    "SET is_highlighted = :h, extended_ae_email = :eae, updated_on = NOW() WHERE id = :id"
                ),
                {"h": 1 if is_highlighted else 0, "eae": extended_ae_email, "id": existing[0]},
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO session_highlight_flags
                        (session_date, slot_time, batch_code, core_ae_email, extended_ae_email, is_highlighted)
                    VALUES (:d, :st, :bc, :cae, :eae, :h)
                    """
                ),
                {"d": session_date, "st": slot_time, "bc": batch_code,
                 "cae": core_ae_email, "eae": extended_ae_email, "h": 1 if is_highlighted else 0},
            )


def upsert_weekly_summary(
    core_ae_email: str, week_start: date, total: int, selected: int, observed: int
) -> None:
    with app_engine().begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM weekly_ae_summary WHERE core_ae_email = :c AND week_start_date = :w LIMIT 1"),
            {"c": core_ae_email, "w": week_start},
        ).fetchone()
        if existing:
            conn.execute(
                text(
                    "UPDATE weekly_ae_summary SET total_sessions=:t, sessions_selected=:s, "
                    "sessions_observed=:o, updated_on=NOW() WHERE id=:id"
                ),
                {"t": total, "s": selected, "o": observed, "id": existing[0]},
            )
        else:
            conn.execute(
                text(
                    "INSERT INTO weekly_ae_summary "
                    "(core_ae_email, week_start_date, total_sessions, sessions_selected, sessions_observed) "
                    "VALUES (:c, :w, :t, :s, :o)"
                ),
                {"c": core_ae_email, "w": week_start, "t": total, "s": selected, "o": observed},
            )


def ping() -> tuple[bool, bool]:
    """Return (cmis_ok, appdb_ok) for the connection self-test."""
    cmis_ok = appdb_ok = False
    try:
        with cmis_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        cmis_ok = True
    except Exception:
        pass
    try:
        with app_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        appdb_ok = True
    except Exception:
        pass
    return cmis_ok, appdb_ok


# ---------------------------------------------------------------------------
# Session evaluations (post-observation form)  -> table: session_evaluation
# ---------------------------------------------------------------------------
def make_session_id(trainer_email: str, session_date, slot_time: str, batch_code: str | None) -> str:
    """Stable key for a CMIS session (the view has no surrogate id of its own)."""
    d = pd.to_datetime(session_date).date().isoformat()
    return f"{trainer_email}|{d}|{slot_time}|{batch_code or ''}"


def get_evaluations(evaluator_email: str | None = None) -> pd.DataFrame:
    where, params = "1=1", {}
    if evaluator_email:
        where = "evaluator_email = :e"
        params["e"] = evaluator_email
    sql = text(
        f"""
        SELECT id, evaluator_email, evaluator_role, session_id, trainer_name,
               trainer_email, session_date, slot_time, batch_code, module,
               program_name, duration_minutes, rating, remarks, status, created_on
        FROM session_evaluation
        WHERE {where}
        ORDER BY created_on DESC
        """
    )
    try:
        with app_engine().connect() as conn:
            return pd.read_sql(sql, conn, params=params)
    except Exception:
        # table not created yet
        return pd.DataFrame()


def evaluated_session_ids(evaluator_email: str) -> set[str]:
    df = get_evaluations(evaluator_email)
    if df.empty:
        return set()
    return set(df["session_id"].tolist())


def save_evaluation(
    evaluator_email: str,
    evaluator_role: str,
    session_id: str,
    trainer_name: str | None,
    trainer_email: str | None,
    session_date: date,
    slot_time: str,
    batch_code: str | None,
    module: str | None,
    program_name: str | None,
    duration_minutes: int | None,
    rating: int | None,
    remarks: str | None,
) -> None:
    """Insert or update this evaluator's evaluation of this session."""
    with app_engine().begin() as conn:
        existing = conn.execute(
            text(
                "SELECT id FROM session_evaluation "
                "WHERE evaluator_email = :e AND session_id = :s LIMIT 1"
            ),
            {"e": evaluator_email, "s": session_id},
        ).fetchone()
        payload = {
            "e": evaluator_email, "r": evaluator_role, "s": session_id,
            "tn": trainer_name, "te": trainer_email, "d": session_date,
            "st": slot_time, "bc": batch_code, "mo": module, "pn": program_name,
            "dur": duration_minutes, "rt": rating, "rm": remarks,
        }
        if existing:
            conn.execute(
                text(
                    "UPDATE session_evaluation SET duration_minutes=:dur, rating=:rt, "
                    "remarks=:rm, status='Completed', updated_on=NOW() WHERE id=:id"
                ),
                {"dur": duration_minutes, "rt": rating, "rm": remarks, "id": existing[0]},
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO session_evaluation
                        (evaluator_email, evaluator_role, session_id, trainer_name,
                         trainer_email, session_date, slot_time, batch_code, module,
                         program_name, duration_minutes, rating, remarks, status)
                    VALUES (:e,:r,:s,:tn,:te,:d,:st,:bc,:mo,:pn,:dur,:rt,:rm,'Completed')
                    """
                ),
                payload,
            )


def week_monday(d) -> date:
    """Monday of the week containing d."""
    d = pd.to_datetime(d).date()
    return d - timedelta(days=d.weekday())


def recompute_weekly_summary(core_ae_email: str, any_day_in_week) -> None:
    """
    Recalculate and store this Core AE's counts for the week containing
    `any_day_in_week`, writing to weekly_ae_summary.

      total_sessions    = sessions flagged available for observation
                          (session_highlight_flags.is_highlighted = 1)
      sessions_selected = selections with status Selected / Confirmed
      sessions_observed = evaluations submitted (session_evaluation rows)

    Called after any claim / evaluation so the table stays current.
    """
    ws = week_monday(any_day_in_week)
    we = ws + timedelta(days=6)

    with app_engine().begin() as conn:
        total = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM session_highlight_flags
                WHERE core_ae_email = :c
                  AND session_date BETWEEN :ws AND :we
                  AND is_highlighted = 1
                """
            ),
            {"c": core_ae_email, "ws": ws, "we": we},
        ).scalar() or 0

        # selections are keyed by (date, slot, batch); scope them to this Core AE
        # via the highlight flags, which carry core_ae_email.
        # selections now live in TWO tables (one per role) — count both.
        selected = 0
        for tbl in ("extended_ae_session_selection", "core_ae_session_selection"):
            try:
                selected += conn.execute(
                    text(
                        f"""
                        SELECT COUNT(DISTINCT s.id)
                        FROM {tbl} s
                        JOIN session_highlight_flags f
                          ON f.session_date = s.session_date
                         AND f.slot_time    = s.slot_time
                         AND (f.batch_code <=> s.batch_code)
                        WHERE f.core_ae_email = :c
                          AND s.session_date BETWEEN :ws AND :we
                          AND s.status IN ('Selected', 'Confirmed')
                        """
                    ),
                    {"c": core_ae_email, "ws": ws, "we": we},
                ).scalar() or 0
            except Exception:
                pass  # table may not exist yet

        # evaluations likewise split per role
        observed = 0
        for tbl in ("extended_ae_evaluation", "core_ae_evaluation"):
            try:
                observed += conn.execute(
                    text(
                        f"""
                        SELECT COUNT(DISTINCT e.id)
                        FROM {tbl} e
                        JOIN session_highlight_flags f
                          ON f.session_date = e.session_date
                         AND f.slot_time    = e.slot_time
                         AND (f.batch_code <=> e.batch_code)
                        WHERE f.core_ae_email = :c
                          AND e.session_date BETWEEN :ws AND :we
                        """
                    ),
                    {"c": core_ae_email, "ws": ws, "we": we},
                ).scalar() or 0
            except Exception:
                pass

    upsert_weekly_summary(core_ae_email, ws, int(total), int(selected), int(observed))


def get_weekly_summary(core_ae_email: str | None = None) -> pd.DataFrame:
    where, params = "1=1", {}
    if core_ae_email:
        where = "core_ae_email = :c"
        params["c"] = core_ae_email
    sql = text(
        f"""
        SELECT core_ae_email, week_start_date, total_sessions,
               sessions_selected, sessions_observed, updated_on
        FROM weekly_ae_summary
        WHERE {where}
        ORDER BY week_start_date DESC, core_ae_email
        """
    )
    try:
        with app_engine().connect() as conn:
            return pd.read_sql(sql, conn, params=params)
    except Exception:
        return pd.DataFrame()


# ===========================================================================
# ROLE-SEPARATED selections + evaluations
#   core_ae_session_selection      (+ assigned_extended_ae_email)
#   extended_ae_session_selection
#   core_ae_evaluation
#   extended_ae_evaluation
# The role decides which pair of tables is used.
# ===========================================================================

def _sel_table(role: str) -> tuple[str, str]:
    """(table, email_column) for the selection table matching this role."""
    if role == "extended_ae":
        return "extended_ae_session_selection", "extended_ae_email"
    return "core_ae_session_selection", "core_ae_email"


def _eval_table(role: str) -> tuple[str, str]:
    """(table, email_column) for the evaluation table matching this role."""
    if role == "extended_ae":
        return "extended_ae_evaluation", "extended_ae_email"
    return "core_ae_evaluation", "core_ae_email"


def get_selections_for_role(role: str, email: str | None, from_date: date, to_date: date) -> pd.DataFrame:
    tbl, col = _sel_table(role)
    where = "session_date BETWEEN :a AND :b"
    params: dict[str, Any] = {"a": from_date, "b": to_date}
    if email:
        where += f" AND {col} = :e"
        params["e"] = email
    extra = ", assigned_extended_ae_email" if tbl == "core_ae_session_selection" else ""
    sql = text(
        f"SELECT id, {col} AS owner_email, session_date, slot_time, module, "
        f"batch_code, status{extra} FROM {tbl} WHERE {where}"
    )
    try:
        with app_engine().connect() as conn:
            return pd.read_sql(sql, conn, params=params)
    except Exception:
        return pd.DataFrame()


def upsert_selection_for_role(
    role: str,
    email: str,
    session_date: date,
    slot_time: str,
    module: str | None,
    batch_code: str | None,
    status: str,
    assigned_extended_ae_email: str | None = None,
) -> int | None:
    """Write a claim to the table that matches the user's role. Returns the row id."""
    tbl, col = _sel_table(role)
    is_core = tbl == "core_ae_session_selection"

    with app_engine().begin() as conn:
        existing = conn.execute(
            text(
                f"SELECT id FROM {tbl} WHERE {col} = :e AND session_date = :d "
                f"AND slot_time = :st AND (batch_code <=> :bc) LIMIT 1"
            ),
            {"e": email, "d": session_date, "st": slot_time, "bc": batch_code},
        ).fetchone()

        if existing:
            row_id = existing[0]
            if is_core:
                conn.execute(
                    text(
                        f"UPDATE {tbl} SET status=:s, assigned_extended_ae_email=:a, "
                        f"updated_on=NOW() WHERE id=:id"
                    ),
                    {"s": status, "a": assigned_extended_ae_email, "id": row_id},
                )
            else:
                conn.execute(
                    text(f"UPDATE {tbl} SET status=:s, updated_on=NOW() WHERE id=:id"),
                    {"s": status, "id": row_id},
                )
            return row_id
        else:
            if is_core:
                res = conn.execute(
                    text(
                        f"INSERT INTO {tbl} ({col}, session_date, slot_time, module, "
                        f"batch_code, status, assigned_extended_ae_email) "
                        f"VALUES (:e,:d,:st,:m,:bc,:s,:a)"
                    ),
                    {"e": email, "d": session_date, "st": slot_time, "m": module,
                     "bc": batch_code, "s": status, "a": assigned_extended_ae_email},
                )
            else:
                res = conn.execute(
                    text(
                        f"INSERT INTO {tbl} ({col}, session_date, slot_time, module, "
                        f"batch_code, status) VALUES (:e,:d,:st,:m,:bc,:s)"
                    ),
                    {"e": email, "d": session_date, "st": slot_time, "m": module,
                     "bc": batch_code, "s": status},
                )
            return res.lastrowid


def get_evaluations_for_role(role: str, email: str | None = None) -> pd.DataFrame:
    tbl, col = _eval_table(role)
    where, params = "1=1", {}
    if email:
        where = f"{col} = :e"
        params["e"] = email
    sql = text(
        f"SELECT id, {col} AS evaluator_email, session_id, trainer_name, trainer_email, "
        f"session_date, slot_time, batch_code, module, program_name, duration_minutes, "
        f"rating, remarks, status, created_on FROM {tbl} WHERE {where} ORDER BY created_on DESC"
    )
    try:
        with app_engine().connect() as conn:
            return pd.read_sql(sql, conn, params=params)
    except Exception:
        return pd.DataFrame()


def evaluated_session_ids_for_role(role: str, email: str) -> set[str]:
    df = get_evaluations_for_role(role, email)
    return set(df["session_id"].tolist()) if not df.empty else set()


def save_evaluation_for_role(
    role: str,
    email: str,
    session_id: str,
    trainer_name: str | None,
    trainer_email: str | None,
    session_date: date,
    slot_time: str,
    batch_code: str | None,
    module: str | None,
    program_name: str | None,
    duration_minutes: int | None,
    rating: int | None,
    remarks: str | None,
) -> None:
    tbl, col = _eval_table(role)
    with app_engine().begin() as conn:
        existing = conn.execute(
            text(f"SELECT id FROM {tbl} WHERE {col} = :e AND session_id = :s LIMIT 1"),
            {"e": email, "s": session_id},
        ).fetchone()
        if existing:
            conn.execute(
                text(
                    f"UPDATE {tbl} SET duration_minutes=:dur, rating=:rt, remarks=:rm, "
                    f"status='Completed', updated_on=NOW() WHERE id=:id"
                ),
                {"dur": duration_minutes, "rt": rating, "rm": remarks, "id": existing[0]},
            )
        else:
            conn.execute(
                text(
                    f"INSERT INTO {tbl} ({col}, session_id, trainer_name, trainer_email, "
                    f"session_date, slot_time, batch_code, module, program_name, "
                    f"duration_minutes, rating, remarks, status) "
                    f"VALUES (:e,:sid,:tn,:te,:d,:st,:bc,:mo,:pn,:dur,:rt,:rm,'Completed')"
                ),
                {"e": email, "sid": session_id, "tn": trainer_name, "te": trainer_email,
                 "d": session_date, "st": slot_time, "bc": batch_code, "mo": module,
                 "pn": program_name, "dur": duration_minutes, "rt": rating, "rm": remarks},
            )


# ---------------------------------------------------------------------------
# Core AE  <->  Extended AE pairing, from the `ae_extae` table
#   ae_email_id | ext_ae_1 | ext_ae_2 | ext_ae_3
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def get_ae_pairings() -> pd.DataFrame:
    try:
        with app_engine().connect() as conn:
            return pd.read_sql(
                text("SELECT ae_email_id, ext_ae_1, ext_ae_2, ext_ae_3 FROM ae_extae"), conn
            )
    except Exception:
        return pd.DataFrame()


def extended_aes_for_core(core_ae_email: str) -> list[str]:
    """The Extended AEs paired to this Core AE (from ae_extae)."""
    df = get_ae_pairings()
    if df.empty:
        return []
    rows = df[df["ae_email_id"].str.lower() == (core_ae_email or "").lower()]
    out: list[str] = []
    for _, r in rows.iterrows():
        for c in ("ext_ae_1", "ext_ae_2", "ext_ae_3"):
            v = r.get(c)
            # pandas turns SQL NULLs into NaN, which str()s to "nan" —
            # guard explicitly or a bogus "nan" option reaches the dropdown.
            if pd.isna(v):
                continue
            s = str(v).strip()
            if s and s.lower() not in ("nan", "none", "null"):
                out.append(s)
    return sorted(set(out))


def core_ae_for_extended(extended_ae_email: str) -> str | None:
    """The Core AE this Extended AE is paired to (from ae_extae)."""
    df = get_ae_pairings()
    if df.empty:
        return None
    target = (extended_ae_email or "").lower()
    if not target:
        return None
    for _, r in df.iterrows():
        for c in ("ext_ae_1", "ext_ae_2", "ext_ae_3"):
            v = r.get(c)
            if pd.isna(v):
                continue
            if str(v).strip().lower() == target:
                return r["ae_email_id"]
    return None


def all_extended_aes() -> list[str]:
    """Every Extended AE in user_roles (used for the 'pick others' escape hatch)."""
    df = get_user_roles()
    if df.empty:
        return []
    return sorted(df[df["role"] == "extended_ae"]["email"].tolist())


# ---------------------------------------------------------------------------
# CHANGE #1 — delegated sessions must be visible to the assigned Extended AE.
# A Core AE claims into core_ae_session_selection and sets
# assigned_extended_ae_email; that work has to surface for the assignee.
# ---------------------------------------------------------------------------
def get_delegated_to_extended(extended_ae_email: str, from_date: date, to_date: date) -> pd.DataFrame:
    """Sessions a Core AE claimed and assigned TO this Extended AE."""
    sql = text(
        """
        SELECT id, core_ae_email, session_date, slot_time, module, batch_code,
               status, assigned_extended_ae_email
        FROM core_ae_session_selection
        WHERE assigned_extended_ae_email = :e
          AND session_date BETWEEN :a AND :b
        """
    )
    try:
        with app_engine().connect() as conn:
            return pd.read_sql(sql, conn, params={"e": extended_ae_email, "a": from_date, "b": to_date})
    except Exception:
        return pd.DataFrame()


def get_visible_selections(role: str, email: str, from_date: date, to_date: date) -> pd.DataFrame:
    """
    Everything this user should see as 'theirs' for the period.

      core_ae / admin -> their own core_ae_session_selection rows
      extended_ae     -> their own claims  +  anything delegated to them

    Returns columns: session_date, slot_time, batch_code, status, source
    where source is 'own' or 'delegated'.
    """
    own = get_selections_for_role(role, email, from_date, to_date)
    if not own.empty:
        own = own[["session_date", "slot_time", "batch_code", "status"]].copy()
        own["source"] = "own"
        own["delegated_by"] = None

    if role != "extended_ae":
        return own if not own.empty else pd.DataFrame(
            columns=["session_date", "slot_time", "batch_code", "status", "source", "delegated_by"]
        )

    deleg = get_delegated_to_extended(email, from_date, to_date)
    if not deleg.empty:
        deleg = deleg[["session_date", "slot_time", "batch_code", "status", "core_ae_email"]].copy()
        deleg = deleg.rename(columns={"core_ae_email": "delegated_by"})
        deleg["source"] = "delegated"

    frames = [f for f in (own, deleg) if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame(
            columns=["session_date", "slot_time", "batch_code", "status", "source", "delegated_by"]
        )
    out = pd.concat(frames, ignore_index=True)
    # if a session is both owned and delegated, the user's own row wins
    out = out.drop_duplicates(subset=["session_date", "slot_time", "batch_code"], keep="first")
    return out


# ---------------------------------------------------------------------------
# CROSS-VISIBILITY (new): within a Core AE's team, the Core AE and their
# Extended AEs all SEE each other's selections. Only the person who made a
# selection (owner_email) may change it.
# ---------------------------------------------------------------------------
@st.cache_data(ttl=30, show_spinner=False)
def get_team_selections(core_ae_email: str, from_date: date, to_date: date) -> pd.DataFrame:
    """
    Every selection tied to this Core AE's team for the period, from BOTH
    role tables. Returns one row per (date, slot, batch) with:
        status, owner_email, owner_role
    so the UI can show "claimed by X" and lock editing to the owner.
    """
    frames = []

    # Core AE's own picks
    core = get_selections_for_role("core_ae", core_ae_email, from_date, to_date)
    if not core.empty:
        core = core[["session_date", "slot_time", "batch_code", "status", "owner_email"]].copy()
        core["owner_role"] = "core_ae"
        frames.append(core)

    # Extended AEs paired to this Core AE
    ext_emails = extended_aes_for_core(core_ae_email)
    for ext in ext_emails:
        e = get_selections_for_role("extended_ae", ext, from_date, to_date)
        if not e.empty:
            e = e[["session_date", "slot_time", "batch_code", "status", "owner_email"]].copy()
            e["owner_role"] = "extended_ae"
            frames.append(e)

    if not frames:
        return pd.DataFrame(
            columns=["session_date", "slot_time", "batch_code", "status", "owner_email", "owner_role"]
        )

    out = pd.concat(frames, ignore_index=True)
    # a claimed status wins over Not Selected if two rows collide
    rank = {"Confirmed": 3, "Selected": 2, "Choosing": 1, "Not Selected": 0}
    out["_r"] = out["status"].map(lambda s: rank.get(s, 0))
    out = out.sort_values("_r", ascending=False).drop_duplicates(
        subset=["session_date", "slot_time", "batch_code"], keep="first"
    ).drop(columns=["_r"])
    return out


# ===========================================================================
# MOCK INTERVIEW / SLOT TASK ASSIGNMENT  ->  table: ae_slot_task
#
# A member's "own slots" are the CMIS rows where THEY are the email_id (their
# own teaching hours) — not the trainer sessions they observe.
#
# The DEFAULT task for each slot is DERIVED FROM CMIS ITSELF, via c_alias:
#   - c_alias starting 'plr'  (plr_mi1/2, plr_crd1/2, plr_mi_save, PLR_SAVE)
#                                                    -> mock_interview
#     (the whole plr* family are the placement / interview modules)
#   - anything else (a real course module: ISP, cs_ai, dp_*, java_core, ...)
#                                                    -> teaching
# So a slot is a Mock Interview because its CMIS course alias is a placement
# module, NOT because no override row exists. This matches the live data.
#
# A row in ae_slot_task exists ONLY when that CMIS-derived default has been
# overridden:
#   - automatically, when the member claims an Evaluation for that exact
#     (session_date, slot_time) — wired in from upsert_selection_for_role
#     via sync_slot_task_from_evaluation()
#   - manually, when the member picks another task for that slot on the
#     Calendar tab
# Clearing an override deletes the row, restoring whatever CMIS implies for
# that slot — nothing extra to do.
# ===========================================================================

# Full universe of task types a resolved slot can carry.
TASK_TYPES = [
    "mock_interview", "teaching",
    "evaluation", "training", "project_involvement", "other",
]
# What a member may MANUALLY pick from the Calendar dropdown. Picking the
# slot's own CMIS-derived default clears any override (see set_slot_task).
MANUAL_TASK_TYPES = [
    "mock_interview", "teaching",
    "training", "project_involvement", "other",
]
TASK_LABELS = {
    "mock_interview": "🎯 Mock Interview",
    "teaching": "🏫 Teaching",
    "evaluation": "🔎 Evaluation",
    "training": "📚 Training",
    "project_involvement": "🛠️ Project Involvement",
    "other": "✳️ Other",
}


def default_task_for_alias(c_alias: str | None) -> str:
    """The task a CMIS slot implies from its course alias.
    The whole plr* family (plr_mi1/2, plr_crd1/2, plr_mi_save, PLR_SAVE) are
    the placement / interview modules -> mock_interview.
    Everything else is a real teaching module -> teaching.
    """
    a = (c_alias or "").strip().lower()
    if a.startswith("plr"):
        return "mock_interview"
    return "teaching"


def role_for_email(email: str) -> str | None:
    df = get_user_roles()
    if df.empty or not email:
        return None
    m = df[df["email"].str.lower() == email.lower()]
    return m.iloc[0]["role"] if not m.empty else None


@st.cache_data(ttl=300, show_spinner=False)
def get_member_own_slots(member_email: str, from_date: date, to_date: date) -> pd.DataFrame:
    """This member's OWN rows in the CMIS view (their own teaching hours) —
    the slot grid the Mock Interview default applies to."""
    if not member_email:
        return pd.DataFrame()
    sql = text(
        f"""
        SELECT s_date, slot_name, slot_time, day_name, batch_code, m_code,
               c_alias, program_name
        FROM {CMIS_VIEW}
        WHERE email_id = :e AND s_date BETWEEN :a AND :b
        ORDER BY s_date, slot_time
        """
    )
    with cmis_engine().connect() as conn:
        return pd.read_sql(sql, conn, params={"e": member_email, "a": from_date, "b": to_date})


def get_slot_tasks(member_email: str, from_date: date, to_date: date) -> pd.DataFrame:
    """Only the OVERRIDE rows for this member/period (may be sparse)."""
    sql = text(
        """
        SELECT id, member_email, member_role, session_date, slot_time, slot_name,
               task_type, other_note, ref_selection_id, set_by, updated_on
        FROM ae_slot_task
        WHERE member_email = :e AND session_date BETWEEN :a AND :b
        """
    )
    try:
        with app_engine().connect() as conn:
            return pd.read_sql(sql, conn, params={"e": member_email, "a": from_date, "b": to_date})
    except Exception:
        return pd.DataFrame()


def resolve_member_calendar(member_email: str, from_date: date, to_date: date) -> pd.DataFrame:
    """
    Every one of this member's own CMIS slots for the window, with the
    resolved task merged in. The task for a slot is:
        override row (if any)  >  CMIS-derived default (from c_alias)
    Adds columns:
        _date, default_task, task_type, is_default,
        other_note, ref_selection_id, set_by
    where default_task is what CMIS implies and is_default is True when no
    override applies (task_type == default_task).
    """
    own = get_member_own_slots(member_email, from_date, to_date)
    if own.empty:
        return own
    own = own.copy()
    own["_date"] = pd.to_datetime(own["s_date"]).dt.date
    own["default_task"] = own["c_alias"].apply(default_task_for_alias)

    tasks = get_slot_tasks(member_email, from_date, to_date)
    by_key: dict[str, Any] = {}
    if not tasks.empty:
        for _, t in tasks.iterrows():
            k = f"{pd.to_datetime(t['session_date']).date()}|{t['slot_time']}"
            by_key[k] = t

    def _resolve(r) -> pd.Series:
        default = r["default_task"]
        t = by_key.get(f"{r['_date']}|{r['slot_time']}")
        if t is None:
            return pd.Series({"task_type": default, "is_default": True,
                               "other_note": None, "ref_selection_id": None,
                               "set_by": None})
        return pd.Series({"task_type": t["task_type"], "is_default": False,
                           "other_note": t["other_note"],
                           "ref_selection_id": t["ref_selection_id"],
                           "set_by": t["set_by"]})

    resolved = own.join(own.apply(_resolve, axis=1))
    return resolved


def set_slot_task(
    member_email: str,
    member_role: str,
    session_date: date,
    slot_time: str,
    slot_name: str | None,
    task_type: str,
    other_note: str | None = None,
    set_by: str | None = None,
    default_task: str | None = None,
) -> None:
    """
    Manually set (or reset) a slot's task. Picking the slot's own CMIS-derived
    default (pass it as `default_task`) deletes the override row so the slot
    falls back to what CMIS implies — that's the "clear" path. When
    default_task is not supplied we fall back to the legacy behaviour of
    treating 'mock_interview' as the clear value.
    """
    clear_value = default_task or "mock_interview"
    with app_engine().begin() as conn:
        existing = conn.execute(
            text(
                "SELECT id FROM ae_slot_task WHERE member_email = :e "
                "AND session_date = :d AND slot_time = :st LIMIT 1"
            ),
            {"e": member_email, "d": session_date, "st": slot_time},
        ).fetchone()

        if task_type == clear_value:
            if existing:
                conn.execute(text("DELETE FROM ae_slot_task WHERE id = :id"), {"id": existing[0]})
            return

        if existing:
            conn.execute(
                text(
                    "UPDATE ae_slot_task SET task_type=:tt, other_note=:on_, "
                    "ref_selection_id=NULL, set_by=:sb, updated_on=NOW() WHERE id=:id"
                ),
                {"tt": task_type, "on_": other_note, "sb": set_by, "id": existing[0]},
            )
        else:
            conn.execute(
                text(
                    "INSERT INTO ae_slot_task "
                    "(member_email, member_role, session_date, slot_time, slot_name, "
                    " task_type, other_note, set_by) "
                    "VALUES (:e,:r,:d,:st,:sn,:tt,:on_,:sb)"
                ),
                {"e": member_email, "r": member_role, "d": session_date, "st": slot_time,
                 "sn": slot_name, "tt": task_type, "on_": other_note, "sb": set_by},
            )


def sync_slot_task_from_evaluation(
    member_email: str,
    member_role: str,
    session_date: date,
    slot_time: str,
    is_claimed: bool,
    ref_selection_id: int | None,
) -> None:
    """
    Call this right after an evaluation claim is saved (status flips to/from
    Selected/Confirmed). Keeps ae_slot_task in sync with that claim:

      claimed    -> this slot's task becomes 'evaluation', linked via
                    ref_selection_id
      unclaimed  -> if the slot's task is currently 'evaluation' (i.e. it was
                    this claim that set it), fall back to the default by
                    deleting the row. A manual Training / Project / Other
                    pick on that slot is left untouched — only an
                    evaluation-driven override reverts automatically.
    """
    with app_engine().begin() as conn:
        existing = conn.execute(
            text(
                "SELECT id, task_type FROM ae_slot_task WHERE member_email = :e "
                "AND session_date = :d AND slot_time = :st LIMIT 1"
            ),
            {"e": member_email, "d": session_date, "st": slot_time},
        ).fetchone()

        if is_claimed:
            if existing:
                conn.execute(
                    text(
                        "UPDATE ae_slot_task SET task_type='evaluation', "
                        "ref_selection_id=:rid, set_by=:sb, updated_on=NOW() WHERE id=:id"
                    ),
                    {"rid": ref_selection_id, "sb": member_email, "id": existing[0]},
                )
            else:
                conn.execute(
                    text(
                        "INSERT INTO ae_slot_task "
                        "(member_email, member_role, session_date, slot_time, "
                        " task_type, ref_selection_id, set_by) "
                        "VALUES (:e,:r,:d,:st,'evaluation',:rid,:sb)"
                    ),
                    {"e": member_email, "r": member_role, "d": session_date, "st": slot_time,
                     "rid": ref_selection_id, "sb": member_email},
                )
        else:
            if existing and existing[1] == "evaluation":
                conn.execute(text("DELETE FROM ae_slot_task WHERE id = :id"), {"id": existing[0]})
