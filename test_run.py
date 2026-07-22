"""
End-to-end test run against the LIVE databases.

Exercises the whole chain:
  1. Both DB connections
  2. Seeded reference data (user_roles, core_ae_faculty_map)
  3. CMIS session fetch for a real Core AE's faculty
  4. Claim a session      -> extended_ae_session_selection + session_highlight_flags
  5. Evaluate a session   -> session_evaluation
  6. Weekly summary recompute -> weekly_ae_summary
  7. CLEANUP: every row this test wrote is deleted again

Safe to run: all test rows use the marker below and are removed at the end,
even if a step fails.

Run:
  docker run --rm -v "${PWD}:/app" -w /app python:3.11-slim bash -c \
    "pip install -q -r requirements.txt && python test_run.py"
"""
import sys
import tomllib
import traceback
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
from sqlalchemy import create_engine, text

SECRETS = Path(".streamlit/secrets.toml")
VIEW = "upcoming_trainer_utilization_view"

# Everything this test writes is tagged with this so cleanup is exact.
TEST_EMAIL = "zz.testrun@anudip.invalid"

PASS, FAIL = "  \033[92m✅ PASS\033[0m", "  \033[91m❌ FAIL\033[0m"
results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(f"{PASS if ok else FAIL}  {name}" + (f"  — {detail}" if detail else ""))
    return ok


def eng(section):
    cfg = tomllib.load(open(SECRETS, "rb"))[section]
    url = (f"mysql+pymysql://{quote_plus(str(cfg['user']))}:{quote_plus(str(cfg['password']))}"
           f"@{cfg['host']}:{cfg['port']}/{cfg['database']}?charset=utf8mb4")
    return create_engine(url, pool_pre_ping=True)


def cleanup(app):
    """Remove every row this test created."""
    with app.begin() as c:
        for tbl, col in [
            ("extended_ae_session_selection", "extended_ae_email"),
            ("session_highlight_flags", "extended_ae_email"),
            ("session_evaluation", "evaluator_email"),
        ]:
            try:
                c.execute(text(f"DELETE FROM {tbl} WHERE {col} = :e"), {"e": TEST_EMAIL})
            except Exception:
                pass


