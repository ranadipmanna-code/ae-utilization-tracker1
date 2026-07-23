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

4. Create the Mock Interview pool table (one time):

       # phpMyAdmin -> Anudip_AE_Team -> SQL tab -> paste create_mi_pool.sql -> Go

5. Seed the roster (writes user_roles + core_ae_faculty_map, one time):

       python seed_appdb.py

6. Run:

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


## Mock Interview pool (MI Pool tab)

Models the escalation chain from the `MI Details New` sheet. An interview
nobody picks up falls one rung at a time:

| Rung | Who acts | Sheet column | Stored in |
|---|---|---|---|
| 1 | Extended AE | `Status` (Accepted / Rejected) | `mock_interview_assignment.status` |
| 2 | Core AE | `AE Status` ("Taken by …") | `mi_pool_claim` (`claim_role='core_ae'`) |
| 3 | Faculty | `Taken by Faculty` = Yes | `mi_pool_claim` (`claim_role='faculty'`) |

State is derived, never stored twice — `mi_pool.build_pool()` walks the ladder
from the bottom up: whoever last accepted holds it, otherwise it sits open at
the rung below whoever last passed.

The tab is visible to **all three roles**. A Core AE can now see what the
Extended AE team has and hasn't taken, which previously wasn't surfaced
anywhere.

### Interviews are atomic

CMIS stores a two-hour Mock Interview as four consecutive 30-minute rows. The
sheet stores it as one row (16:00 → 18:00) assigned to one person, and that is
now what the code does too: `mi_pool.merge_mi_blocks()` merges contiguous slots
into one block before anything is allocated.

This fixed a real bug. Allocation used to iterate the raw CMIS rows, which
collided with the one-MI-per-AE-per-day spread rule: the moment an AE took the
first half-hour, that rule locked them out of the rest of the day, forcing the
remaining fragments onto *different* AEs. One interview routinely ended up
shared between three or four people. Blocks make that structurally impossible.

Contiguity is checked properly — two separate interviews for the same batch on
the same day (10:00–11:00 and 15:00–16:00) stay separate.

## Filtering

The Sessions tab's **Show** dropdown gained:

- `Extended AE claimed sessions`
- `Core AE claimed sessions`
- `Mock Interviews only`

The MI Pool tab has its own Show filter covering every rung, open and claimed.

## Performance notes

The lag had three causes, in descending order of impact:

1. **`st.cache_data.clear()` after every save.** This threw away the CMIS
   session pull too, so the next rerun re-queried CMIS from scratch — seconds,
   not milliseconds. Replaced with `db.clear_app_caches()`, which clears only
   the app-DB caches a write can actually invalidate and leaves the CMIS reads
   warm on their 5-minute TTL. This is the big one.
2. **Widget count.** 40 cards/page meant ~120 Streamlit elements. Page size is
   now 25, `Duration` is formatted only for visible rows, and the MI Pool tab
   uses a single `st.data_editor` instead of per-row cards.
3. **Row-wise `.apply()` passes.** Key building, ownership, timestamps and slot
   merging are now vectorised, and state resolution short-circuits entirely
   when nothing in range is claimed yet. Worth roughly 20% on the merge at
   5,000 rows — real, but much smaller than (1).
