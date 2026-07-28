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
        SELECT s_date, email_id, m_code, f_name, l_name, time_duration,
               day_name, c_alias, slot_name, slot_time, batch_code,
               class_link, program_name
        FROM {CMIS_VIEW}
        WHERE s_date BETWEEN :lo AND :hi
          AND email_id IS NOT NULL AND TRIM(email_id) <> ''
        ORDER BY s_date, slot_time
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
    records = df[insert_cols].where(pd.notnull(df[insert_cols]), None).to_dict("records")
    with appdb.begin() as conn:
        conn.execute(stmt, records)
    return len(records)


def prune(appdb: Engine, cutoff: date) -> int:
    """Drop everything older than `cutoff` (i.e. before today)."""
    stmt = text(f"DELETE FROM {MIRROR_TABLE} WHERE s_date < :cutoff")
    with appdb.begin() as conn:
        result = conn.execute(stmt, {"cutoff": cutoff})
        return result.rowcount or 0


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
