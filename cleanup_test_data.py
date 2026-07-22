"""
Clear out test data created during manual testing.

Shows you what's there FIRST, asks for confirmation, then deletes.
Only touches the transactional tables — never user_roles or
core_ae_faculty_map (your seeded reference data).

Run:
  docker run --rm -it -v "${PWD}:/app" -w /app python:3.11-slim bash -c \
    "pip install -q -r requirements.txt && python cleanup_test_data.py"
"""
import sys
import tomllib
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
from sqlalchemy import create_engine, text

SECRETS = Path(".streamlit/secrets.toml")

TABLES = [
    "extended_ae_session_selection",
    "session_highlight_flags",
    "session_evaluation",
    "weekly_ae_summary",
]


def eng():
    cfg = tomllib.load(open(SECRETS, "rb"))["appdb"]
    url = (f"mysql+pymysql://{quote_plus(str(cfg['user']))}:{quote_plus(str(cfg['password']))}"
           f"@{cfg['host']}:{cfg['port']}/{cfg['database']}?charset=utf8mb4")
    return create_engine(url)


def main():
    if not SECRETS.exists():
        sys.exit("❌ .streamlit/secrets.toml not found.")
    e = eng()

    print("=" * 64)
    print("CURRENT CONTENTS OF THE TRANSACTIONAL TABLES")
    print("=" * 64)
    counts = {}
    with e.connect() as c:
        for t in TABLES:
            try:
                n = c.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() or 0
            except Exception as ex:
                print(f"  {t}: (missing — {str(ex)[:40]})")
                continue
            counts[t] = n
            print(f"\n  {t}: {n} row(s)")
            if n:
                df = pd.read_sql(text(f"SELECT * FROM {t} LIMIT 10"), c)
                print(df.to_string(index=False, max_colwidth=28))

    total = sum(counts.values())
    if total == 0:
        print("\n✅ Already clean — nothing to delete.")
        return

    print("\n" + "=" * 64)
    print(f"About to DELETE all {total} row(s) from: {', '.join(counts)}")
    print("Reference data (user_roles, core_ae_faculty_map) will NOT be touched.")
    print("=" * 64)
    ans = input("Type 'yes' to confirm: ").strip().lower()
    if ans != "yes":
        print("Aborted — nothing deleted.")
        return

    with e.begin() as c:
        for t in counts:
            c.execute(text(f"DELETE FROM {t}"))
            print(f"  cleared {t}")

    with e.connect() as c:
        left = sum((c.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() or 0) for t in counts)
    print(f"\n{'✅ All test data removed.' if left == 0 else f'⚠️  {left} rows remain.'}")


if __name__ == "__main__":
    main()
