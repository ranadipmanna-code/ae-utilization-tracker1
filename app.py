"""
Extended AE Utilization Tracker — Streamlit edition.

Reads faculty sessions from the CMIS view (read-only) and reads/writes app
state to the Anudip_AE_Team database (the hackathon tables).

Workflow (per the spec):
  Step 1  Pick week + Core AE.
  Step 2  Fetch that Core AE's faculty sessions from CMIS.
  Step 3  Highlight sessions available for Extended AE observation (yellow).
  Step 4  Extended AE claims sessions (status dropdown). Claimed -> GREEN.
  Step 5  CMIS task defaults: each member's own CMIS slot is typed from its
          course alias — the plr* family (plr_mi*, plr_crd*, PLR_SAVE, the
          placement/interview modules) -> Mock Interview, any other course
          alias -> Teaching. Claiming an Evaluation for that slot, or manually
          picking Training / Project Involvement / Other on the Calendar tab,
          overrides that; re-selecting the slot's own CMIS type clears the
          override. See ae_slot_task in db.py.

RBAC via user_roles.role:
  admin        -> any Core AE, full visibility
  core_ae      -> own faculty, can view + see team selections
  extended_ae  -> own paired Core AE's faculty, can claim
"""
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

import db
import mi_pool

st.set_page_config(page_title="AE Utilization Tracker", layout="wide", page_icon="📊")


# ---------------------------------------------------------------------------
# Theming — two skins:
#   "light"  : Apple-inspired. Airy, lots of whitespace, SF-ish system stack,
#              near-white canvas, soft grey rules, restrained accent blue.
#   "dark"   : Anudip-inspired. Deep navy canvas with the foundation's
#              orange/amber accent, higher-contrast cards.
# ---------------------------------------------------------------------------
THEMES = {
    # Clean & minimal — Apple/Linear inspired. Cool neutral grays, generous
    # whitespace, a single refined indigo accent, whisper-soft shadows.
    "light": {
        "bg": "#fbfbfc", "surface": "#ffffff", "surface_2": "#f6f7f9",
        "text": "#16181d", "muted": "#6b7280", "border": "#ececef",
        "accent": "#5e6ad2", "accent_soft": "#eef0fb",
        "avail_bg": "#fffdf6", "avail_border": "#e6b32e", "avail_text": "#8a6100",
        "claim_bg": "#f2fbf5", "claim_border": "#38b26a", "claim_text": "#0b5f28",
        "done_bg": "#f4f5fd", "done_border": "#5e6ad2",
        "chip_bg": "#f2f3f5", "chip_text": "#5c6069",
        "shadow": "0 1px 2px rgba(16,18,29,.04), 0 4px 16px rgba(16,18,29,.05)",
        # task-type colors for the Calendar tab
        "mock_bg": "#fff4ec", "mock_border": "#e07b39", "mock_text": "#8a4413",
        "teach_bg": "#f4f5f7", "teach_border": "#9aa0ab", "teach_text": "#565c66",
        "train_bg": "#eef6ff", "train_border": "#3b82c4", "train_text": "#1c4e73",
        "proj_bg": "#f5eefd", "proj_border": "#8b5cf6", "proj_text": "#4c2889",
        "other_bg": "#fdf0f3", "other_border": "#e0577a", "other_text": "#7a1330",
    },
    "dark": {
        "bg": "#0c0d10", "surface": "#161719", "surface_2": "#1c1d21",
        "text": "#f4f5f6", "muted": "#8a8f98", "border": "#26272b",
        "accent": "#7c86e8", "accent_soft": "#1e1f2e",
        "avail_bg": "#211d10", "avail_border": "#e6b32e", "avail_text": "#f5d78a",
        "claim_bg": "#10241a", "claim_border": "#3fb872", "claim_text": "#8fe6b6",
        "done_bg": "#191b28", "done_border": "#7c86e8",
        "chip_bg": "#232428", "chip_text": "#b6bac2",
        "shadow": "0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.5)",
        # task-type colors for the Calendar tab
        "mock_bg": "#2a1a0f", "mock_border": "#e0873f", "mock_text": "#f5c795",
        "teach_bg": "#1c1d21", "teach_border": "#5a5f6a", "teach_text": "#b6bac2",
        "train_bg": "#12202f", "train_border": "#4f9fe0", "train_text": "#a9d6fb",
        "proj_bg": "#221a35", "proj_border": "#a377f5", "proj_text": "#d9c8fb",
        "other_bg": "#301521", "other_border": "#e26f90", "other_text": "#f7b8ca",
    },
}


