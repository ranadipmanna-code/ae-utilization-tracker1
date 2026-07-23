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


## Fixes — MI Pool interface review

### 1. `config.toml` was in a location Streamlit never reads  ← root cause

`.streamlit/` existed but held only `secrets.toml.example`; `config.toml` sat
at the **repo root**. Streamlit only reads `.streamlit/config.toml`, so
`base = "light"` never took effect. That is why the data grid rendered dark
inside a light page — the app's own CSS was light, but Streamlit's internal
theme was not. Moved to `.streamlit/config.toml`.

This also affected `primaryColor` and every other theme key, so widget accents
across the whole app were falling back to Streamlit defaults.

### 2. MI Pool now uses cards, not a data grid

The grid had three faults at once: thirteen columns pushed past the right edge
and collided with Streamlit's own toolbar; most columns read `—` on a freshly
loaded pool; and `st.data_editor` renders to a canvas that ignores the app's
CSS theme. It now uses the same `.slot-head` / `.scard` / `.pill` language as
the Sessions tab, grouped by day and paginated at 20.

Rungs appear on a card only once someone has acted on them, so an untouched
interview shows no filler.

### 3. MI Pool no longer depends on the Sessions tab

It read `st.session_state['shared_from']`, which `_sessions_tab` sets only
**after four possible early returns**. A Core AE with no mapped faculty, or no
sessions in range, left this tab permanently stuck on "open the Sessions tab
first". It now has its own From/To pickers.

### 4. MI Pool runs the allocator itself

`build_pool()` only ever *read* `mock_interview_assignment`. If the Sessions
tab hadn't run `ensure_mock_interviews_assigned()` for that window, every row
showed *Extended AE / Open / —* and looked like broken auto-assignment. The tab
now ensures allocation for its own date range first.

### 5. Stale 30-minute assignment rows — needs a one-time cleanup

Before Mock Interviews became atomic blocks, the allocator wrote **one row per
30-minute fragment**. Those keys can never match a merged block key:

    block key            2026-07-23|10:30 AM - 12:30 PM|ANP-D7035
    stale fragment key   2026-07-23|10:30 AM - 11:00 AM|ANP-D7035   -> no match

So old assignments look invisible and get re-allocated on top of. Check and
clean with the query at the bottom of `create_mi_pool.sql` (it deletes only
`source = 'auto'` rows; anything a person chose is left alone).

### 6. `create_mi_pool.sql` was missing from the repo

Without `mi_pool_claim`, reads fall back to empty but **"Take as Core AE" and
"Hand to faculty" raise**. The file is restored, and those buttons now catch
the missing-table error and say which script to run.

### 7. Mock Interviews separated from class observations

In the Sessions list the two were interleaved. MI rows are now tagged
(`_is_mi`), sorted into their own contiguous section — so a section never
splits across a page — under a **🎯 Mock Interviews** header, with a warm tint
and a `🎯 MI` badge reusing the Calendar tab's existing Mock Interview palette.
A fifth stat tile counts them, and the tile grid reflows at 1100px so five
tiles don't crush.

### 8. Missing `timedelta` import in `mi_pool.py`

Would have raised `NameError` on first render of the new date pickers.


## Theme — Anudip brand

Both modes are derived from five values at the top of `app.py`:

```python
BRAND = {
    "orange":      "#ee7623",   # primary — CTAs, "mine", focus
    "orange_dark": "#c85f14",
    "orange_lite": "#f7913f",   # dark mode needs a lighter orange to read
    "navy":        "#14293f",   # headings and body text on light
    "navy_deep":   "#0d1620",   # dark mode canvas
}
```

**These were matched by eye from the live anudip.org, not sampled from its
stylesheet** — the page's CSS isn't reachable programmatically. If Anudip has
an official brand sheet, replace these five values and everything follows;
nothing else in the file needs editing. Keep `.streamlit/config.toml` in step,
since it themes the widgets and data grid that CSS cannot reach.

Dark mode uses a navy canvas rather than neutral black, so the orange still
reads as a brand colour rather than as a warning.

### Hue assignment

Four states appear side by side in the session list, so none may share a hue:

| State | Light | Dark |
|---|---|---|
| Mine | Anudip orange `#ee7623` | `#f7913f` |
| Open / available | blue `#2e7cb8` | `#4e9bc9` |
| Teammate's | green `#2e9e63` | `#3fb87c` |
| Mock Interview | violet `#7c4dbe` | `#a87be0` |

Mock Interview moved **off** orange precisely because orange became the brand
accent — leaving it there would have made "mine" and "MI" indistinguishable.
The Calendar's "project" type inherited the old teal in exchange. Closest hue
pair is 58° apart in light, 52° in dark.

### Accessibility

Every text/background pair in both modes passes WCAG AA (4.5:1). Two findings
worth recording, because they constrain how the orange may be used:

- **White on Anudip orange is only 2.90:1 — it fails.** Navy on orange is
  5.11:1, so `on_accent` is navy. Any new orange-filled element must use
  `{t['on_accent']}`, never `#fff`.
- **Orange as *text* on white is 2.90:1 — also fails.** `accent_text`
  (`#ad4f0f`) is a darkened orange at 5.38:1 for when the accent has to be the
  text rather than the fill.

`muted` was also darkened from `#667a8e` (4.43:1) to `#5d7085` (5.09:1).

Hairline card borders sit at ~1.2:1 against their surface. That is deliberate:
WCAG 1.4.11 governs UI components and state indicators, not decorative
dividers, and raising them to 3:1 would give every card a heavy outline.
