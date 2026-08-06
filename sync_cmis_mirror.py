#!/usr/bin/env python3
"""
sync_cmis_mirror.py  —  daily CMIS -> Anudip mirror refresh (cron job)

WHAT IT DOES
------------
1. Reads the next 30 days (today .. today+29) of sessions from the live CMIS
   view `upcoming_trainer_utilization_view`.
2. Upserts them into `Anudip_AE_Team.cmis_session_mirror` (idempotent — safe
   to run twice in a day).
3. Prunes the mirror: deletes anything with s_date < today (yesterday and
   older). Data leaving the window is NOT preserved here — the portal only
   ever needs today..today+9, and the 30-day mirror is just a sync buffer.

The portal reads ONLY from this mirror for session display and MI pooling.
The one exception is the admin email-reconciliation report, which still hits
live CMIS for the full roster (see db.get_cmis_directory).

WHY 30 / 10
-----------
Mirror holds 30 days; portal shows the next 10 (today..today+9). The extra 20
days are slack: if this job fails to run one morning, the visible 10-day window
is still fully populated for up to ~20 more days before a gap could appear.

CONFIG
------
Reads DB creds from environment variables so it can run head-less under cron,
independent of Streamlit's st.secrets. Set these in the cron environment or a
sourced .env:

    CMIS_HOST, CMIS_PORT, CMIS_USER, CMIS_PASSWORD, CMIS_DB
    APPDB_HOST, APPDB_PORT, APPDB_USER, APPDB_PASSWORD, APPDB_DB

CRON EXAMPLE (run 05:30 every day, log to file)
-----------------------------------------------
    30 5 * * *  cd /path/to/app && /usr/bin/env python3 sync_cmis_mirror.py \
                >> /var/log/cmis_mirror_sync.log 2>&1
"""
from __future__ import annotations

import hashlib
import os
import sys
from datetime import date, timedelta
from urllib.parse import quote_plus

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

CMIS_VIEW = "upcoming_trainer_utilization_view"
MIRROR_TABLE = "cmis_session_mirror"
WINDOW_DAYS = 30  # today .. today + (WINDOW_DAYS - 1)

# Columns pulled from CMIS -> stored in the mirror (order matters for upsert).
COLS = [
    "s_date", "email_id", "m_code", "f_name", "l_name", "time_duration",
    "day_name", "c_alias", "slot_name", "slot_time", "batch_code",
    "class_link", "program_name",
    # Contact info joined from anudip_cmis17.members on m_code = member_code.
    "mobile_no", "alt_contact_no", "member_email",
]


def _engine(prefix: str) -> Engine:
    host = os.environ[f"{prefix}_HOST"]
    port = os.environ.get(f"{prefix}_PORT", "3306")
    user = quote_plus(os.environ[f"{prefix}_USER"])
    pwd = quote_plus(os.environ[f"{prefix}_PASSWORD"])
    db = os.environ[f"{prefix}_DB"]
    url = f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}?charset=utf8mb4"
    return create_engine(url, pool_pre_ping=True, future=True)


def _session_key(email: str, s_date, slot_time, batch_code) -> str:
    """MUST match the natural key used everywhere else in the app:
    trainer_email | ISO date | slot_time | batch_code, then sha256."""
    d = pd.to_datetime(s_date).date().isoformat()
    natural = f"{str(email).strip().lower()}|{d}|{slot_time or ''}|{batch_code or ''}"
    return hashlib.sha256(natural.encode("utf-8")).hexdigest()


def fetch_window(cmis: Engine, lo: date, hi: date) -> pd.DataFrame:
    sql = text(
        f"""
        SELECT v.s_date, v.email_id, v.m_code, v.f_name, v.l_name,
               v.time_duration, v.day_name, v.c_alias, v.slot_name,
               v.slot_time, v.batch_code, v.class_link, v.program_name,
               -- Trainer contact info from the members table, matched on the
               -- trainer's member code. NULLIF drops the placeholder 0s so a
               -- real alt_contact_no can be used as fallback in the app.
               NULLIF(m.mobile_no, 0)      AS mobile_no,
               NULLIF(m.alt_contact_no, 0) AS alt_contact_no,
               m.email_id                  AS member_email
        FROM {CMIS_VIEW} v
        LEFT JOIN members m ON m.member_code = v.m_code
        WHERE v.s_date BETWEEN :lo AND :hi
          AND v.email_id IS NOT NULL AND TRIM(v.email_id) <> ''
        ORDER BY v.s_date, v.slot_time
        """
    )
    with cmis.connect() as conn:
        return pd.read_sql(sql, conn, params={"lo": lo, "hi": hi})