def _css(t: dict, name: str = "light") -> str:
    return f"""
    <style>
      /* Tell the browser this page has an intentional, fully-styled color
         scheme. Without this, Chrome/Android's automatic dark theme can
         decide to force-invert freshly injected HTML (like the sessions
         table below) even though every color here is set explicitly —
         which is why the table could render black under the Light skin. */
      html {{ color-scheme: light; }}
      /* the date-picker calendar lives in a detached popover; force it + every
         descendant (incl. empty padding cells) to light, beating inline styles */
      [data-baseweb="popover"] [data-baseweb="calendar"],
      [data-baseweb="popover"] [data-baseweb="calendar"] * {{
        background-color:{t['surface']} !important;
        background-image:none !important;
      }}
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;450;500;600;700&display=swap');
      html, body, [data-testid="stAppViewContainer"], .stApp {{
        background:{t['bg']} !important; color:{t['text']} !important;
        font-family:"Inter","Inter var",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
        -webkit-font-smoothing:antialiased;
        -moz-osx-font-smoothing:grayscale;
        letter-spacing:-0.006em;
      }}
      [data-testid="stHeader"] {{ background:transparent !important; }}
      .block-container {{ padding-top:2.2rem; padding-bottom:5rem; max-width:1120px; }}
      h1 {{ font-weight:600; letter-spacing:-.03em; font-size:1.9rem; margin-bottom:0; line-height:1.15; }}
      h2 {{ font-weight:600; letter-spacing:-.02em; font-size:1.35rem; }}
      h3 {{ font-weight:600; letter-spacing:-.015em; font-size:1.1rem; }}
      p,span,label,div,li {{ color:{t['text']}; }}
      [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * {{
        color:{t['muted']} !important; font-size:.83rem;
      }}
      /* a little more breathing room between stacked elements */
      [data-testid="stVerticalBlock"] > div {{ gap:.15rem; }}

      /* ---------- SIDEBAR ---------- */
      [data-testid="stSidebar"] {{
        background:{t['surface']} !important; border-right:1px solid {t['border']};
      }}
      [data-testid="stSidebar"] * {{ color:{t['text']}; }}
      /* quiet, secondary sign-out */
      [data-testid="stSidebar"] .stButton > button {{
        background:transparent !important; color:{t['muted']} !important;
        border:1px solid {t['border']} !important; font-weight:500; font-size:.85rem;
        padding:.4rem 1rem;
      }}
      [data-testid="stSidebar"] .stButton > button:hover {{
        background:{t['surface_2']} !important; color:{t['text']} !important;
        border-color:{t['muted']} !important;
      }}
      [data-testid="stSidebar"] .stButton > button * {{ color:inherit !important; }}

      /* ---------- ALL INPUT SHELLS ---------- */
      div[data-baseweb="select"] > div,
      .stTextInput input, .stTextArea textarea,
      .stDateInput input, div[data-testid="stDateInput"] > div > div,
      .stNumberInput input, div[data-testid="stNumberInput"] > div > div {{
        background:{t['surface']} !important;
        border:1px solid {t['border']} !important;
        border-radius:10px !important; color:{t['text']} !important;
        min-height:42px; box-shadow:none !important;
      }}
      .stDateInput *, div[data-testid="stDateInput"] * {{ color:{t['text']} !important; }}
      .stDateInput svg, .stNumberInput svg {{ fill:{t['muted']} !important; }}
      div[data-baseweb="select"] > div:focus-within,
      .stTextInput input:focus, .stTextArea textarea:focus {{
        border-color:{t['accent']} !important; box-shadow:0 0 0 3px {t['accent']}2b !important;
      }}
      div[data-baseweb="select"] div, div[data-baseweb="select"] span,
      div[data-baseweb="select"] input {{ color:{t['text']} !important; }}
      div[data-baseweb="select"] svg {{ fill:{t['muted']} !important; }}
      input::placeholder, textarea::placeholder {{ color:{t['muted']} !important; opacity:1; }}

      /* ---------- DISABLED / AUTOFILLED FIELDS ----------
         Streamlit fades disabled inputs to ~40% opacity, which made the
         auto-filled session details look empty. Show them clearly as
         read-only facts instead of ghost text. */
      .stTextInput input:disabled, .stTextArea textarea:disabled,
      input:disabled, textarea:disabled,
      div[data-testid="stTextInput"] input[disabled],
      [data-baseweb="input"] input:disabled {{
        -webkit-text-fill-color:{t['text']} !important;
        color:{t['text']} !important;
        opacity:1 !important;
        background:{t['surface_2']} !important;
        border:1px solid {t['border']} !important;
        font-weight:500;
        cursor:default;
      }}
      div[data-testid="stTextInput"]:has(input:disabled) label,
      div[data-testid="stTextInput"] input[disabled] + div {{
        opacity:1 !important;
      }}
      /* the wrapper baseweb dims too */
      div[data-baseweb="input"]:has(input:disabled),
      div[data-baseweb="base-input"]:has(input:disabled) {{
        opacity:1 !important; background:{t['surface_2']} !important;
      }}

      /* ---------- POPOVERS / MENUS / CALENDAR ---------- */
      /* Force the ENTIRE dropdown popover light — every nested element.
         The trainer/batch selectbox menus were rendering on a dark base. */
      div[data-baseweb="popover"],
      div[data-baseweb="popover"] *,
      div[data-baseweb="popover"] > div,
      div[data-baseweb="popover"] > div > div,
      ul[data-baseweb="menu"], div[data-baseweb="menu"],
      ul[data-baseweb="menu"] *, div[data-baseweb="menu"] * {{
        background-color:{t['surface']} !important;
        color:{t['text']} !important;
      }}
      div[data-baseweb="popover"] > div {{
        border:1px solid {t['border']} !important;
        border-radius:12px !important; box-shadow:{t['shadow']} !important;
        overflow:hidden;
      }}
      div[data-baseweb="calendar"], div[data-baseweb="datepicker"] {{
        background:{t['surface']} !important; border:1px solid {t['border']} !important;
        border-radius:12px !important; box-shadow:{t['shadow']} !important;
      }}
      ul[role="listbox"], div[role="listbox"] {{
        background:{t['surface']} !important;
      }}
      li[role="option"], div[role="option"] {{
        background:{t['surface']} !important; color:{t['text']} !important;
        font-size:.9rem; padding:9px 14px !important;
      }}
      li[role="option"] div, li[role="option"] span {{
        background:transparent !important; color:{t['text']} !important;
      }}
      /* hover + selected get the accent tint (not black) */
      li[role="option"]:hover, div[role="option"]:hover,
      li[aria-selected="true"], div[aria-selected="true"] {{
        background:{t['accent_soft']} !important; color:{t['accent']} !important;
      }}
      li[aria-selected="true"] *, li[role="option"]:hover *,
      div[aria-selected="true"] *, div[role="option"]:hover * {{
        background:transparent !important; color:{t['accent']} !important;
      }}

      /* ---------- CALENDAR internals (kill the black empty cells) ----------
         baseweb re-injects its own !important styles when the popover opens,
         which land AFTER this block and out-specify a plain catch-all — that's
         why whole leading/trailing week rows still rendered black. We beat it
         two ways: (1) pin the light background on the popover SHELL itself, so
         even elements we don't name show light behind them, and (2) use a
         high-specificity chain (popover > calendar > descendants) plus explicit
         ::before/::after, since the black in empty cells is often a pseudo. */
      div[data-baseweb="popover"] div[data-baseweb="calendar"],
      div[data-baseweb="popover"] div[data-baseweb="calendar"] *,
      div[data-baseweb="popover"] div[data-baseweb="calendar"] *::before,
      div[data-baseweb="popover"] div[data-baseweb="calendar"] *::after,
      div[data-baseweb="calendar"],
      div[data-baseweb="calendar"] *,
      div[data-baseweb="calendar"] *::before,
      div[data-baseweb="calendar"] *::after,
      div[data-baseweb="calendar"] [role="grid"],
      div[data-baseweb="calendar"] [role="row"],
      div[data-baseweb="calendar"] [role="gridcell"],
      div[data-baseweb="calendar"] [role="gridcell"] > div,
      div[data-baseweb="datepicker"],
      div[data-baseweb="datepicker"] * {{
        background-color:{t['surface']} !important;
        background-image:none !important;
        color:{t['text']} !important;
        border-color:{t['border']} !important;
      }}
      /* selected day — highest specificity so it survives over the reset above */
      div[data-baseweb="popover"] div[data-baseweb="calendar"] [aria-selected="true"],
      div[data-baseweb="popover"] div[data-baseweb="calendar"] [aria-selected="true"] *,
      div[data-baseweb="calendar"] [aria-selected="true"],
      div[data-baseweb="calendar"] [aria-selected="true"] * {{
        background-color:{t['accent']} !important; color:#fff !important;
        border-radius:8px !important;
      }}
      /* hovered day */
      div[data-baseweb="calendar"] [role="gridcell"]:hover,
      div[data-baseweb="calendar"] [role="gridcell"]:hover *,
      div[data-baseweb="calendar"] [class*="Day"]:hover {{
        background-color:{t['accent_soft']} !important; color:{t['accent']} !important;
        border-radius:8px !important;
      }}
      /* disabled / out-of-range days: faded surface, never black */
      div[data-baseweb="calendar"] [aria-disabled="true"],
      div[data-baseweb="calendar"] [aria-disabled="true"] * {{
        background-color:{t['surface']} !important;
        color:{t['muted']} !important; opacity:.4;
      }}

      /* ---------- NUMBER INPUT stepper (-/+ were rendering dark) ---------- */
      div[data-testid="stNumberInput"] button,
      [data-testid="stNumberInputStepUp"], [data-testid="stNumberInputStepDown"] {{
        background:{t['surface_2']} !important; color:{t['text']} !important;
        border:1px solid {t['border']} !important;
      }}
      div[data-testid="stNumberInput"] button:hover {{
        background:{t['accent_soft']} !important; color:{t['accent']} !important;
      }}
      div[data-testid="stNumberInput"] button svg {{ fill:{t['text']} !important; }}

      /* ---------- TABS ---------- */
      .stTabs [data-baseweb="tab-list"] {{
        gap:4px; background:{t['surface_2']}; padding:5px; border-radius:12px;
        border:1px solid {t['border']};
      }}
      .stTabs [data-baseweb="tab"] {{
        height:38px; border-radius:8px; padding:0 16px;
        color:{t['muted']} !important; font-weight:500; font-size:.9rem;
      }}
      .stTabs [aria-selected="true"] {{
        background:{t['surface']} !important; color:{t['text']} !important;
        font-weight:600; box-shadow:0 1px 3px rgba(0,0,0,.08);
      }}
      .stTabs [aria-selected="true"] * {{ color:{t['text']} !important; }}
      .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display:none; }}

      /* ---------- BUTTONS ---------- */
      .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {{
        background:{t['accent']}; color:#fff !important; border:none; border-radius:10px;
        padding:.5rem 1.15rem; font-weight:600; font-size:.9rem;
        transition:opacity .15s ease, transform .06s ease;
      }}
      .stButton > button:hover, .stFormSubmitButton > button:hover {{ opacity:.87; }}
      .stButton > button:active {{ transform:scale(.98); }}
      .stFormSubmitButton > button *, .stDownloadButton > button * {{ color:#fff !important; }}

      /* ---------- EXPANDER ---------- */
      [data-testid="stExpander"] {{
        border:1px solid {t['border']} !important; border-radius:10px !important;
        background:{t['surface']} !important; margin-bottom:14px;
      }}
      [data-testid="stExpander"] summary {{ color:{t['text']} !important; font-size:.86rem; }}
      [data-testid="stExpander"] summary:hover {{ color:{t['accent']} !important; }}
      [data-testid="stExpander"] * {{ color:{t['text']}; }}

      /* ---------- METRICS ---------- */
      div[data-testid="stMetric"] {{
        background:{t['surface']}; border:1px solid {t['border']};
        border-radius:12px; padding:14px 16px;
      }}
      div[data-testid="stMetricValue"] {{ font-weight:600; letter-spacing:-.02em; font-size:1.5rem; }}
      div[data-testid="stMetricValue"] * {{ color:{t['text']} !important; }}
      div[data-testid="stMetricLabel"] * {{ color:{t['muted']} !important; font-size:.78rem; }}

      /* colourful stat cards for the at-a-glance snapshot */
      .stat-row {{
        display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:8px 0 18px;
      }}
      .stat {{
        border-radius:14px; padding:18px 20px; border:1px solid {t['border']};
        background:{t['surface']}; position:relative; overflow:hidden;
        transition:transform .12s ease, box-shadow .12s ease;
      }}
      .stat:hover {{ transform:translateY(-2px); box-shadow:{t['shadow']}; }}
      .stat::before {{ content:""; position:absolute; left:0; top:0; bottom:0; width:4px; }}
      .stat-total::before {{ background:{t['muted']}; }}
      .stat-avail::before {{ background:{t['avail_border']}; }}
      .stat-claim::before {{ background:{t['claim_border']}; }}
      .stat-mine::before  {{ background:{t['accent']}; }}
      .stat-num {{ font-size:1.9rem; font-weight:650; letter-spacing:-.03em; line-height:1; }}
      .stat-lbl {{ font-size:.8rem; color:{t['muted']}; margin-top:6px; font-weight:500; }}
      .stat-avail .stat-num {{ color:{t['avail_text']}; }}
      .stat-claim .stat-num {{ color:{t['claim_text']}; }}
      .stat-mine .stat-num  {{ color:{t['accent']}; }}
      @media (max-width: 640px) {{ .stat-row {{ grid-template-columns:repeat(2,1fr); }} }}

      /* help strip above the session table */
      .help-strip {{
        display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap;
        gap:10px; padding:11px 16px; margin-bottom:10px;
        background:{t['accent_soft']}; border:1px solid {t['border']};
        border-radius:12px; font-size:.84rem; color:{t['text']};
      }}
      .help-strip b {{ color:{t['text']}; font-weight:600; }}
      .legend {{ display:flex; gap:8px; flex-wrap:wrap; }}
      .lg {{ font-size:.74rem; font-weight:600; padding:2px 9px; border-radius:980px; }}
      .lg-avail {{ background:{t['avail_border']}; color:{t['avail_text']}; }}
      .lg-mine  {{ background:{t['accent']}; color:#fff; }}
      .lg-lock  {{ background:{t['chip_bg']}; color:{t['muted']}; }}

      /* ---------- SESSION CARDS (daily-use list) ---------- */
      .slot-head {{
        font-size:.82rem; font-weight:650; letter-spacing:-.01em; color:{t['text']};
        margin:18px 0 8px; padding-bottom:6px; border-bottom:1px solid {t['border']};
      }}
      .slot-count {{
        float:right; font-size:.72rem; font-weight:500; color:{t['muted']};
        background:{t['surface_2']}; padding:1px 9px; border-radius:980px;
      }}
      .scard {{
        border-radius:12px; padding:12px 15px; margin-bottom:8px;
        border:1px solid {t['border']}; background:{t['surface']};
        border-left:3px solid {t['border']};
        transition:transform .1s ease, box-shadow .1s ease;
      }}
      .scard:hover {{ transform:translateX(2px); box-shadow:{t['shadow']}; }}
      .scard-avail {{ border-left-color:{t['avail_border']}; }}
      .scard-mine  {{ border-left-color:{t['accent']}; background:{t['done_bg']}; }}
      .scard-lock  {{ border-left-color:{t['claim_border']}; background:{t['claim_bg']}; }}
      .scard-top {{ font-size:.95rem; font-weight:600; letter-spacing:-.01em; color:{t['text']};
                    display:flex; align-items:center; gap:8px; flex-wrap:wrap; }}
      .scard-sub {{ font-size:.79rem; color:{t['muted']}; margin-top:4px; }}
      .scard-sub b {{ color:{t['text']}; font-weight:600; }}
      .pill {{ font-size:.68rem; font-weight:600; padding:2px 9px; border-radius:980px; }}
      .pill-avail {{ background:{t['avail_border']}; color:{t['avail_text']}; }}
      .pill-mine  {{ background:{t['accent']}; color:#fff; }}
      .pill-lock  {{ background:{t['claim_border']}; color:#04301f; }}
      .locked-status {{
        text-align:center; font-size:.8rem; font-weight:600; color:{t['muted']};
        padding:9px 0;
      }}

      /* ---------- CALENDAR / TASK CARDS ---------- */
      .tcard {{
        border-radius:12px; padding:11px 14px; margin-bottom:8px;
        border:1px solid {t['border']}; border-left:3px solid {t['border']};
        transition:transform .1s ease, box-shadow .1s ease;
      }}
      .tcard:hover {{ transform:translateX(2px); box-shadow:{t['shadow']}; }}
      .tcard-mock  {{ background:{t['mock_bg']};  border-left-color:{t['mock_border']}; }}
      .tcard-teach {{ background:{t['teach_bg']}; border-left-color:{t['teach_border']}; }}
      .tcard-eval  {{ background:{t['claim_bg']}; border-left-color:{t['claim_border']}; }}
      .tcard-train {{ background:{t['train_bg']}; border-left-color:{t['train_border']}; }}
      .tcard-proj  {{ background:{t['proj_bg']};  border-left-color:{t['proj_border']}; }}
      .tcard-other {{ background:{t['other_bg']}; border-left-color:{t['other_border']}; }}
      .tcard-top {{ font-size:.92rem; font-weight:600; letter-spacing:-.01em; color:{t['text']};
                    display:flex; align-items:center; gap:8px; flex-wrap:wrap; }}
      .tcard-sub {{ font-size:.78rem; color:{t['muted']}; margin-top:3px; }}
      .tchip {{ font-size:.68rem; font-weight:600; padding:2px 9px; border-radius:980px; }}
      .tchip-mock  {{ background:{t['mock_border']};  color:#fff; }}
      .tchip-teach {{ background:{t['teach_border']}; color:#fff; }}
      .tchip-eval  {{ background:{t['claim_border']}; color:#04301f; }}
      .tchip-train {{ background:{t['train_border']}; color:#fff; }}
      .tchip-proj  {{ background:{t['proj_border']};  color:#fff; }}
      .tchip-other {{ background:{t['other_border']}; color:#fff; }}
      .cal-daymark {{
        font-size:.82rem; font-weight:650; letter-spacing:-.01em; color:{t['text']};
        margin:18px 0 8px; padding-bottom:6px; border-bottom:1px solid {t['border']};
      }}

      /* ---------- SESSION ROW ---------- */
      .sess-card {{
        border-radius:10px; padding:11px 14px; margin-bottom:7px;
        border:1px solid {t['border']}; background:{t['surface']};
        border-left:3px solid {t['border']};
        transition:background .12s ease;
      }}
      .sess-card:hover {{ background:{t['surface_2']}; }}
      .sess-available {{ background:{t['avail_bg']}; border-left-color:{t['avail_border']}; }}
      .sess-claimed {{ background:{t['claim_bg']}; border-left-color:{t['claim_border']}; }}
      .sess-done {{ background:{t['done_bg']}; border-left-color:{t['done_border']}; }}
      .sess-name {{ font-size:.94rem; font-weight:600; letter-spacing:-.01em; }}
      .sess-meta {{ font-size:.78rem; color:{t['muted']}; margin-top:3px; }}
      .chip {{
        display:inline-block; font-size:.68rem; font-weight:500;
        background:{t['chip_bg']}; color:{t['chip_text']};
        padding:2px 8px; border-radius:6px; margin-left:5px;
      }}
      .chip-prog {{ background:{t['accent_soft']}; color:{t['accent']}; font-weight:600; }}
      .badge {{
        display:inline-block; font-size:.67rem; font-weight:600;
        padding:1px 8px; border-radius:6px; margin-left:7px;
      }}
      .badge-available {{ background:{t['avail_border']}; color:{t['avail_text']}; }}
      .badge-selected, .badge-confirmed {{ background:{t['claim_border']}; color:#04301f; }}
      .badge-choosing {{ background:{t['accent']}; color:#fff; }}
      .badge-done {{ background:{t['done_border']}; color:#fff; }}

      /* ---------- facts panel ---------- */
      .eval-facts {{
        background:{t['surface_2']}; border:1px solid {t['border']};
        border-radius:10px; padding:14px 16px; margin-bottom:16px;
      }}
      .eval-facts-title {{
        font-size:.74rem; font-weight:700; text-transform:uppercase;
        letter-spacing:.05em; color:{t['muted']}; margin-bottom:10px;
      }}
      .eval-grid {{
        display:grid; grid-template-columns:repeat(3, 1fr); gap:10px 18px;
      }}
      .eval-grid > div {{ display:flex; flex-direction:column; }}
      .ef-k {{
        font-size:.7rem; font-weight:600; text-transform:uppercase;
        letter-spacing:.04em; color:{t['muted']}; margin-bottom:2px;
      }}
      .ef-v {{ font-size:.9rem; font-weight:600; color:{t['text']}; }}
      .ef-sid {{
        margin-top:12px; padding-top:10px; border-top:1px solid {t['border']};
        font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
        font-size:.72rem; color:{t['muted']}; word-break:break-all;
      }}
      .ef-sid .ef-k {{ display:block; margin-bottom:3px; }}

      /* day group heading */
      .day-head {{
        font-size:.76rem; font-weight:700; letter-spacing:.04em; text-transform:uppercase;
        color:{t['muted']}; margin:18px 0 8px; padding-bottom:5px;
        border-bottom:1px solid {t['border']};
      }}

      /* ---------- LOGIN ---------- */
      .login-title {{ font-size:1.9rem; font-weight:700; letter-spacing:-.03em; margin-bottom:6px; }}
      .login-sub {{ color:{t['muted']}; font-size:.88rem; margin-bottom:24px; }}
      .dbdot {{ font-size:.75rem; color:{t['muted']}; margin-top:14px; }}

      hr, [data-testid="stDivider"] {{ border-color:{t['border']} !important; }}
      /* ---------- SESSION TABLE (themed HTML, not the canvas grid) ---------- */
      .stDataFrame, [data-testid="stDataFrame"] {{
        border:1px solid {t['border']}; border-radius:10px; overflow:hidden;
      }}
      /* Force the editable grid (data_editor) to light in light mode.
         glide-data-grid uses a canvas + these CSS vars. */
      [data-testid="stDataFrame"], [data-testid="stDataEditor"],
      .stDataFrame, .stDataEditor {{
        --gdg-bg-cell:{t['surface']};
        --gdg-bg-cell-medium:{t['surface_2']};
        --gdg-bg-header:{t['surface_2']};
        --gdg-bg-header-hovered:{t['chip_bg']};
        --gdg-bg-header-has-focus:{t['chip_bg']};
        --gdg-text-dark:{t['text']};
        --gdg-text-medium:{t['muted']};
        --gdg-text-light:{t['muted']};
        --gdg-text-header:{t['muted']};
        --gdg-border-color:{t['border']};
        --gdg-horizontal-border-color:{t['border']};
        --gdg-accent-color:{t['accent']};
        --gdg-accent-light:{t['accent_soft']};
        --gdg-bg-bubble:{t['surface']};
      }}
      [data-testid="stDataEditor"] canvas {{ background:{t['surface']} !important; }}
      .sess-table-wrap {{
        border:1px solid {t['border']}; border-radius:12px; overflow:hidden;
        margin-bottom:14px; color-scheme:{name}; forced-color-adjust:none;
      }}
      .sess-table {{
        width:100%; border-collapse:collapse; font-size:.86rem;
        background:{t['surface']}; color:{t['text']}; forced-color-adjust:none;
      }}
      .sess-table thead th {{
        text-align:left; padding:11px 14px; font-weight:600; font-size:.76rem;
        text-transform:uppercase; letter-spacing:.03em;
        color:{t['muted']}; background:{t['surface_2']};
        border-bottom:1px solid {t['border']}; position:sticky; top:0;
      }}
      .sess-table tbody td {{
        padding:10px 14px; border-bottom:1px solid {t['border']};
        color:{t['text']};
      }}
      .sess-table tbody tr:last-child td {{ border-bottom:none; }}
      .sess-table tbody tr:hover {{ background:{t['surface_2']}; }}
      .sess-table tr.row-claimed {{ background:{t['claim_bg']}; }}
      .sess-table tr.row-deleg   {{ background:{t['done_bg']}; }}

      .st {{ display:inline-block; padding:2px 9px; border-radius:980px;
             font-size:.72rem; font-weight:600; }}
      .st-conf {{ background:{t['claim_border']}; color:#04301f; }}
      .st-sel  {{ background:{t['claim_border']}; color:#04301f; }}
      .st-cho  {{ background:{t['accent']}; color:#fff; }}
      .st-non  {{ background:{t['chip_bg']}; color:{t['muted']}; }}

      /* ---------- facts panel ---------- */      /* ---------- facts panel ---------- */
      .eval-facts {{
        background:{t['surface_2']}; border:1px solid {t['border']};
        border-radius:10px; padding:14px 16px; margin-bottom:16px;
      }}
      .eval-facts-title {{
        font-size:.74rem; font-weight:700; text-transform:uppercase;
        letter-spacing:.05em; color:{t['muted']}; margin-bottom:10px;
      }}
      .eval-grid {{
        display:grid; grid-template-columns:repeat(3, 1fr); gap:10px 18px;
      }}
      .eval-grid > div {{ display:flex; flex-direction:column; }}
      .ef-k {{
        font-size:.7rem; font-weight:600; text-transform:uppercase;
        letter-spacing:.04em; color:{t['muted']}; margin-bottom:2px;
      }}
      .ef-v {{ font-size:.9rem; font-weight:600; color:{t['text']}; }}
      .ef-sid {{
        margin-top:12px; padding-top:10px; border-top:1px solid {t['border']};
        font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
        font-size:.72rem; color:{t['muted']}; word-break:break-all;
      }}
      .ef-sid .ef-k {{ display:block; margin-bottom:3px; }}

      /* day group heading */
      .day-head {{
        font-size:.76rem; font-weight:700; letter-spacing:.04em; text-transform:uppercase;
        color:{t['muted']}; margin:18px 0 8px; padding-bottom:5px;
        border-bottom:1px solid {t['border']};
      }}

      /* ---------- LOGIN ---------- */
      .login-title {{ font-size:1.9rem; font-weight:700; letter-spacing:-.03em; margin-bottom:6px; }}
      .login-sub {{ color:{t['muted']}; font-size:.88rem; margin-bottom:24px; }}
      .dbdot {{ font-size:.75rem; color:{t['muted']}; margin-top:14px; }}

      hr, [data-testid="stDivider"] {{ border-color:{t['border']} !important; }}
      [data-testid="stAlert"] {{ border-radius:10px; }}
      div[role="radiogroup"] label {{ font-size:.85rem; }}
    </style>
    """


