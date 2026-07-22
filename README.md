# AE Utilization Tracker — Streamlit

Reads faculty sessions from the CMIS database (read-only) and reads/writes app
state to the Anudip_AE_Team database (the hackathon tables).

## Setup

1. Install deps:

       pip install -r requirements.txt

2. Create secrets:

       cp .streamlit/secrets.toml.example .streamlit/secrets.toml
       # then edit .streamlit/secrets.toml and fill in the two DB passwords

3. Test the connections:

       python test_connection.py

4. Seed the roster (writes user_roles + core_ae_faculty_map, one time):

       python seed_appdb.py

5. Run:

       streamlit run app.py

## Databases

- **CMIS** (read-only): `upcoming_trainer_utilization_view` — faculty sessions,
  and also the source of each member's own slot grid (rows where `email_id`
  is that member) used by the Mock Interview default.
- **App DB** (read/write): `core_ae_faculty_map`, `extended_ae_session_selection`,
  `core_ae_session_selection`, `session_highlight_flags`, `user_roles`,
  `weekly_ae_summary`, `core_ae_evaluation`, `extended_ae_evaluation`,
  `ae_extae`, `ae_slot_task`.

Yellow = available for observation. Green = claimed (Selected/Confirmed).

### Mock Interview default (Calendar tab)

Run `create_ae_slot_task.sql` once (same way as `create_role_tables.sql`) to
add the `ae_slot_task` table. Every slot in a member's own CMIS schedule
defaults to **Mock Interview**. It's automatically replaced with
**Evaluation** the moment they claim a CMIS session for that exact
`(session_date, slot_time)` on the Sessions tab, and reverts back the moment
that claim is undone. Members can also manually set a slot to **Training**,
**Project Involvement**, or **Other** (with a note) from the new **Calendar**
tab — clearing that pick restores the Mock Interview default too.

## Deploy to Streamlit Cloud

Push this folder to GitHub (secrets.toml is gitignored). In Streamlit Cloud,
paste the contents of your secrets.toml into the app's **Secrets** box. The two
Anudip DBs must allow inbound connections from Streamlit Cloud's IPs.
