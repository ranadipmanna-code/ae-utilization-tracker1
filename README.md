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

The interface felt slow because almost every Streamlit rerun — every dropdown
change, checkbox tick or page turn — fired a burst of **uncached, one-at-a-time
database round-trips**. Pandas was never the bottleneck; network latency was.

Measured for a Core AE with ten Extended AEs:

| Call | Before | After (warm cache) |
|---|---|---|
| `db.ping()` (sidebar dots) | 2, uncached, every rerun | 0 |
| CMIS session fetch | 1, but the **entire horizon** (to Oct 2027) | 0; window-bounded |
| MI allocation, per Save | 22 (a CMIS + app query **per AE**) | 0 |
| `get_visible_selections` | 2, uncached | 0 |
| `get_my_mock_interview_claims` | 1, uncached | 0 |
| `get_team_selections` | 11 (one query **per team member**) | 0 |
| **Ordinary rerun** | **16 round-trips** | **0** |
| **After a Save** | **39 round-trips** | **~4, batched** |

At 80 ms latency that is ~1.3 s of dead time per click and ~3.1 s per save,
down to effectively nothing and ~0.3 s.

### What changed

1. **Killed the N+1 loops.** `get_team_selections` and the Mock Interview
   allocator both looped one query per person. Both now issue a single
   `IN (...)` query — `get_selections_for_emails()` and
   `get_members_own_slots()` — and split the result in pandas. Cost is now
   flat in team size instead of linear.
2. **Bounded the CMIS fetch.** The Sessions tab pulled every session the
   faculty have on record, then discarded ~95% with a pandas filter. A cheap
   `faculty_date_bounds()` MIN/MAX/COUNT probe now sizes the date pickers, the
   dates are chosen first, and `fetch_sessions_range_for_faculty()` fetches
   only that window. Every downstream pandas pass got proportionally cheaper
   for free.
3. **Cached the hot read paths** — `ping` (30 s), and `get_team_selections`,
   `get_visible_selections`, `get_mock_interview_assignments`,
   `get_my_mock_interview_claims`, `get_delegated_to_extended` (45 s).
4. **Stopped re-running allocation on every Save.** `st.cache_data.clear()`
   was discarding the CMIS pull too; the replacement `db.clear_app_caches()`
   clears only app-DB read caches. `ensure_mock_interviews_assigned` is
   deliberately *excluded* — it performs the full allocation, it is
   idempotent, and its own 10-minute TTL is the right cadence. Clearing it per
   save was what made saving feel like it had hung.
5. **Cut the element count.** A 25-row page of cards is ~100 Streamlit
   elements, all re-serialised on every rerun. The Sessions list now defaults
   to **⚡ Table (fast)** — one `st.data_editor`, one element, no pagination —
   with **🗂 Cards** still available from the toggle. The MI Pool tab uses the
   same approach.
6. **Vectorised the remaining row-wise passes** (key building, ownership,
   timestamps, slot merging), and state resolution short-circuits entirely
   when nothing in range is claimed yet. Worth ~20% on the merge at 5,000
   rows — real, but far smaller than items 1–5.

### Trade-offs

Read caches are 30–45 s, so a teammate's claim can take up to ~45 s to appear
if you don't touch anything. Any save clears them immediately, so your own
actions are always reflected at once. Lengthen the TTLs in `db.py` if you'd
rather trade freshness for even fewer queries.