def apply_theme():
    if "theme" not in st.session_state:
        st.session_state.theme = "light"
    st.markdown(_css(THEMES[st.session_state.theme], st.session_state.theme), unsafe_allow_html=True)


STATUS_OPTIONS = ["Not Selected", "Selected"]
# "Choosing" and "Confirmed" are no longer offered as picks, but stay valid
# values: existing rows saved under the old 4-option flow keep working, and
# _status_badge()/CLAIMED below still recognise them for display and claim
# counting. Only the pick list shown to the user has shrunk.
CLAIMED = {"Selected", "Confirmed"}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def _theme_toggle(key: str):
    """Small segmented control to switch skins."""
    cur = st.session_state.get("theme", "light")
    choice = st.radio(
        "Appearance",
        ["light", "dark"],
        index=0 if cur == "light" else 1,
        horizontal=True,
        key=key,
        format_func=lambda v: "☀️  Light" if v == "light" else "🌙  Dark",
    )
    if choice != cur:
        st.session_state.theme = choice
        st.rerun()


def login_view():
    apply_theme()
    left, mid, right = st.columns([1, 1.1, 1])
    with mid:
        st.markdown('<div class="login-wrap">', unsafe_allow_html=True)
        st.markdown(
            '<div class="login-title">AE Utilization Tracker</div>'
            '<div class="login-sub">Academic Excellence · Anudip Foundation</div>',
            unsafe_allow_html=True,
        )
        with st.form("login", border=False):
            email = st.text_input("Email", placeholder="you@anudip.org").strip().lower()
            pwd = st.text_input("Password", type="password", placeholder="••••••••")
            ok = st.form_submit_button("Sign in", use_container_width=True)
        _theme_toggle("theme_login")
        cmis_ok, app_ok = db.ping()
        st.markdown(
            f'<div class="dbdot">CMIS {"🟢" if cmis_ok else "🔴"} &nbsp;·&nbsp; App DB {"🟢" if app_ok else "🔴"}</div>',
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    if ok:
        roles = db.get_user_roles()
        match = roles[roles["email"].str.lower() == email]
        if match.empty:
            st.error("Email not found.")
            return
        if pwd != st.secrets["auth"]["shared_password"]:
            st.error("Incorrect password.")
            return
        row = match.iloc[0]
        st.session_state.user = {"email": row["email"], "name": row["name"], "role": row["role"]}
        st.rerun()


def current_week_bounds(offset_weeks: int = 0) -> tuple[date, date]:
    today = date.today() + timedelta(weeks=offset_weeks)
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)