def upsert(appdb: Engine, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    df = df.copy()
    df["session_key"] = [
        _session_key(r.email_id, r.s_date, r.slot_time, r.batch_code)
        for r in df.itertuples(index=False)
    ]
    # Collapse any duplicate natural keys inside the batch (last wins) so the
    # single INSERT statement never carries two rows with the same PK.
    df = df.drop_duplicates(subset="session_key", keep="last")

    insert_cols = ["session_key"] + COLS
    placeholders = ", ".join(f":{c}" for c in insert_cols)
    updates = ", ".join(f"{c}=VALUES({c})" for c in COLS)  # PK excluded
    stmt = text(
        f"""
        INSERT INTO {MIRROR_TABLE} ({", ".join(insert_cols)})
        VALUES ({placeholders})
        ON DUPLICATE KEY UPDATE {updates}, synced_at=CURRENT_TIMESTAMP
        """
    )
    # Build records, then scrub any NaN/NaT to None. A DataFrame .where()
    # alone leaves numpy float NaN in all-null columns (e.g. alt_contact_no
    # when no row in the batch has one), and MySQL rejects NaN outright
    # ("nan can not be used with MySQL"). Cleaning per-value after to_dict
    # guarantees every NaN becomes a real SQL NULL.
    records = df[insert_cols].to_dict("records")
    for _rec in records:
        for _k, _v in _rec.items():
            if _v is not None and _v != _v:  # NaN is the only value where v != v
                _rec[_k] = None
            elif pd.isna(_v):                # catches NaT and pandas NA too
                _rec[_k] = None
    with appdb.begin() as conn:
        conn.execute(stmt, records)
    return len(records)


def prune(appdb: Engine, cutoff: date) -> int:
    """Drop everything older than `cutoff` (i.e. before today)."""
    stmt = text(f"DELETE FROM {MIRROR_TABLE} WHERE s_date < :cutoff")
    with appdb.begin() as conn:
        result = conn.execute(stmt, {"cutoff": cutoff})
        return result.rowcount or 0


def reconcile(appdb: Engine, lo: date, hi: date, live_keys: set[str]) -> int:
    """Delete mirror rows INSIDE the fetched window that no longer exist in
    live CMIS -- a session that gets cancelled, rescheduled, or moved after
    being synced once used to leave a permanent phantom row behind, since
    upsert() only ever adds/updates and the old prune() only removed rows
    that had aged into the past. This is what was causing the mirror to
    hold MORE rows than live CMIS for the same date range (confirmed via a
    same-window COUNT(*) on both sides: mirror had 616 extra rows).

    Only rows in [lo, hi] are considered -- this never touches anything
    outside the window that was actually fetched, so a partial/narrower
    sync run can't wrongly delete dates it didn't just refresh.
    """
    if not live_keys:
        # An empty CMIS pull almost certainly means something's wrong with
        # the source query/connection, not that every session vanished --
        # refuse to wipe the whole window on a zero-row fetch.
        return 0
    sql = text(
        f"SELECT session_key FROM {MIRROR_TABLE} WHERE s_date BETWEEN :lo AND :hi"
    )
    with appdb.connect() as conn:
        existing = {r[0] for r in conn.execute(sql, {"lo": lo, "hi": hi})}
    orphaned = existing - live_keys
    if not orphaned:
        return 0
    del_stmt = text(f"DELETE FROM {MIRROR_TABLE} WHERE session_key = :k")
    with appdb.begin() as conn:
        conn.execute(del_stmt, [{"k": k} for k in orphaned])
    return len(orphaned)


def main() -> int:
    today = date.today()
    lo, hi = today, today + timedelta(days=WINDOW_DAYS - 1)

    cmis = _engine("CMIS")
    appdb = _engine("APPDB")

    print(f"[sync] window {lo} .. {hi}  ({WINDOW_DAYS} days)")
    src = fetch_window(cmis, lo, hi)
    print(f"[sync] fetched {len(src)} rows from CMIS")

    n_up = upsert(appdb, src)
    print(f"[sync] upserted {n_up} rows into {MIRROR_TABLE}")

    live_keys = {
        _session_key(r.email_id, r.s_date, r.slot_time, r.batch_code)
        for r in src.itertuples(index=False)
    } if not src.empty else set()
    n_orphaned = reconcile(appdb, lo, hi, live_keys)
    print(f"[sync] removed {n_orphaned} orphaned rows no longer in live CMIS")

    n_pruned = prune(appdb, cutoff=today)
    print(f"[sync] pruned {n_pruned} stale rows (s_date < {today})")

    print("[sync] done")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 — cron wants a nonzero exit + log line
        print(f"[sync] FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
