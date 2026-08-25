#!/usr/bin/env python3
"""
snapshot_cmis_directory.py — refresh the App-DB copy of the CMIS trainer
directory used by the admin email-reconciliation report.

The report needs the FULL CMIS roster across ALL dates (not the 30-day
session mirror). Rather than give Streamlit live CMIS creds, this runs in
GitHub Actions and writes one row per trainer into
Anudip_AE_Team.cmis_trainer_directory. The app reads that table.

Idempotent: truncate + reinsert in one transaction.

Env vars (same names as sync_cmis_mirror.py):
    CMIS_HOST CMIS_PORT CMIS_USER CMIS_PASSWORD CMIS_DB
    APPDB_HOST APPDB_PORT APPDB_USER APPDB_PASSWORD APPDB_DB
"""
from __future__ import annotations

import os
import sys
from urllib.parse import quote_plus

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

CMIS_VIEW = "trainer_utilization_view"
SNAP_TABLE = "cmis_trainer_directory"


def _engine(prefix: str) -> Engine:
    host = os.environ[f"{prefix}_HOST"]
    port = os.environ.get(f"{prefix}_PORT", "3306")
    user = quote_plus(os.environ[f"{prefix}_USER"])
    pwd = quote_plus(os.environ[f"{prefix}_PASSWORD"])
    db = os.environ[f"{prefix}_DB"]
    url = f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}?charset=utf8mb4"
    return create_engine(url, pool_pre_ping=True, future=True)


def fetch_directory(cmis: Engine) -> pd.DataFrame:
    sql = text(
        f"""
        SELECT LOWER(TRIM(email_id))                    AS cmis_email,
               LOWER(TRIM(CONCAT(f_name, ' ', l_name))) AS cmis_full_name,
               COUNT(*)                                 AS slot_count,
               MIN(s_date)                              AS first_slot,
               MAX(s_date)                              AS last_slot
        FROM {CMIS_VIEW}
        WHERE email_id IS NOT NULL AND TRIM(email_id) <> ''
        GROUP BY 1, 2
        """
    )
    with cmis.connect() as conn:
        return pd.read_sql(sql, conn)


def replace_snapshot(appdb: Engine, df: pd.DataFrame) -> int:
    if df.empty:
        # A zero-row CMIS pull almost certainly means a source/connection
        # problem — refuse to wipe a good snapshot on it.
        print("[snap] CMIS returned 0 rows — leaving existing snapshot intact.")
        return 0
    records = df.to_dict("records")
    for rec in records:
        for k, v in rec.items():
            if v is not None and v != v:      # NaN
                rec[k] = None
            elif pd.isna(v):                  # NaT / NA
                rec[k] = None
    stmt = text(
        f"""
        INSERT INTO {SNAP_TABLE}
            (cmis_email, cmis_full_name, slot_count, first_slot, last_slot)
        VALUES (:cmis_email, :cmis_full_name, :slot_count, :first_slot, :last_slot)
        """
    )
    with appdb.begin() as conn:
        conn.execute(text(f"DELETE FROM {SNAP_TABLE}"))
        conn.execute(stmt, records)
    return len(records)


def main() -> int:
    cmis = _engine("CMIS")
    appdb = _engine("APPDB")
    df = fetch_directory(cmis)
    print(f"[snap] fetched {len(df)} trainer rows from CMIS")
    n = replace_snapshot(appdb, df)
    print(f"[snap] wrote {n} rows into {SNAP_TABLE}")
    print("[snap] done")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[snap] FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