# ---------------------------------------------------------------------------
# Main dashboard
# ---------------------------------------------------------------------------
def dashboard():
    apply_theme()
    user = st.session_state.user
    role = user["role"]

    with st.sidebar:
        st.markdown(f"### {user['name']}")
        st.caption(f"{user['email']} · {role}")
        if st.button("Sign out", use_container_width=True):
            del st.session_state.user
            st.rerun()
        st.divider()
        _theme_toggle("theme_app")
        st.divider()
        cmis_ok, app_ok = db.ping()
        st.markdown(
            f'<div class="dbdot">CMIS {"🟢" if cmis_ok else "🔴"} &nbsp;·&nbsp; App DB {"🟢" if app_ok else "🔴"}</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        "<h1 style='margin-bottom:2px'>Extended AE Utilization Tracker</h1>"
        "<p style='opacity:.6;margin-top:0;font-size:.92rem'>"
        "Faculty observation scheduling · live from CMIS + Anudip AE Team DB</p>",
        unsafe_allow_html=True,
    )

    # Evaluation removed (change #3). Tabs differ per role.
    # The MI Pool tab sits next to Sessions for every role — a Core AE has to
    # be able to see what the Extended AEs have and haven't picked up, which
    # is exactly what was missing before.
    if role == "admin":
        made = st.tabs(["📋  Sessions", "🎯  MI Pool", "👥  My Extended AE Team",
                        "📊  Weekly Summary", "📅  Calendar", "🔗  Email Health"])
        with made[0]:
            _sessions_tab(user, role)
        with made[1]:
            mi_pool.render_mi_pool_tab(user, role)
        with made[2]:
            _rollup_tab(user, role)
        with made[3]:
            _summary_tab(user, role)
        with made[4]:
            _calendar_tab(user, role)
        with made[5]:
            _email_health_tab()
    elif role == "core_ae":
        made = st.tabs(["📋  Sessions", "🎯  MI Pool", "👥  My Extended AE Team",
                        "📊  Weekly Summary", "📅  Calendar"])
        with made[0]:
            _sessions_tab(user, role)
        with made[1]:
            mi_pool.render_mi_pool_tab(user, role)
        with made[2]:
            _rollup_tab(user, role)
        with made[3]:
            _summary_tab(user, role)
        with made[4]:
            _calendar_tab(user, role)
    else:  # extended_ae
        made = st.tabs(["📋  Sessions", "🎯  MI Pool", "🧭  My Alignment", "📅  Calendar"])
        with made[0]:
            _sessions_tab(user, role)
        with made[1]:
            mi_pool.render_mi_pool_tab(user, role)
        with made[2]:
            _my_core_tab(user)
        with made[3]:
            _calendar_tab(user, role)


def _summary_tab(user, role):
    st.markdown("### Weekly Summary")
    st.caption("Auto-maintained in `weekly_ae_summary` — updates whenever a session is claimed.")

    scope = None if role == "admin" else user["email"]
    df = db.get_weekly_summary(scope)

    core_options = _core_options_for(role, user["email"])
    c1, c2 = st.columns([2, 1])
    with c1:
        pick = st.selectbox("Core AE", core_options, key="sum_core")
    with c2:
        st.write("")
        if st.button("↻  Rebuild this week", use_container_width=True):
            try:
                db.recompute_weekly_summary(pick, date.today())
                db.clear_app_caches()
                st.success("Summary rebuilt.")
                st.rerun()
            except Exception as e:
                st.error(f"Could not rebuild: {e}")

    if df.empty:
        st.info(
            "No summary rows yet. They appear automatically once someone claims "
            "a session — or hit **Rebuild this week** above."
        )
        return

    view = df.rename(columns={
        "core_ae_email": "Core AE", "week_start_date": "Week of",
        "total_sessions": "Available", "sessions_selected": "Selected",
        "sessions_observed": "Observed", "updated_on": "Updated",
    })
    st.dataframe(view, use_container_width=True, hide_index=True)


def _email_health_tab():
    """Admin-only. Read-only diagnostic: which user_roles / core_ae_faculty_map
    emails have no matching email_id in CMIS, so their Calendar/Sessions data
    silently looks empty. Never writes to the database — generates SQL for a
    human to review and run in phpMyAdmin."""
    st.markdown("### 🔗 Email Health — app DB vs CMIS")
    st.caption(
        "CMIS and the app DB live on two different MySQL servers, so they "
        "can't be joined in one query — this compares them in Python instead. "
        "Shows every `user_roles` / `core_ae_faculty_map` email with **no "
        "matching `email_id` in CMIS**. Those members will show no CMIS "
        "slots on the Sessions/Calendar tabs even if their sessions exist, "
        "because the join can't find them. This tool is read-only — it never "
        "changes the database."
    )

    if st.button("↻  Run health check", type="primary"):
        db.clear_app_caches()

    try:
        with st.spinner("Comparing app DB emails against CMIS…"):
            report = db.email_health_report()
    except Exception as e:
        st.error(f"Could not run the health check: {e}")
        return

    if report.empty:
        st.success("✅ Every app DB email has a matching CMIS email_id. Nothing to fix.")
        return

    st.warning(f"⚠️ {len(report)} app DB email{'s' if len(report) != 1 else ''} "
               f"have no exact match in CMIS.")

    view = report.rename(columns={
        "source": "Table", "field": "Column", "app_email": "App DB email",
        "app_name": "Name", "role": "Role",
        "suggested_cmis_email": "Suggested CMIS email",
        "match_method": "Matched by", "match_score": "Score",
        "cmis_slot_count": "CMIS slots",
    }).drop(columns=["matches_cmis"])
    st.dataframe(view, use_container_width=True, hide_index=True)

    n_strong = report["match_method"].isin(["normalised_email", "name"]).sum()
    n_fuzzy = (report["match_method"] == "fuzzy").sum()
    n_none = report["suggested_cmis_email"].isna().sum()
    st.caption(
        f"**{n_strong}** high-confidence fixes (normalised email or exact name "
        f"match) · **{n_fuzzy}** fuzzy suggestions to eyeball · **{n_none}** "
        f"with no CMIS match at all. That last group is usually fine — Core AEs "
        f"observe rather than teach, so they legitimately have no CMIS sessions."
    )

    with st.expander("📋  Generate fix SQL (review before running — nothing here executes automatically)"):
        sql_text = db.build_email_fix_sql(report)
        st.code(sql_text, language="sql")
        st.caption(
            "Copy this into phpMyAdmin's SQL tab on the **app DB server** "
            "(Anudip_AE_Team, 128.199.28.53) — not CMIS. The high-confidence "
            "block is safe to run as-is; read the fuzzy block line by line "
            "first, since those matched on spelling similarity rather than an "
            "exact key."
        )


def _week_bounds_now():
    ws, we = current_week_bounds(0)
    return ws, we


def _rollup_tab(user, role):
    core_options = _core_options_for(role, user["email"])
    if not core_options:
        st.info("No Core AE mapping found.")
        return
    core_ae_email = st.selectbox("Core AE", core_options, key="rollup_core")

    # ---- TEAM ROSTER (structure, always shown) ----
    st.markdown("### 👥 Team Roster")

    ext_aes = db.extended_aes_for_core(core_ae_email)
    faculty = db.faculty_emails_for_core(core_ae_email)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Extended AEs** ({len(ext_aes)})")
        if ext_aes:
            roles_df = db.get_user_roles()
            name_by = {}
            if not roles_df.empty:
                name_by = dict(zip(roles_df["email"].str.lower(), roles_df["name"]))
            for e in ext_aes:
                nm = name_by.get(e.lower(), e.split("@")[0])
                st.markdown(f"- {nm}  \n  <span style='opacity:.6;font-size:.8rem'>{e}</span>",
                            unsafe_allow_html=True)
        else:
            st.caption("No Extended AEs paired in ae_extae.")
    with c2:
        st.markdown(f"**Trainers** ({len(faculty)})")
        if faculty:
            for t in sorted(faculty)[:30]:
                st.markdown(f"- {t.split('@')[0]}")
            if len(faculty) > 30:
                st.caption(f"…and {len(faculty) - 30} more")
        else:
            st.caption("No trainers mapped in core_ae_faculty_map.")

    st.divider()

    # ---- ACTIVITY (selections this week) ----
    ws, we = _week_bounds_now()
    st.markdown(f"### 📋 Team Selections — week of {ws} → {we}")
    _team_rollup(core_ae_email, ws, we)


