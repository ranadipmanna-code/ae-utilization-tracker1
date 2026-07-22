"""
Quick connection self-test — run BEFORE launching the app:

    python test_connection.py

Reads .streamlit/secrets.toml directly (without Streamlit) and checks that
both databases are reachable and the expected tables/views exist.
"""
import sys
import tomllib
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text

SECRETS = Path(".streamlit/secrets.toml")


def load_secrets():
    if not SECRETS.exists():
        sys.exit("❌ .streamlit/secrets.toml not found. Copy secrets.toml.example and fill it in.")
    with open(SECRETS, "rb") as f:
        return tomllib.load(f)


def engine_for(cfg):
    pwd = quote_plus(str(cfg["password"]))  # escape special chars in password
    user = quote_plus(str(cfg["user"]))
    url = (f"mysql+pymysql://{user}:{pwd}"
           f"@{cfg['host']}:{cfg['port']}/{cfg['database']}?charset=utf8mb4")
    return create_engine(url, pool_pre_ping=True)


def main():
    s = load_secrets()

    # CMIS
    print("Testing CMIS (read-only)…")
    try:
        eng = engine_for(s["cmis"])
        with eng.connect() as c:
            n = c.execute(text("SELECT COUNT(*) FROM upcoming_trainer_utilization_view")).scalar()
            print(f"  ✅ CMIS reachable. upcoming_trainer_utilization_view has {n} rows.")
    except Exception as e:
        print(f"  ❌ CMIS failed: {e}")

    # App DB
    print("Testing App DB (read/write)…")
    try:
        eng = engine_for(s["appdb"])
        with eng.connect() as c:
            for tbl in ["core_ae_faculty_map", "extended_ae_session_selection",
                        "session_highlight_flags", "user_roles", "weekly_ae_summary"]:
                cnt = c.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
                print(f"  ✅ {tbl}: {cnt} rows")
    except Exception as e:
        print(f"  ❌ App DB failed: {e}")


if __name__ == "__main__":
    main()