def main():
    if not SECRETS.exists():
        sys.exit("❌ .streamlit/secrets.toml not found.")

    print("=" * 70)
    print("AE UTILIZATION TRACKER — END-TO-END TEST RUN")
    print("=" * 70)

    cmis, app = eng("cmis"), eng("appdb")

    # ---------------------------------------------------------------- 1. conns
    print("\n[1] DATABASE CONNECTIONS")
    try:
        with cmis.connect() as c:
            n = c.execute(text(f"SELECT COUNT(*) FROM {VIEW}")).scalar()
        check("CMIS reachable", True, f"{n:,} sessions in view")
    except Exception as e:
        check("CMIS reachable", False, str(e)[:60]); return
    try:
        with app.connect() as c:
            c.execute(text("SELECT 1"))
        check("App DB reachable", True)
    except Exception as e:
        check("App DB reachable", False, str(e)[:60]); return

    # ------------------------------------------------------------ 2. ref data
    print("\n[2] SEEDED REFERENCE DATA")
    with app.connect() as c:
        roles = pd.read_sql(text("SELECT role, COUNT(*) n FROM user_roles GROUP BY role"), c)
        fmap = pd.read_sql(text("SELECT COUNT(*) n, COUNT(DISTINCT core_ae_email) c FROM core_ae_faculty_map"), c)
    role_counts = dict(zip(roles["role"], roles["n"])) if not roles.empty else {}
    check("user_roles populated", sum(role_counts.values()) > 0, str(role_counts))
    check("core_ae_faculty_map populated",
          int(fmap.iloc[0]["n"]) > 0,
          f"{int(fmap.iloc[0]['n'])} rows / {int(fmap.iloc[0]['c'])} Core AEs")

    # ------------------------------------------------- 3. pick a real session
    print("\n[3] CMIS SESSION FETCH")
    with app.connect() as c:
        row = pd.read_sql(text(
            "SELECT core_ae_email, faculty_1 FROM core_ae_faculty_map "
            "WHERE faculty_1 IS NOT NULL LIMIT 1"), c)
    if row.empty:
        check("found a Core AE with faculty", False); return
    core_ae = row.iloc[0]["core_ae_email"]
    faculty = row.iloc[0]["faculty_1"]
    check("found a Core AE with faculty", True, f"{core_ae} -> {faculty}")

    with cmis.connect() as c:
        sess = pd.read_sql(text(
            f"SELECT s_date, slot_time, batch_code, m_code, f_name, l_name, "
            f"program_name, email_id FROM {VIEW} WHERE email_id = :e "
            f"ORDER BY s_date LIMIT 1"), c, params={"e": faculty})
    if sess.empty:
        check("CMIS returns sessions for that faculty", False, "no rows"); return
    s = sess.iloc[0]
    sdate = pd.to_datetime(s["s_date"]).date()
    check("CMIS returns sessions for that faculty", True,
          f"{s['f_name']} {s['l_name']} on {sdate} {s['slot_time']}")

    try:
        # ------------------------------------------------------- 4. claim path
        print("\n[4] CLAIM A SESSION  (write path)")
        with app.begin() as c:
            c.execute(text(
                "INSERT INTO extended_ae_session_selection "
                "(extended_ae_email, session_date, slot_time, module, batch_code, status) "
                "VALUES (:e,:d,:st,:m,:b,'Selected')"),
                {"e": TEST_EMAIL, "d": sdate, "st": s["slot_time"],
                 "m": s["m_code"], "b": s["batch_code"]})
            c.execute(text(
                "INSERT INTO session_highlight_flags "
                "(session_date, slot_time, batch_code, core_ae_email, extended_ae_email, is_highlighted) "
                "VALUES (:d,:st,:b,:c,:e,1)"),
                {"d": sdate, "st": s["slot_time"], "b": s["batch_code"],
                 "c": core_ae, "e": TEST_EMAIL})
        with app.connect() as c:
            got = c.execute(text(
                "SELECT status FROM extended_ae_session_selection WHERE extended_ae_email=:e"),
                {"e": TEST_EMAIL}).fetchone()
            flag = c.execute(text(
                "SELECT is_highlighted FROM session_highlight_flags WHERE extended_ae_email=:e"),
                {"e": TEST_EMAIL}).fetchone()
        check("selection row written", got is not None and got[0] == "Selected",
              f"status={got[0] if got else None}")
        check("highlight flag written", flag is not None and int(flag[0]) == 1)

        # ---------------------------------------------------- 5. evaluation
        print("\n[5] SUBMIT AN EVALUATION  (write path)")
        sid = f"{faculty}|{sdate}|{s['slot_time']}|{s['batch_code'] or ''}"
        try:
            with app.begin() as c:
                c.execute(text(
                    "INSERT INTO session_evaluation "
                    "(evaluator_email, evaluator_role, session_id, trainer_name, trainer_email, "
                    " session_date, slot_time, batch_code, module, program_name, "
                    " duration_minutes, rating, remarks, status) "
                    "VALUES (:e,'core_ae',:sid,:tn,:te,:d,:st,:b,:m,:p,30,4,'Test run — auto-deleted','Completed')"),
                    {"e": TEST_EMAIL, "sid": sid,
                     "tn": f"{s['f_name']} {s['l_name']}", "te": faculty,
                     "d": sdate, "st": s["slot_time"], "b": s["batch_code"],
                     "m": s["m_code"], "p": s["program_name"]})
            with app.connect() as c:
                ev = c.execute(text(
                    "SELECT rating, duration_minutes FROM session_evaluation WHERE evaluator_email=:e"),
                    {"e": TEST_EMAIL}).fetchone()
            check("evaluation row written", ev is not None and int(ev[0]) == 4,
                  f"rating={ev[0]}, mins={ev[1]}" if ev else "")
        except Exception as e:
            check("evaluation row written", False,
                  "session_evaluation table missing? run create_evaluation_table.sql")
            print(f"      {str(e)[:90]}")

        # ------------------------------------------------- 6. weekly summary
        print("\n[6] WEEKLY SUMMARY RECOMPUTE")
        ws = sdate - timedelta(days=sdate.weekday())
        we = ws + timedelta(days=6)
        with app.connect() as c:
            total = c.execute(text(
                "SELECT COUNT(*) FROM session_highlight_flags WHERE core_ae_email=:c "
                "AND session_date BETWEEN :a AND :b AND is_highlighted=1"),
                {"c": core_ae, "a": ws, "b": we}).scalar()
            selected = c.execute(text(
                "SELECT COUNT(DISTINCT s.id) FROM extended_ae_session_selection s "
                "JOIN session_highlight_flags f ON f.session_date=s.session_date "
                " AND f.slot_time=s.slot_time AND (f.batch_code <=> s.batch_code) "
                "WHERE f.core_ae_email=:c AND s.session_date BETWEEN :a AND :b "
                " AND s.status IN ('Selected','Confirmed')"),
                {"c": core_ae, "a": ws, "b": we}).scalar()
        check("summary counts computable", total is not None and total >= 1,
              f"week {ws}: available={total}, selected={selected}")

    finally:
        # ---------------------------------------------------------- 7. cleanup
        print("\n[7] CLEANUP")
        cleanup(app)
        with app.connect() as c:
            left = 0
            for tbl, col in [("extended_ae_session_selection", "extended_ae_email"),
                             ("session_highlight_flags", "extended_ae_email"),
                             ("session_evaluation", "evaluator_email")]:
                try:
                    left += c.execute(text(f"SELECT COUNT(*) FROM {tbl} WHERE {col}=:e"),
                                      {"e": TEST_EMAIL}).scalar() or 0
                except Exception:
                    pass
        check("all test rows removed", left == 0, f"{left} leftover")

    # ------------------------------------------------------------- verdict
    print("\n" + "=" * 70)
    ok = sum(1 for _, o in results if o)
    print(f"RESULT: {ok}/{len(results)} checks passed")
    if ok == len(results):
        print("🎉 Everything works end-to-end — connections, reads, writes, cleanup.")
    else:
        print("⚠️  Some checks failed — see above.")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