def _my_core_tab(user):
    """For an Extended AE: show which Core AE(s) they're aligned with + teammates."""
    st.markdown("### 🧭 My Alignment")
    my_core = db.core_ae_for_extended(user["email"])
    roles_df = db.get_user_roles()
    name_by = {}
    if not roles_df.empty:
        name_by = dict(zip(roles_df["email"].str.lower(), roles_df["name"]))

    if not my_core:
        st.info("You're not paired to a Core AE yet in the ae_extae table.")
        return

    core_name = name_by.get(my_core.lower(), my_core.split("@")[0])
    st.markdown(
        f"You report to **{core_name}**  \n"
        f"<span style='opacity:.6;font-size:.85rem'>{my_core}</span>",
        unsafe_allow_html=True,
    )

    # teammates: other Extended AEs under the same Core AE
    teammates = [e for e in db.extended_aes_for_core(my_core) if e.lower() != user["email"].lower()]
    st.markdown(f"**Teammates under {core_name}** ({len(teammates)})")
    if teammates:
        for e in teammates:
            nm = name_by.get(e.lower(), e.split("@")[0])
            st.markdown(f"- {nm}  <span style='opacity:.5;font-size:.8rem'>({e})</span>",
                        unsafe_allow_html=True)
    else:
        st.caption("You're the only Extended AE under this Core AE.")

    # the trainers this team observes
    faculty = db.faculty_emails_for_core(my_core)
    st.divider()
    st.markdown(f"**Trainers your team observes** ({len(faculty)})")
    for t in sorted(faculty)[:40]:
        st.markdown(f"- {t.split('@')[0]}")
    if len(faculty) > 40:
        st.caption(f"…and {len(faculty) - 40} more")


def _calendar_members_for(user, role) -> list[tuple[str, str]]:
    """(email, display label) options this user may view on the calendar.
    Everyone can always see themselves; Core AE/Admin also see their team."""
    roles_df = db.get_user_roles()
    name_by = {}
    if not roles_df.empty:
        name_by = dict(zip(roles_df["email"].str.lower(), roles_df["name"]))

    def _label(email: str) -> str:
        nm = name_by.get(email.lower(), email.split("@")[0])
        return f"{nm}  ·  {email}"

    opts = [(user["email"], f"{_label(user['email'])}  (you)")]
    if role == "core_ae":
        for e in db.extended_aes_for_core(user["email"]):
            opts.append((e, _label(e)))
    elif role == "admin":
        if not roles_df.empty:
            for _, r in roles_df.iterrows():
                if r["email"].lower() != user["email"].lower():
                    opts.append((r["email"], _label(r["email"])))
    return opts


def _slot_end_minutes(slot: str) -> int:
    """Minutes-since-midnight for a slot's END, e.g. '11:00 AM - 11:30 AM' -> 690.
    Companion to _slot_start_minutes; used to detect back-to-back runs."""
    if not slot or "-" not in str(slot):
        return -1
    try:
        end = str(slot).split("-", 1)[1].strip()
        t = pd.to_datetime(end, format="%I:%M %p")
        return t.hour * 60 + t.minute
    except Exception:
        return -1


def _merge_calendar_runs(grp: pd.DataFrame) -> list[dict]:
    """Collapse a day's slots into contiguous same-task runs for display.

    Two rows merge only when ALL of these hold: back-to-back in time (one
    slot's end == the next one's start), same batch_code, same c_alias, same
    *current* task_type, and — if the task is 'other' — the same note. Same
    c_alias also guarantees the same default_task, so a merged card's "clear
    override" behaviour stays correct for every slot underneath it.

    Deliberately NOT merged across a c_alias change even when the task_type
    happens to match (e.g. plr_mi1 followed by plr_mi2, both Mock Interview):
    keeping them separate preserves each slot's own default for the "reset to
    CMIS default" path, and avoids silently combining two different interview
    rounds into one card.

    Returns a list of dicts, each with the merged slot_time string, the
    representative row's fields, and `_members`: the original rows (as Series)
    that make up the run, in order — used when saving to fan the write across
    every real slot.
    """
    rows = [r for _, r in grp.iterrows()]
    runs: list[dict] = []
    for r in rows:
        if runs:
            prev = runs[-1]
            same_group = (
                r.get("batch_code") == prev["_rep"].get("batch_code")
                and r.get("c_alias") == prev["_rep"].get("c_alias")
                and r["task_type"] == prev["_rep"]["task_type"]
                and (r["task_type"] != "other"
                     or (r.get("other_note") or "") == (prev["_rep"].get("other_note") or ""))
            )
            contiguous = _slot_end_minutes(prev["_members"][-1]["slot_time"]) == _slot_start_minutes(r["slot_time"])
            if same_group and contiguous:
                prev["_members"].append(r)
                start = str(prev["_members"][0]["slot_time"]).split("-", 1)[0].strip()
                end = str(r["slot_time"]).split("-", 1)[1].strip()
                prev["slot_time"] = f"{start} - {end}"
                continue
        runs.append({"_rep": r, "_members": [r], "slot_time": r["slot_time"]})
    return runs


def _calendar_tab(user, role):
    st.markdown("### 📅 Calendar — CMIS task defaults & assignment")

    members = _calendar_members_for(user, role)
    labels = [lbl for _, lbl in members]
    pick_idx = st.selectbox(
        "Member", range(len(members)), format_func=lambda i: labels[i], key="cal_member"
    )
    member_email, _ = members[pick_idx]
    is_editable = member_email.lower() == user["email"].lower()
    member_role = db.role_for_email(member_email) or role

    # Date range comes from the Sessions tab, not an independent picker here —
    # the two tabs are meant to always show the same window. If the Sessions
    # tab hasn't been visited yet this session, fall back to a sensible
    # default (today -> +13 days, matching Sessions' own first-load default)
    # so Calendar still works standalone.
    ws = st.session_state.get("shared_from") or date.today()
    we = st.session_state.get("shared_to") or (date.today() + timedelta(days=13))
    range_note = "" if is_editable else "  ·  🔒 view-only (not your calendar)"
    st.caption(f"{ws} → {we}  ·  matches the Sessions tab date range{range_note}")

    with st.spinner("Fetching this member's schedule…"):
        cal = db.resolve_member_calendar(member_email, ws, we)

    if cal.empty:
        st.info("No CMIS slots found for this member in this week — nothing to default onto.")
        return

    counts = cal["task_type"].value_counts().to_dict()
    chip_row = " ".join(
        f"<span class='tchip tchip-{_task_css(tt)}'>{db.TASK_LABELS.get(tt, tt)} · {counts.get(tt, 0)}</span>"
        for tt in db.TASK_TYPES if counts.get(tt, 0)
    )
    st.markdown(f"<div class='legend' style='margin:6px 0 14px'>{chip_row}</div>", unsafe_allow_html=True)

    cal["_sort_mins"] = cal["slot_time"].map(_slot_start_minutes)
    cal = cal.sort_values(["_date", "_sort_mins"]).drop(columns=["_sort_mins"]).reset_index(drop=True)

    pending: dict[str, tuple[str, str | None, pd.Series]] = {}
    with st.form(f"cal_form_{member_email}_{ws}"):
        for day, grp in cal.groupby("_date", sort=True):
            st.markdown(
                f"<div class='cal-daymark'>{pd.Timestamp(day).strftime('%A, %d %b')}"
                f"<span class='slot-count'>{len(grp)} slot{'s' if len(grp)!=1 else ''}</span></div>",
                unsafe_allow_html=True,
            )
            for card in _merge_calendar_runs(grp):
                r = card["_rep"]
                task = r["task_type"]
                css = _task_css(task)
                sub_bits = [_txt_safe(r.get("batch_code")), _txt_safe(r.get("c_alias")),
                            _txt_safe(r.get("slot_name")), _txt_safe(r.get("program_name"))]
                if task == "other" and r.get("other_note"):
                    sub_bits.append(f"“{r['other_note']}”")
                sub_line = " · ".join(b for b in sub_bits if b)

                cA, cB = st.columns([4, 1.6])
                with cA:
                    st.markdown(
                        f"""<div class="tcard tcard-{css}">
                          <div class="tcard-top">🕑 {card['slot_time']}
                            <span class="tchip tchip-{css}">{db.TASK_LABELS.get(task, task)}</span></div>
                          <div class="tcard-sub">{sub_line}</div>
                        </div>""",
                        unsafe_allow_html=True,
                    )
                with cB:
                    key = f"{r['_date']}|{card['_members'][0]['slot_time']}"
                    if task == "evaluation":
                        st.markdown(
                            "<div class='locked-status'>🔒 via Evaluation<br>"
                            "<span style='font-weight:400;opacity:.75'>change on Sessions tab</span></div>",
                            unsafe_allow_html=True,
                        )
                    elif is_editable:
                        # Options = this slot's own CMIS-derived default first,
                        # then the manual override tasks (dedup, keep order).
                        default_task = r.get("default_task") or "mock_interview"
                        override_tasks = ["training", "project_involvement", "other"]
                        opts = [default_task] + [t for t in override_tasks
                                                 if t != default_task]
                        choice = st.selectbox(
                            "task", opts,
                            index=opts.index(task) if task in opts else 0,
                            format_func=lambda t: db.TASK_LABELS.get(t, t),
                            key=f"tk_{key}", label_visibility="collapsed",
                        )
                        note = None
                        if choice == "other":
                            note = st.text_input(
                                "note", value=r.get("other_note") or "",
                                key=f"nt_{key}", label_visibility="collapsed",
                                placeholder="What kind of task?",
                            )
                        if choice != task or (choice == "other" and note != (r.get("other_note") or "")):
                            pending[key] = (choice, note, card["_members"])
                    else:
                        st.markdown(f"<div class='locked-status'>{db.TASK_LABELS.get(task, task)}</div>",
                                    unsafe_allow_html=True)

        saved = st.form_submit_button("💾  Save calendar changes", type="primary",
                                       use_container_width=True, disabled=not is_editable)

    if saved:
        if not pending:
            st.info("No changes to save.")
        else:
            n_slots = 0
            for _, (new_task, note, members) in pending.items():
                # A merged card writes to EVERY 30-min slot it spans, so the
                # DB ends up identical to changing each slot by hand. Each
                # member keeps its own slot_time/slot_name/default_task, since
                # merging never crosses a c_alias boundary (see
                # _merge_calendar_runs) — but being explicit here is cheap
                # insurance against that ever changing.
                for m in members:
                    db.set_slot_task(
                        member_email, member_role, m["_date"], m["slot_time"],
                        m.get("slot_name"), new_task, other_note=note, set_by=user["email"],
                        default_task=m.get("default_task"),
                    )
                    n_slots += 1
            db.clear_app_caches()
            st.success(f"Saved {n_slots} slot{'s' if n_slots != 1 else ''} across "
                       f"{len(pending)} card{'s' if len(pending) != 1 else ''}.")
            st.rerun()


def _task_css(task_type: str) -> str:
    return {
        "mock_interview": "mock", "teaching": "teach",
        "evaluation": "eval", "training": "train",
        "project_involvement": "proj", "other": "other",
    }.get(task_type, "mock")


def _sessions_tab(user, role):
    core_options = _core_options_for(role, user["email"])
    if not core_options:
        st.warning("No Core AE mapping found for your account in core_ae_faculty_map.")
        return

    c1, _ = st.columns([2, 3])
    with c1:
        core_ae_email = st.selectbox("Core AE Member", core_options)

    faculty = db.faculty_emails_for_core(core_ae_email)
    if not faculty:
        st.info(f"No faculty mapped to {core_ae_email} in core_ae_faculty_map.")
        return

    # A cheap MIN/MAX/COUNT probe sizes the date pickers. The tab used to pull
    # every session row this faculty has in CMIS -- a horizon that can run to
    # late 2027 -- purely to read .min()/.max() off the frame, then discard
    # ~95% of it with a pandas filter. Every later pandas pass then paid for
    # rows nobody would ever see.
    lo_d, hi_d, n_total = db.faculty_date_bounds(tuple(faculty))
    if not lo_d or not hi_d:
        st.info("No CMIS sessions found for this Core AE's faculty.")
        return

    with st.expander(
        f"🔎  Filters · {n_total:,} sessions in CMIS ({lo_d} → {hi_d})", expanded=True
    ):
        # Dates come FIRST now, because the fetch below is bounded by them.
        d1, d2, d3 = st.columns(3)
        default_from = max(lo_d, date.today())
        if default_from > hi_d:
            default_from = lo_d
        # allow the picker to reach CMIS's global max (e.g. Oct 2027), not just
        # this AE's own last session — so future dates are always selectable.
        g_lo, g_hi = db.cmis_date_bounds()
        pick_min = g_lo or lo_d
        pick_max = g_hi or hi_d
        with d1:
            date_from = st.date_input("From", value=default_from, min_value=pick_min, max_value=pick_max)
        with d2:
            date_to = st.date_input(
                "To", value=min(hi_d, default_from + timedelta(days=13)),
                min_value=pick_min, max_value=pick_max,
            )
        with d3:
            # "Extended AE claimed sessions" is the one Core AEs kept asking
            # for: from a Core AE login there was previously no way to see
            # what the Extended AE team had already taken.
            only_open = st.selectbox(
                "Show",
                [
                    "All sessions",
                    "Unclaimed only",
                    "My claims only",
                    "Extended AE claimed sessions",
                    "Core AE claimed sessions",
                    "Mock Interviews only",
                ],
            )

        if date_to < date_from:
            st.warning("‘To’ is before ‘From’ — showing nothing. Widen the range.")
            return

        with st.spinner("Fetching sessions from CMIS…"):
            sessions = db.fetch_sessions_range_for_faculty(
                tuple(faculty), date_from, date_to
            )

        if sessions.empty:
            st.info(f"No CMIS sessions for this Core AE's faculty between {date_from} and {date_to}.")
            return

        sessions = sessions.copy()
        sessions["_trainer"] = (
            sessions["f_name"].fillna("") + " " + sessions["l_name"].fillna("")
        ).str.strip()
        sessions["_date"] = pd.to_datetime(sessions["s_date"]).dt.date

        # Trainer/batch choices now reflect the chosen window, which is more
        # useful anyway — no more scrolling past trainers who have nothing on.
        f1, f2 = st.columns(2)
        with f1:
            trainers = ["All trainers"] + sorted(sessions["_trainer"].dropna().unique().tolist())
            pick_trainer = st.selectbox("Trainer", trainers)
        with f2:
            pool = sessions if pick_trainer == "All trainers" else sessions[sessions["_trainer"] == pick_trainer]
            batches = ["All batches"] + sorted(pool["batch_code"].dropna().unique().tolist())
            pick_batch = st.selectbox("Batch code", batches)

        # CMIS splits a long class into consecutive 30-min rows (same trainer,
        # same batch, back-to-back). Merging them shows one row per real class.
        merge_slots = st.checkbox(
            "Merge back-to-back slots into one class",
            value=True,
            help="CMIS records a 2-hour class as four 30-minute rows. "
                 "Leave this on to see one row per real class — claiming it "
                 "claims every 30-minute slot underneath in one tap. Untick to "
                 "work with the raw 30-minute slots individually.",
        )

    # Calendar tab reads these directly so both tabs always show the same
    # window — Sessions is the source of truth here, Calendar has no
    # independent date picker of its own.
    st.session_state["shared_from"] = date_from
    st.session_state["shared_to"] = date_to

    # Runs automatically whenever the date range is known — no admin action
    # needed. Cached for 10 minutes per range so repeated page loads/reruns
    # don't redo the full allocation; the underlying write is idempotent
    # either way, so this is purely a "don't do it more than necessary" cache.
    mi_run = db.ensure_mock_interviews_assigned(date_from, date_to, cap_per_week=3)
    if role in ("admin", "extended_ae"):
        st.caption(
            f"🎯 Mock Interview auto-assign for {date_from} → {date_to}: "
            f"{mi_run['candidates']} candidate session(s) found system-wide, "
            f"{mi_run['assigned']} newly assigned this run "
            f"(0 is expected if everyone eligible is already at cap or "
            f"there's simply nothing free left in this range)."
        )


    if role == "extended_ae":
        my_mi = db.get_my_mock_interview_claims(user["email"], date_from, date_to)
        if not my_mi.empty:
            st.markdown("#### 🎯 My Mock Interviews")
            st.caption(
                "Auto-assigned Mock Interview sessions for you to observe/evaluate — "
                "these can be from any trainer, not just your own Core AE's pod. "
                "Unselect any you can't make."
            )
            with st.form("my_mi_form"):
                mi_pending: dict[int, str] = {}
                for _, r in my_mi.sort_values(["_date", "slot_time"]).iterrows():
                    trainer = f"{r.get('f_name') or ''} {r.get('l_name') or ''}".strip() or "Unknown trainer"
                    day_lbl = pd.to_datetime(r["_date"]).strftime("%a, %d %b")
                    cA, cB = st.columns([4, 1.3])
                    with cA:
                        st.markdown(
                            f"<div class='scard scard-mine'>"
                            f"<div class='scard-top'>🕑 {day_lbl} · {r['slot_time']}</div>"
                            f"<div class='scard-sub'>{trainer} · {r.get('batch_code') or ''} · "
                            f"{r.get('c_alias') or ''} · {r.get('program_name') or ''}</div></div>",
                            unsafe_allow_html=True,
                        )
                    with cB:
                        mi_opts = ["Selected", "Not Selected"]
                        cur = r["status"] if r["status"] in mi_opts else "Selected"
                        choice = st.selectbox(
                            "status", mi_opts, index=mi_opts.index(cur),
                            key=f"mi_{r['id']}", label_visibility="collapsed",
                        )
                        if choice != cur:
                            mi_pending[r["id"]] = choice
                if st.form_submit_button("💾  Save my Mock Interview choices", type="primary"):
                    for _id, new_status in mi_pending.items():
                        row = my_mi[my_mi["id"] == _id].iloc[0]
                        db.upsert_mock_interview_assignment(
                            user["email"], row["session_date"], row["slot_time"],
                            row["batch_code"], row["c_alias"], row.get("trainer_email"),
                            row.get("trainer_name"), row.get("program_name"),
                            status=new_status, source="manual",
                        )
                    if mi_pending:
                        db.clear_app_caches()
                        st.success(f"Updated {len(mi_pending)} Mock Interview selection"
                                   f"{'s' if len(mi_pending) != 1 else ''}.")
                        st.rerun()
                    else:
                        st.info("No changes to save.")

    if pick_trainer != "All trainers":
        sessions = sessions[sessions["_trainer"] == pick_trainer]
    if pick_batch != "All batches":
        sessions = sessions[sessions["batch_code"] == pick_batch]
    sessions = sessions[(sessions["_date"] >= date_from) & (sessions["_date"] <= date_to)]

    # ---- claim-status filter -------------------------------------------
    if only_open == "Mock Interviews only":
        aliases = {a.lower() for a in db.MOCK_INTERVIEW_ALIASES}
        sessions = sessions[
            sessions["c_alias"].fillna("").str.lower().isin(aliases)
        ]
    elif only_open != "All sessions":
        # Vectorised key build — the old row-wise .apply() walked every one of
        # the (often several thousand) filtered rows in Python before a single
        # card was drawn.
        keys = (
            sessions["_date"].astype(str) + "|"
            + sessions["slot_time"].astype(str) + "|"
            + sessions["batch_code"].fillna("").astype(str)
        )

        if only_open in ("Unclaimed only", "My claims only"):
            vis = db.get_visible_selections(role, user["email"], date_from, date_to)
            mine = set()
            if not vis.empty:
                claimed_rows = vis[vis["status"].isin(CLAIMED)]
                mine = set(
                    claimed_rows["session_date"].astype(str) + "|"
                    + claimed_rows["slot_time"].astype(str) + "|"
                    + claimed_rows["batch_code"].fillna("").astype(str)
                )
            if only_open == "Unclaimed only":
                sessions = sessions[~keys.isin(mine)]
            else:
                sessions = sessions[keys.isin(mine)]
        else:
            # Team-wide view: who holds what, across both role tables.
            team = db.get_team_selections(core_ae_email, date_from, date_to)
            want_role = "extended_ae" if only_open.startswith("Extended") else "core_ae"
            held = set()
            if not team.empty:
                hits = team[
                    team["status"].isin(CLAIMED) & (team["owner_role"] == want_role)
                ]
                held = set(
                    hits["session_date"].astype(str) + "|"
                    + hits["slot_time"].astype(str) + "|"
                    + hits["batch_code"].fillna("").astype(str)
                )
            sessions = sessions[keys.isin(held)]

    if sessions.empty:
        st.info("No sessions match these filters. Try widening the date range.")
        return

    # NOTE: no row cap here — pagination in _sessions_table handles volume,
    # so the metrics and page count reflect the TRUE filtered total.
    if merge_slots:
        sessions = _merge_consecutive(sessions)

    _sessions_table(sessions, core_ae_email, date_from, date_to, role, user["email"])


def _core_options_for(role: str, email: str) -> list[str]:
    """
    Which Core AEs this user may work with.

      admin        -> everyone (override)
      core_ae      -> themselves
      extended_ae  -> only their paired Core AE, per the ae_extae table.
                      Falls back to the full list if no pairing is recorded,
                      so a missing row never locks someone out.
    """
    all_cores = db.list_core_ae_emails()
    if role == "admin":
        return all_cores
    if role == "core_ae":
        return [c for c in all_cores if c.lower() == email.lower()] or all_cores

    # extended_ae — scope to their pair
    paired = db.core_ae_for_extended(email)
    if paired:
        return [paired]
    return all_cores


def _session_key(r) -> str:
    return f"{r['s_date']}|{r['slot_time']}|{r.get('batch_code','')}"


def _txt_safe(v) -> str:
    """Clean display text: '' for NULL/NaN/'nan' so cards never show junk."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none", "null") else s


def _badge(status: str, claimed: bool) -> str:
    if status == "Confirmed":
        return '<span class="badge badge-confirmed">✓ Confirmed</span>'
    if status == "Selected":
        return '<span class="badge badge-selected">✓ Selected</span>'
    if status == "Choosing":
        return '<span class="badge badge-choosing">⏳ Choosing</span>'
    return '<span class="badge badge-available">◷ Available</span>'


def _merge_consecutive(df: pd.DataFrame) -> pd.DataFrame:
    """
    Collapse back-to-back CMIS slots into one row per class.

    CMIS stores a 2-hour class as four consecutive 30-minute rows with the same
    trainer, batch and date. This groups those into a single row whose
    slot_time spans start->end, so the list reflects real classes.
    """
    if df.empty:
        return df

    d = df.copy()
    _slots = d["slot_time"].astype(str)
    d["_start"] = _slots.str.split("-").str[0].str.strip()
    d["_end"] = _slots.str.split("-").str[-1].str.strip()
    d["_sort"] = pd.to_datetime(d["_start"], format="%I:%M %p", errors="coerce")
    d = d.sort_values(["email_id", "_date", "batch_code", "_sort"]).reset_index(drop=True)

    # A run breaks whenever the trainer, date or batch changes, or the
    # previous slot's end time isn't this slot's start time. Expressing that
    # as a shifted comparison and a cumulative sum turns what was a Python
    # loop over every row into three vectorised passes — the same result, but
    # it no longer scales badly with the size of the date range.
    _bkey = (
        d["email_id"].astype(str) + "\x1f"
        + d["_date"].astype(str) + "\x1f"
        + d["batch_code"].fillna("").astype(str)
    )
    broke = (_bkey != _bkey.shift(1)) | (d["_start"] != d["_end"].shift(1))
    d["_grp"] = broke.cumsum()

    grouped = d.groupby("_grp", sort=False)
    res = grouped.head(1).copy().reset_index(drop=True)

    agg = grouped.agg(
        _members=("slot_time", lambda s: [str(x) for x in s]),
        _merged_count=("slot_time", "size"),
        _span_end=("_end", "last"),
        _span_start=("_start", "first"),
    ).reset_index(drop=True)

    # Total duration across the run, falling back to the first row's value
    # when CMIS didn't record one.
    if "time_duration" in d.columns:
        dur = grouped["time_duration"].apply(
            lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum()
        ).reset_index(drop=True)
        res["time_duration"] = dur.where(dur > 0, res["time_duration"])

    # the original 30-min slot strings this class is built from — every
    # claim/highlight/task write fans out across ALL of these so the DB
    # stays identical to what an unmerged view would have written.
    res["_members"] = agg["_members"]
    res["_merged_count"] = agg["_merged_count"]
    multi = agg["_merged_count"] > 1
    res.loc[multi, "slot_time"] = (
        agg.loc[multi, "_span_start"] + " - " + agg.loc[multi, "_span_end"]
    )

    return res.drop(columns=["_start", "_end", "_sort", "_grp"], errors="ignore")


def _slot_start_minutes(slot: str) -> int:
    """Minutes-since-midnight for a slot's start, e.g. '11:00 AM - 11:30 AM' -> 660.

    Used to sort slots chronologically. slot_time is a plain string, and a
    plain string sort puts every '0…AM/PM' slot before every '1…AM/PM' slot
    regardless of time of day (lexicographic '0' < '1') — so '02:30 PM' would
    sort ahead of '11:00 AM' even though 11:00 AM comes first in the day.
    Unparseable values sort last rather than raising, so one bad row doesn't
    break the whole day's ordering.
    """
    if not slot or "-" not in str(slot):
        return 10**6
    try:
        start = str(slot).split("-", 1)[0].strip()
        t = pd.to_datetime(start, format="%I:%M %p")
        return t.hour * 60 + t.minute
    except Exception:
        return 10**6


def _parse_slot_minutes(slot: str) -> int | None:
    """Derive minutes from a slot string like '02:00 PM - 02:30 PM'."""
    if not slot or "-" not in str(slot):
        return None
    try:
        a, b = [s.strip() for s in str(slot).split("-", 1)]
        t1 = pd.to_datetime(a, format="%I:%M %p")
        t2 = pd.to_datetime(b, format="%I:%M %p")
        mins = int((t2 - t1).total_seconds() // 60)
        return mins if mins > 0 else None
    except Exception:
        return None


def _mins_to_text(mins: int) -> str:
    if mins < 60:
        return f"{mins} min"
    h, m = divmod(mins, 60)
    return f"{h}h" if m == 0 else f"{h}h {m}m"


def _cmis_duration_minutes(r) -> int | None:
    """The authoritative CMIS duration, in minutes.

    CMIS `time_duration` is stored in DECIMAL HOURS (0.5 = 30 min). This is the
    field of record, so we always trust it when present. Only when it's
    missing/blank do we derive from the slot string.
    """
    raw = r.get("time_duration")
    try:
        if raw is not None and str(raw).strip() != "":
            hours = float(raw)
            if hours > 0:
                return int(round(hours * 60))
    except (TypeError, ValueError):
        pass
    return _parse_slot_minutes(r.get("slot_time"))


def _fmt_duration(r) -> str:
    """
    Duration shown in the table — taken DIRECTLY from CMIS `time_duration`
    (converted hours->minutes) so it always matches the CMIS record. Falls back
    to slot arithmetic only when CMIS has no value.
    """
    mins = _cmis_duration_minutes(r)
    return _mins_to_text(mins) if mins is not None else "—"


def _sessions_table(sessions, core_ae_email, date_from, date_to, role, user_email):
    """
    Card-based session list, grouped by time slot. Each session is a clean card
    with a one-tap claim control. Cross-visibility: everyone on the team sees
    each other's picks; only the owner can change a claimed session.
    """
    can_select = role in ("extended_ae", "core_ae", "admin")

    team = db.get_team_selections(core_ae_email, date_from, date_to)
    status_by_key, owner_by_key, ownrole_by_key = {}, {}, {}
    if not team.empty:
        for _, s in team.iterrows():
            k = f"{s['session_date']}|{s['slot_time']}|{s['batch_code'] or ''}"
            status_by_key[k] = s["status"]
            owner_by_key[k] = s["owner_email"]
            ownrole_by_key[k] = s["owner_role"]

    df = sessions.copy()
    # Vectorised — this used to be a row-wise .apply() over the whole filtered
    # set, which is pure Python overhead on every rerun.
    df["_key"] = (
        df["_date"].astype(str) + "|"
        + df["slot_time"].astype(str) + "|"
        + df["batch_code"].fillna("").astype(str)
    )

    def _members_of(r) -> list[str]:
        """The raw 30-min slot strings behind a row. A merged class carries the
        list in `_members`; an unmerged row is just its own slot."""
        m = r.get("_members")
        if isinstance(m, (list, tuple)) and len(m) > 0:
            return [str(x) for x in m]
        return [str(r["slot_time"])]

    def _row_state(r):
        """Status/owner/role for a (possibly merged) row. A claimed member wins,
        so a merged class shows as claimed if any slot underneath is claimed;
        otherwise it falls back to the first member's state."""
        batch = r["batch_code"] or ""
        keys = [f"{r['_date']}|{m}|{batch}" for m in _members_of(r)]
        for k in keys:
            stt = status_by_key.get(k, "Not Selected")
            if stt in CLAIMED or stt == "Choosing":
                return pd.Series([stt, owner_by_key.get(k), ownrole_by_key.get(k)])
        k0 = keys[0]
        return pd.Series([status_by_key.get(k0, "Not Selected"),
                          owner_by_key.get(k0), ownrole_by_key.get(k0)])

    if status_by_key:
        df[["Status", "_owner", "_ownrole"]] = df.apply(_row_state, axis=1)
    else:
        # Overwhelmingly the common case early in a week: nobody has claimed
        # anything yet, so there is nothing to look up. Skipping the row-wise
        # apply entirely here is worth more than any micro-optimisation
        # inside it.
        df["Status"] = "Not Selected"
        df["_owner"] = None
        df["_ownrole"] = None

    df["Trainer"] = (df["f_name"].fillna("") + " " + df["l_name"].fillna("")).str.strip()
    df["_editable"] = df["_owner"].isna() | (
        df["_owner"].fillna("").str.lower() == user_email.lower()
    )

    # ---- TRAINER-FIRST ordering ----
    # Sessions are blocked per trainer (all of Jency's sessions in one go, then
    # Subash's, ...). The trainer whose earliest slot comes first leads the
    # list; inside a block, sessions run chronologically. Sorting happens
    # BEFORE pagination so trainer blocks stay contiguous across pages.
    # Vectorised: parse every slot's start time in two passes over the whole
    # column instead of one Python call per row.
    _starts = df["slot_time"].astype(str).str.split("-").str[0].str.strip()
    _t = pd.to_datetime(_starts, format="%I:%M %p", errors="coerce")
    _fallback = _t.isna()
    if _fallback.any():
        # CMIS sometimes drops the space: "07:30PM"
        _t = _t.mask(_fallback, pd.to_datetime(_starts[_fallback], errors="coerce"))
    _day = pd.to_datetime(df["_date"])
    _offset = pd.to_timedelta(
        _t.dt.hour.fillna(23) * 3600 + _t.dt.minute.fillna(59) * 60, unit="s"
    )
    df["_ts"] = _day + _offset  # unparseable -> pushed to end of day
    df["_first_ts"] = df.groupby("Trainer")["_ts"].transform("min")
    df = df.sort_values(
        ["_first_ts", "Trainer", "_ts", "batch_code"], kind="stable"
    ).reset_index(drop=True)

    total = len(df)
    claimed = int(df["Status"].isin(list(CLAIMED)).sum())
    mine = int((df["_owner"].fillna("").str.lower() == user_email.lower()).sum())
    available = total - claimed

    st.markdown(
        f"""<div class="stat-row">
          <div class="stat stat-total"><div class="stat-num">{total:,}</div><div class="stat-lbl">Sessions</div></div>
          <div class="stat stat-avail"><div class="stat-num">{available:,}</div><div class="stat-lbl">◷ Available</div></div>
          <div class="stat stat-claim"><div class="stat-num">{claimed:,}</div><div class="stat-lbl">✓ Claimed by team</div></div>
          <div class="stat stat-mine"><div class="stat-num">{mine:,}</div><div class="stat-lbl">★ Mine</div></div>
        </div>""",
        unsafe_allow_html=True,
    )

    st.markdown(
        """<div class="help-strip">
          <span><b>Tip:</b> pick a status on any available session, then <b>Save</b> at the bottom.</span>
          <span class="legend">
            <span class="lg lg-avail">◷ Available</span>
            <span class="lg lg-mine">★ Mine</span>
            <span class="lg lg-lock">🔒 Teammate's</span>
          </span>
        </div>""",
        unsafe_allow_html=True,
    )

    # 40 cards meant ~120 Streamlit elements per page (a column pair, a
    # markdown block and a selectbox each). That element count, not the SQL,
    # is what made the page feel sluggish. 25 keeps it comfortably responsive.
    # ---- renderer choice -------------------------------------------------
    # The card list is pretty but expensive: each row costs a column pair, a
    # markdown block and a selectbox, so a 25-row page is ~100 Streamlit
    # elements and every rerun re-serialises all of them. The table is a
    # SINGLE element regardless of row count, which is why it stays smooth
    # where the cards crawl. Cards remain available for anyone who prefers
    # them.
    vcol1, vcol2 = st.columns([2, 3])
    with vcol1:
        view_mode = st.radio(
            "View",
            ["⚡ Table (fast)", "🗂 Cards"],
            horizontal=True,
            key="sessions_view_mode",
            label_visibility="collapsed",
        )
    fast = view_mode.startswith("⚡")

    pending: dict = {}  # key -> (new status, row) — collected then saved together

    if fast:
        with vcol2:
            st.caption(
                "Tick **Claim** on the sessions you're taking, then Save. "
                "Rows held by a teammate are locked."
            )
        me = user_email.lower()
        grid = pd.DataFrame({
            "Claim": df["_owner"].fillna("").str.lower().eq(me)
                     & df["Status"].isin(list(CLAIMED)),
            "Date": pd.to_datetime(df["_date"]).dt.strftime("%a, %d %b"),
            "Time": df["slot_time"].astype(str),
            "Trainer": df["Trainer"],
            "Batch": df["batch_code"].fillna(""),
            "Module": df["c_alias"].fillna(""),
            "Held by": [
                "★ You" if (o or "").lower() == me
                else (f"🔒 {o.split('@')[0]}" if o and s in CLAIMED else "◷ Available")
                for o, s in zip(df["_owner"].fillna(""), df["Status"])
            ],
        }).reset_index(drop=True)

        edited = st.data_editor(
            grid,
            hide_index=True,
            use_container_width=True,
            height=min(640, 90 + 35 * min(len(grid), 16)),
            disabled=["Date", "Time", "Trainer", "Batch", "Module", "Held by"],
            column_config={
                "Claim": st.column_config.CheckboxColumn("Claim", width="small"),
            },
            key="sessions_fast_editor",
        )

        before = grid["Claim"].tolist()
        after = edited["Claim"].tolist()
        locked_attempts = 0
        for i, (b, a) in enumerate(zip(before, after)):
            if b == a:
                continue
            row = df.iloc[i]
            if not row["_editable"]:
                locked_attempts += 1
                continue
            pending[row["_key"]] = ("Selected" if a else "Not Selected", row)
        if locked_attempts:
            st.warning(
                f"{locked_attempts} row(s) are held by a teammate and were ignored."
            )
        saved = st.button("💾  Save changes", type="primary", use_container_width=True)

    else:
        saved = _render_session_cards(df, user_email, can_select, pending)

    if saved:
        if not pending:
            st.info("No changes to save — pick a status on a session first.")
        else:
            n = 0
            for key, (new_status, r) in pending.items():
                # A merged class writes the claim to EVERY 30-min slot it spans,
                # so the DB is identical to claiming each slot by hand. An
                # unmerged row has a single member (its own slot).
                members = r.get("_members")
                if not isinstance(members, (list, tuple)) or not members:
                    members = [r["slot_time"]]
                for m_slot in members:
                    sel_id = db.upsert_selection_for_role(
                        role, user_email, r["_date"], m_slot,
                        r["m_code"], r["batch_code"], new_status,
                    )
                    db.set_highlight_flag(
                        r["_date"], m_slot, r["batch_code"],
                        core_ae_email, user_email, new_status in CLAIMED,
                    )
                    # Mock Interview default mechanism: claiming/un-claiming an
                    # Evaluation here removes/restores the default on the
                    # Calendar tab for this exact (date, slot_time).
                    try:
                        db.sync_slot_task_from_evaluation(
                            user_email, role, r["_date"], m_slot,
                            new_status in CLAIMED, sel_id,
                        )
                    except Exception:
                        pass
                n += 1
            try:
                db.recompute_weekly_summary(core_ae_email, date_from)
            except Exception:
                pass
            db.clear_app_caches()
            st.success(f"Saved {n} change{'s' if n != 1 else ''}.")
            st.rerun()


def _team_rollup(core_ae_email, week_start, week_end):
    st.subheader("My Extended AE Team — Selected Sessions")
    sel = db.get_selections_for_role("extended_ae", None, week_start, week_end)
    if sel.empty:
        st.caption("No Extended AE selections yet for this week.")
        return
    claimed = sel[sel["status"].isin(list(CLAIMED) + ["Choosing"])]
    if claimed.empty:
        st.caption("No Extended AE selections yet for this week.")
        return
    view = claimed[["owner_email", "session_date", "slot_time", "module", "batch_code", "status"]]
    view = view.rename(columns={"owner_email": "Extended AE", "session_date": "Date",
                                "slot_time": "Time", "module": "Module",
                                "batch_code": "Batch", "status": "Status"})
    st.dataframe(view, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
def main():
    if "user" not in st.session_state:
        login_view()
    else:
        dashboard()


def _render_session_cards(df, user_email, can_select, pending) -> bool:
    """The original card list, kept as an opt-in view.

    Costs roughly four Streamlit elements per row, so it is paginated hard.
    Fills `pending` in place and returns whether Save was pressed.
    """
    PER_PAGE = 25
    total = len(df)
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    if pages > 1:
        p1, p2 = st.columns([1, 4])
        with p1:
            page = st.number_input("Page", 1, pages, 1, 1, key="page_no")
        with p2:
            st.markdown(
                f"<div style='padding-top:32px;font-size:.82rem;opacity:.6'>"
                f"Page {int(page)} of {pages} · {total:,} sessions</div>",
                unsafe_allow_html=True,
            )
    else:
        page = 1

    lo = (int(page) - 1) * PER_PAGE
    chunk = df.iloc[lo:lo + PER_PAGE].copy().reset_index(drop=True)

    # Duration is display-only, so it's formatted for the 25 rows actually on
    # screen rather than for every row in the range.
    chunk["Duration"] = chunk.apply(_fmt_duration, axis=1)

    # ---- render as cards grouped by TRAINER (all their sessions in one go),
    #      ordered so the trainer with the earliest slot comes first ----
    def _txt(v) -> str:
        """Clean display text: '' for NULL/NaN/'nan' so cards never show junk."""
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        s = str(v).strip()
        return "" if s.lower() in ("nan", "none", "null") else s

    # `pending` is the caller's dict — fill it, never rebind it.

    with st.form(f"claim_form_{page}"):
        for trainer, grp in chunk.groupby("Trainer", sort=False):
            first = grp.iloc[0]
            span_lo = pd.to_datetime(grp["_date"].min()).strftime("%d %b")
            span_hi = pd.to_datetime(grp["_date"].max()).strftime("%d %b")
            span = span_lo if span_lo == span_hi else f"{span_lo} → {span_hi}"
            st.markdown(
                f"<div class='slot-head'>👤 {trainer or _txt(first.get('email_id')) or 'Unknown trainer'}"
                f" &nbsp;·&nbsp; {span} "
                f"<span class='slot-count'>{len(grp)} session{'s' if len(grp)!=1 else ''}</span></div>",
                unsafe_allow_html=True,
            )
            for _, r in grp.iterrows():
                key = r["_key"]
                status = r["Status"]
                owner = r["_owner"]
                editable = r["_editable"]
                claimed_row = status in CLAIMED

                # ownership label
                if owner and status != "Not Selected":
                    if owner.lower() == user_email.lower():
                        who = "<span class='pill pill-mine'>★ Mine</span>"
                    else:
                        nm = owner.split("@")[0]
                        tag = "Core AE" if r["_ownrole"] == "core_ae" else "Ext AE"
                        who = f"<span class='pill pill-lock'>🔒 {nm} · {tag}</span>"
                elif not claimed_row:
                    who = "<span class='pill pill-avail'>◷ Available</span>"
                else:
                    who = ""

                day_lbl = pd.to_datetime(r["_date"]).strftime("%a, %d %b")
                # CMIS extras: centre alias, slot name, module code — shown when present
                sub_bits = [r["Duration"], f"<b>{_txt(r.get('batch_code'))}</b>"]
                for extra in (_txt(r.get("c_alias")), _txt(r.get("slot_name")),
                              _txt(r.get("m_code")), _txt(r.get("program_name"))):
                    if extra:
                        sub_bits.append(extra)
                sub_line = " · ".join(b for b in sub_bits if b and b != "<b></b>")

                cA, cB = st.columns([4, 1.3])
                with cA:
                    st.markdown(
                        f"""<div class="scard {'scard-mine' if (owner and owner.lower()==user_email.lower()) else ('scard-lock' if claimed_row else 'scard-avail')}">
                          <div class="scard-top">🕑 {day_lbl} &nbsp;·&nbsp; {_txt(r.get('slot_time'))} {who}</div>
                          <div class="scard-sub">{sub_line}</div>
                        </div>""",
                        unsafe_allow_html=True,
                    )
                with cB:
                    if can_select and editable:
                        # Legacy rows saved as "Choosing"/"Confirmed" under the
                        # old 4-option flow aren't in STATUS_OPTIONS anymore.
                        # Compare against what the widget actually SHOWS
                        # (displayed_status), not the raw DB value — otherwise
                        # an untouched legacy row looks like a change the user
                        # never made, and Save would silently downgrade a
                        # Confirmed session to Selected.
                        if status in STATUS_OPTIONS:
                            default_idx = STATUS_OPTIONS.index(status)
                        elif status in CLAIMED:
                            default_idx = STATUS_OPTIONS.index("Selected")
                        else:
                            default_idx = 0
                        displayed_status = STATUS_OPTIONS[default_idx]
                        sel = st.selectbox(
                            "status", STATUS_OPTIONS,
                            index=default_idx,
                            key=f"st_{key}_{page}", label_visibility="collapsed",
                        )
                        if sel != displayed_status:
                            pending[key] = (sel, r)
                    else:
                        st.markdown(
                            f"<div class='locked-status'>{status}</div>",
                            unsafe_allow_html=True,
                        )

        saved = st.form_submit_button("💾  Save changes", type="primary", use_container_width=True)
    return saved


if __name__ == "__main__":
    main()
