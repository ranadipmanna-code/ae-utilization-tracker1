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
import re

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
#              logo teal as accent, higher-contrast cards.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# ANUDIP BRAND COLOURS  <-- edit these five values and the whole app follows
#
# Taken from the anudip.org visual identity: the orange of the "Donate Now"
# call-to-action, and the deep navy used for headings and the footer.
#
# NOTE: these were matched by eye from the live site, not sampled from its
# stylesheet. If Anudip has an official brand sheet with exact hex codes, drop
# them in here -- nothing else in the file needs to change, because both the
# light and dark palettes below are derived from these five values.
# ---------------------------------------------------------------------------
BRAND = {
    "teal":        "#14b8a6",   # primary — sampled from the logo mark/wordmark
    "teal_dark":   "#0d9488",   # hover / pressed
    "teal_lite":   "#2dd4bf",   # the dark theme needs a lighter teal to read
    "orange":      "#f47b20",   # secondary hue, now free for the Calendar's "project" type
    "orange_lite": "#fa9a4d",
    "navy":        "#16283c",   # headings, nav bar and footer ink
    "navy_deep":   "#0c1725",   # the dark theme canvas
    "sky":         "#1b7fc4",   # secondary link/accent blue used across the site
}

# ---------------------------------------------------------------------------
# ANUDIP LOGO — embedded once as base64 so the app has no external asset
# dependency; render everywhere via _brand_mark_html() rather than repeating
# the (long) data URI at each call site.
# ---------------------------------------------------------------------------
ANUDIP_LOGO_B64 = (
    "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E5vdPfzUid0eJJPd8HpycQiFQj1+Y4xBURS0trZmdLjCUIYM/Dl27BiOHTvW3905bVAUDgWW1FO6feRv/eVx1mvQEIFpmkREdPjwYTr33HNpz549Cb/H/3/btm2kaRq98sorRESk6zqZpkm6rtOyZcuorKyMrrjiChJCkBCiz32SZVtaWmjWrFlUV1dH06ZNoxkzZtDUqVOprq6OXnzxRSIiMgyjz+1kE/Kejx07RpdddhmVlZXR97//fSIaOH1MB9nPl156iS666CLn91TPUv7teDRK+8Jh2hcKUX0wmPDZFwrRvnCYWmKxtPUNBAw5tbyzsxNbtmxJKpkBoLKyEsuWLcOUKVMAwFE/77jjDrzyyit4/fXXMXnyZKccEcGMS0+rKEpGbpTymqKiIjzwwAMgIvzyl7/EH//4R6xduxZCCEyfPh2AFUFnGAZUVYUQAkIIqHGBJqZpJviId186CDsSjnPu9DVZP+Pr6n6drOPqq68G5xzr16/H2LFjQURQFMXpW7KxoLilTXw/ZLvczhQqhHASd8TXmazPmT4D0zSh6zo45zh69Cg2btzY4xo3yLrKfT6UZ1RiYLn1uqKfJpWsQ0rl+vp60jSNtm7dmvB7MsjZt6Ojg/Ly8ujll192/Xuycr3FQw89RFOnTk3bn3RId1/Jrkt1P/LaTz75hADQwYMHM2rTrc5M++emDWTa53T9WLNmDVVXV/eqHkFEphApPwNbXndhSK65k2WDIVtahUIhPP300wlryfz8fBARJk2aBKBLujHGEIvFsHr1atx88834yU9+gra2NifneqaIRqMwTRPhcBiGYcA0TRhxJ2RGo1H85je/AWMMmzZtwuOPP45wOOyUf+2113Dbbbdh5cqVeOeddxIkIABs374db7/9NgDg6aefxtNPP43m5mbnOnn/jDGsW7cO//zP/4wbb7wRq1atwvHjx8EYc+oyTRN5eXmora11xpNsib5792784Ac/wE033YRHHnkEwWAwoezhw4exbt06cM6xbt06PPfcc849rF27FpFIBDt27MBjjz2GvXv3QlEUHD16FE8++SSeffZZtLS0uPa5qakJP/rRj3DzzTfjmWeeSfg7xWk0b775Jh5++GHs378fZWVl0HU942cEwDmyONVngMvrLvTHjJILxEtuRVFcJbf8f0NDAwGgDz/8kIgs6XHnnXcS55wW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"
)


def _brand_mark_html() -> str:
    return (
        f"<div class='bb-mark'>"
        f"<img src='data:image/png;base64,{ANUDIP_LOGO_B64}' alt='Anudip Foundation'/>"
        f"</div>"
    )

# ---------------------------------------------------------------------------
# THEMES
#
# Both modes are built from BRAND above, so light and dark are the same design
# in two exposures rather than two unrelated skins.
#
# Hue assignment is deliberate — these four states sit next to each other in
# the session list, so none of them may share a hue:
#
#     Mine            Anudip teal     (the brand colour marks *your* work)
#     Open/Available  blue
#     Teammate's      green
#     Mock Interview  violet
#
# Mock Interview lives on violet, not teal, so "mine" and "MI" stay
# distinguishable. The Calendar's "project" type sits on orange -- freed up
# now that teal (sampled from the logo) is the brand accent instead.
# ---------------------------------------------------------------------------
THEMES = {
    # Warm paper white, navy ink, Anudip teal accent.
    "light": {
        "bg": "#fbfaf8", "surface": "#ffffff", "surface_2": "#f4f5f7",
        # muted was #667a8e (4.43:1 on white) -- just under WCAG AA. #5d7085
        # clears 4.5:1 on white, on the page bg AND on surface_2, which is
        # where most secondary text actually sits.
        "text": BRAND["navy"], "muted": "#5d7085", "border": "#e3e7ec",
        "accent": BRAND["teal"], "accent_soft": "#f0fdfa",
        # Teal (matching the logo) is a mid-tone: navy on teal is 6:1, the
        # accessible pairing. `accent_text` is a darkened teal for when the
        # accent has to BE the text on a pale surface (5.5:1 on white).
        "on_accent": BRAND["navy"], "accent_text": "#0f766e",
        "avail_bg": "#f2f8fd", "avail_border": "#2e7cb8", "avail_text": "#14496f",
        "claim_bg": "#f1faf4", "claim_border": "#2e9e63", "claim_text": "#0c5c31",
        "done_bg": "#e6fbf7", "done_border": BRAND["teal"],
        "chip_bg": "#f1f3f6", "chip_text": "#56687c",
        "shadow": "0 1px 2px rgba(22,40,60,.05), 0 4px 16px rgba(22,40,60,.06)",
        "accent_hover": BRAND["teal_dark"], "accent_lite": BRAND["teal_lite"],
        "brandbar_bg": BRAND["navy"], "brandbar_tag": "#a8bacb", "link": BRAND["sky"],
        # task-type colors for the Calendar tab
        "mock_bg": "#f6f1fd", "mock_border": "#7c4dbe", "mock_text": "#4b2483",
        # Amber, not grey -- Training/Teaching is mandatory now, so its
        # badge needs to actually stand out in the day list.
        "teach_bg": "#fef3e0", "teach_border": "#c8850f", "teach_text": "#8a5a08",
        "train_bg": "#eff6fe", "train_border": "#3b82c4", "train_text": "#1b4e76",
        # "project" moves onto orange now that teal is the brand accent --
        # same swap logic as Mock Interview did the other direction earlier.
        "proj_bg": "#fdf3ea", "proj_border": BRAND["orange"], "proj_text": "#ad4f0f",
        "other_bg": "#fdf0f3", "other_border": "#e0577a", "other_text": "#7a1330",
        "mi_pill_text": "#ffffff",
    },
    # The same design at night: a navy canvas rather than neutral black, so the
    # teal still reads as the brand colour and not as a status indicator.
    "dark": {
        "bg": BRAND["navy_deep"], "surface": "#15202c", "surface_2": "#1b2836",
        "text": "#e9eef4", "muted": "#90a2b6", "border": "#263543",
        "accent": BRAND["teal_lite"], "accent_soft": "#0f2e2b",
        # On the dark canvas the lighter teal already clears AA as text
        # (9.7:1 against navy_deep), so accent_text is just the accent.
        "on_accent": BRAND["navy_deep"], "accent_text": BRAND["teal_lite"],
        "avail_bg": "#0f2231", "avail_border": "#4e9bc9", "avail_text": "#a9d2ee",
        "claim_bg": "#0f241a", "claim_border": "#3fb87c", "claim_text": "#8fe6b6",
        "done_bg": "#0f2e2b", "done_border": BRAND["teal_lite"],
        "chip_bg": "#222f3c", "chip_text": "#b4c2d0",
        "shadow": "0 1px 2px rgba(0,0,0,.45), 0 8px 24px rgba(0,0,0,.55)",
        "accent_hover": BRAND["teal"], "accent_lite": BRAND["teal_lite"],
        "brandbar_bg": "#12202e", "brandbar_tag": "#8fa3b7", "link": "#63b3e8",
        # task-type colors for the Calendar tab
        "mock_bg": "#201634", "mock_border": "#a87be0", "mock_text": "#d8c3f7",
        "teach_bg": "#2c2008", "teach_border": "#f0b429", "teach_text": "#f6cc5c",
        "train_bg": "#12222f", "train_border": "#4f9fe0", "train_text": "#a9d6fb",
        "proj_bg": "#2b1c10", "proj_border": BRAND["orange_lite"], "proj_text": BRAND["orange_lite"],
        "other_bg": "#2e1520", "other_border": "#e26f90", "other_text": "#f7b8ca",
        "mi_pill_text": "#201634",
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
      @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@500;600;700&family=Open+Sans:wght@400;500;600;700&display=swap');
      html, body, [data-testid="stAppViewContainer"], .stApp {{
        background:{t['bg']} !important; color:{t['text']} !important;
        font-family:"Open Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
        -webkit-font-smoothing:antialiased;
        -moz-osx-font-smoothing:grayscale;
        letter-spacing:-0.006em;
      }}
      [data-testid="stHeader"] {{ background:transparent !important; }}
      /* Streamlit's own sidebar collapse/expand control -- the pale default
         is nearly invisible against the page background in either theme. */
      [data-testid="stSidebarCollapsedControl"] button,
      [data-testid="stSidebarCollapsedControl"] svg {{
        color:{t['text']} !important; fill:{t['text']} !important;
      }}
      [data-testid="stSidebarCollapsedControl"] button {{
        background:{t['surface_2']} !important; border:1px solid {t['border']} !important;
      }}
      [data-testid="stSidebarCollapsedControl"] button:hover {{
        background:{t['chip_bg']} !important;
      }}
      .block-container {{ padding-top:2.2rem; padding-bottom:5rem; max-width:1120px; }}
      h1,h2,h3,h4 {{ font-family:"Poppins","Open Sans",sans-serif !important; }}
      h1 {{ font-weight:700; letter-spacing:-.02em; font-size:2rem; margin-bottom:0; line-height:1.18; }}
      h2 {{ font-weight:600; letter-spacing:-.01em; font-size:1.4rem; }}
      h3 {{ font-weight:600; letter-spacing:-.01em; font-size:1.12rem; }}
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
      /* Refresh needs to read as an actual action, not blend into the quiet
         sign-out style. st.container(key="refresh_btn") gives a stable,
         version-proof CSS hook (Streamlit always emits st-key-<name> for a
         keyed container) rather than guessing at internal button attributes.
         Filled with the theme's accent -- darker teal in light mode, lighter
         teal in dark mode -- already tuned per theme via accent/on_accent. */
      .st-key-refresh_btn .stButton > button {{
        background:{t['accent']} !important; color:{t['on_accent']} !important;
        border:none !important; font-weight:600 !important;
      }}
      .st-key-refresh_btn .stButton > button:hover {{
        background:{t['accent_hover']} !important; color:{t['on_accent']} !important;
        border:none !important;
      }}
      .st-key-refresh_btn .stButton > button * {{ color:{t['on_accent']} !important; }}

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
        background:{t['accent_soft']} !important; color:{t['accent_text']} !important;
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
        background-color:{t['accent']} !important; color:{t['on_accent']} !important;
        border-radius:8px !important;
      }}
      /* hovered day */
      div[data-baseweb="calendar"] [role="gridcell"]:hover,
      div[data-baseweb="calendar"] [role="gridcell"]:hover *,
      div[data-baseweb="calendar"] [class*="Day"]:hover {{
        background-color:{t['accent_soft']} !important; color:{t['accent_text']} !important;
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
        background:{t['accent_soft']} !important; color:{t['accent_text']} !important;
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
        background:{t['accent']}; color:{t['on_accent']} !important; border:none; border-radius:10px;
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
      .stat-mi::before    {{ background:{t['mock_border']}; }}
      .stat-num {{ font-size:1.9rem; font-weight:650; letter-spacing:-.03em; line-height:1; }}
      .stat-lbl {{ font-size:.8rem; color:{t['muted']}; margin-top:6px; font-weight:500; }}
      .stat-avail .stat-num {{ color:{t['avail_text']}; }}
      .stat-claim .stat-num {{ color:{t['claim_text']}; }}
      .stat-mine .stat-num  {{ color:{t['accent_text']}; }}
      .stat-mi .stat-num    {{ color:{t['mock_text']}; }}
      @media (max-width: 1100px) {{ .stat-row {{ grid-template-columns:repeat(3,1fr); }} }}
      @media (max-width: 640px)  {{ .stat-row {{ grid-template-columns:repeat(2,1fr); }} }}

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
      .lg-mine  {{ background:{t['accent']}; color:{t['on_accent']}; }}
      .lg-lock  {{ background:{t['chip_bg']}; color:{t['muted']}; }}

      /* ---------- SECTION HEADERS (observations vs mock interviews) ------ */
      .sec-head {{
        display:flex; align-items:baseline; gap:12px; flex-wrap:wrap;
        font-size:1.02rem; font-weight:700; letter-spacing:-.02em;
        margin:26px 0 4px; padding:10px 16px; border-radius:12px;
      }}
      .sec-note {{ font-size:.76rem; font-weight:500; opacity:.75; }}
      .sec-obs {{ color:{t['text']};        background:{t['surface_2']};
                  border-left:4px solid {t['muted']}; }}
      .sec-mi  {{ color:{t['mock_text']};   background:{t['mock_bg']};
                  border-left:4px solid {t['mock_border']}; }}

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
      /* Third tone for a Mock Interview the person actively declined --
         distinct from "open/pending" (blue) and "yours/selected" (teal). */
      .scard-declined {{ border-left-color:{t['other_border']}; background:{t['other_bg']}; }}
      /* An MI keeps its ownership colour but gains a warm tint, so the two
         kinds of work stay tellable apart at a glance. */
      .scard-mi {{ background:{t['mock_bg']}; }}
      .scard-mock  {{ border-left-color:{t['mock_border']}; background:{t['mock_bg']}; }}
      .scard-top {{ font-size:.95rem; font-weight:600; letter-spacing:-.01em; color:{t['text']};
                    display:flex; align-items:center; gap:8px; flex-wrap:wrap; }}
      .scard-sub {{ font-size:.79rem; color:{t['muted']}; margin-top:4px; }}
      .scard-sub b {{ color:{t['text']}; font-weight:600; }}
      .scard-meta {{ font-size:.79rem; font-weight:400; color:{t['muted']}; margin-left:2px; }}
      .pill {{ font-size:.68rem; font-weight:600; padding:2px 9px; border-radius:980px; }}
      .pill-avail {{ background:{t['avail_border']}; color:{t['avail_text']}; }}
      .pill-mine  {{ background:{t['accent']}; color:{t['on_accent']}; }}
      .pill-lock  {{ background:{t['claim_border']}; color:#04301f; }}
      .pill-mi    {{ background:{t['mock_border']}; color:{t['mi_pill_text']}; }}
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
      .tchip-teach {{ background:{t['teach_border']}; color:#3a2400; }}
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
      .chip-prog {{ background:{t['accent_soft']}; color:{t['accent_text']}; font-weight:600; }}
      .badge {{
        display:inline-block; font-size:.67rem; font-weight:600;
        padding:1px 8px; border-radius:6px; margin-left:7px;
      }}
      .badge-available {{ background:{t['avail_border']}; color:{t['avail_text']}; }}
      .badge-selected, .badge-confirmed {{ background:{t['claim_border']}; color:#04301f; }}
      .badge-choosing {{ background:{t['accent']}; color:{t['on_accent']}; }}
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
      .st-cho  {{ background:{t['accent']}; color:{t['on_accent']}; }}
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
    
      /* ---------- ANUDIP.ORG BRAND CHROME ---------- */
      /* The site's buttons are fully-rounded pills, not soft rectangles. */
      .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {{
        border-radius:999px !important;
        font-family:"Poppins","Open Sans",sans-serif !important;
        font-weight:600 !important; letter-spacing:.01em;
        padding:.5rem 1.4rem !important;
        transition:background .18s ease, transform .18s ease, box-shadow .18s ease;
      }}
      .stButton > button:hover, .stFormSubmitButton > button:hover,
      .stDownloadButton > button:hover {{
        background:{t['accent_hover']} !important;
        box-shadow:0 6px 18px {t['accent']}45 !important;
        transform:translateY(-1px);
      }}
      /* the sidebar sign-out stays quiet — undo the pill fill there */
      [data-testid="stSidebar"] .stButton > button:hover {{
        background:transparent !important; box-shadow:none !important; transform:none;
      }}

      /* Navy masthead with the orange keyline, echoing the site header/footer. */
      .brandbar {{
        display:flex; align-items:center; gap:14px;
        background:{t['brandbar_bg']};
        border-bottom:3px solid {t['accent']};
        border-radius:14px 14px 0 0;
        padding:16px 22px; margin:0 0 22px;
      }}
      .brandbar .bb-mark {{
        flex:0 0 auto; display:flex; align-items:center;
      }}
      .brandbar .bb-mark img {{
        height:46px; width:auto; display:block; border-radius:10px;
        box-shadow:0 1px 4px rgba(0,0,0,.25);
      }}
      .brandbar .bb-name {{
        font-family:"Poppins",sans-serif; font-weight:600; font-size:1.02rem;
        color:#fff !important; line-height:1.2;
      }}
      .brandbar .bb-tag {{
        font-size:.76rem; color:{t['brandbar_tag']} !important;
        letter-spacing:.06em; text-transform:uppercase; margin-top:2px;
      }}
      .brandbar .bb-right {{
        margin-left:auto; font-size:.74rem; letter-spacing:.08em;
        text-transform:uppercase; color:{t['accent_lite']} !important; font-weight:600;
      }}

      /* Section headings get the short orange underline the site uses. */
      h1::after {{
        content:""; display:block; width:56px; height:3px; border-radius:2px;
        background:{t['accent']}; margin-top:10px;
      }}
      /* Tab underline in brand orange rather than Streamlit red. */
      .stTabs [aria-selected="true"] {{ box-shadow:inset 0 -2px 0 {t['accent']} !important; }}
      a, a:visited {{ color:{t['link']} !important; }}
      a:hover {{ color:{t['accent']} !important; }}

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
            '<div class="brandbar" style="border-radius:14px">'
            + _brand_mark_html() +
            '<div><div class="bb-name">Anudip Foundation</div>'
            '<div class="bb-tag">Life. Transformed.</div></div></div>'
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
        row = match.iloc[0]
        auth = db.get_user_auth(email)
        has_personal_pw = bool(auth and auth.get("password_hash") and auth.get("password_salt"))
        if has_personal_pw:
            pw_ok = db.verify_password(pwd, auth["password_salt"], auth["password_hash"])
        else:
            pw_ok = pwd == st.secrets["auth"]["shared_password"]
        if not pw_ok:
            st.error("Incorrect password.")
            return
        st.session_state.user = {"email": row["email"], "name": row["name"], "role": row["role"]}
        st.session_state["_using_shared_password"] = not has_personal_pw
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
        c_refresh, c_signout = st.columns(2)
        with c_refresh:
            with st.container(key="refresh_btn"):
                if st.button("🔄 Refresh", use_container_width=True,
                             help="Re-pull the latest data from CMIS and the app DB. "
                                  "Does not sign you out."):
                    db.clear_all_caches()
                    st.rerun()
        with c_signout:
            if st.button("Sign out", use_container_width=True):
                del st.session_state.user
                st.rerun()

        using_shared = st.session_state.get("_using_shared_password", True)
        pw_label = "🔑 Set your own password" if using_shared else "🔑 Change password"
        with st.expander(pw_label):
            if using_shared:
                st.caption(
                    "You're currently signed in with the shared password. "
                    "Set your own here for better security -- once you do, "
                    "the shared password will no longer work for your account."
                )
            with st.form("change_pwd", clear_on_submit=True):
                cur_pw = st.text_input("Current password", type="password", key="cp_cur")
                new_pw1 = st.text_input("New password", type="password", key="cp_new1")
                st.caption("At least 8 characters, with at least one letter and one number.")
                new_pw2 = st.text_input("Confirm new password", type="password", key="cp_new2")
                submitted = st.form_submit_button("Update password", use_container_width=True)
            if submitted:
                auth = db.get_user_auth(user["email"])
                has_personal_pw = bool(auth and auth.get("password_hash") and auth.get("password_salt"))
                cur_ok = (
                    db.verify_password(cur_pw, auth["password_salt"], auth["password_hash"])
                    if has_personal_pw
                    else cur_pw == st.secrets["auth"]["shared_password"]
                )
                pw_valid = (
                    len(new_pw1) >= 8
                    and re.search(r"[A-Za-z]", new_pw1)
                    and re.search(r"[0-9]", new_pw1)
                )
                if not cur_ok:
                    st.error("Current password is incorrect.")
                elif not pw_valid:
                    st.error("New password must be at least 8 characters, with at least "
                              "one letter and one number.")
                elif new_pw1 != new_pw2:
                    st.error("New passwords don't match.")
                else:
                    db.set_user_password(user["email"], new_pw1)
                    st.session_state["_using_shared_password"] = False
                    st.success("Password updated -- use your new password next time you sign in.")

        st.divider()
        _theme_toggle("theme_app")
        st.divider()
        cmis_ok, app_ok = db.ping()
        st.markdown(
            f'<div class="dbdot">CMIS {"🟢" if cmis_ok else "🔴"} &nbsp;·&nbsp; App DB {"🟢" if app_ok else "🔴"}</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        "<div class='brandbar'>"
        + _brand_mark_html() +
        "<div><div class='bb-name'>Anudip Foundation for Social Welfare</div>"
        "<div class='bb-tag'>Life. Transformed.</div></div>"
        "<div class='bb-right'>Academic Excellence</div>"
        "</div>"
        "<h1 style='margin-bottom:2px'>Extended AE Utilization Tracker</h1>"
        "<p style='opacity:.6;margin-top:10px;font-size:.92rem'>"
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
                and bool(r.get("_locked_mi")) == bool(prev["_rep"].get("_locked_mi"))
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

    # Own-slot (date, slot_time) pairs, captured BEFORE any synthetic rows are
    # folded in -- used below to make sure a cross-pod claim never gets
    # rendered twice on the rare occasion it coincides with one of the
    # member's own CMIS slots (which already surfaces it correctly via the
    # normal ae_slot_task override path inside resolve_member_calendar).
    own_keys = set()
    if not cal.empty:
        own_keys = set(zip(cal["_date"], cal["slot_time"]))

    _SYNTH_COLS = ["_date", "slot_time", "task_type", "default_task",
                   "is_default", "other_note", "ref_selection_id", "set_by",
                   "batch_code", "c_alias", "slot_name", "program_name",
                   "_locked_mi"]

    # Confirmed (Selected) cross-pod Mock Interview assignments live in their
    # own table -- they belong to a DIFFERENT trainer's slot, not this
    # member's own CMIS schedule, so they never show up via the own-slots
    # query above. Fold them in here as extra, locked calendar rows so a
    # member's Calendar reflects everything they've actually committed to.
    my_mi = db.get_my_mock_interview_claims(member_email, ws, we)
    if not my_mi.empty:
        confirmed_mi = my_mi[my_mi["status"] == "Selected"].copy()
        if not confirmed_mi.empty:
            confirmed_mi = confirmed_mi[
                ~confirmed_mi.apply(lambda r: (r["_date"], r["slot_time"]) in own_keys, axis=1)
            ]
        if not confirmed_mi.empty:
            confirmed_mi["task_type"] = "mock_interview"
            confirmed_mi["default_task"] = "mock_interview"
            confirmed_mi["is_default"] = True
            confirmed_mi["other_note"] = None
            confirmed_mi["ref_selection_id"] = None
            confirmed_mi["set_by"] = None
            confirmed_mi["slot_name"] = None
            confirmed_mi["_locked_mi"] = True
            cal = pd.concat([cal, confirmed_mi[_SYNTH_COLS]], ignore_index=True, sort=False)

    # Confirmed (Selected/Confirmed) Evaluation claims have the exact same
    # gap: claiming to OBSERVE another trainer's class writes an override
    # into ae_slot_task keyed to the observer, but that override only ever
    # gets picked up by the per-day render loop below if its (date,
    # slot_time) already exists among the observer's own CMIS rows -- which
    # it essentially never does, since you're watching someone ELSE teach.
    # The override was always being written correctly (Sessions tab claiming
    # worked); it just never had a calendar row to attach to. Same fix as
    # Mock Interview: fold the claim itself in as a synthetic row.
    my_claims = db.get_selections_for_role(member_role, member_email, ws, we)
    if not my_claims.empty:
        claimed = my_claims[my_claims["status"].isin(CLAIMED)].copy()
        if not claimed.empty:
            claimed["_date"] = pd.to_datetime(claimed["session_date"]).dt.date
            claimed = claimed[
                ~claimed.apply(lambda r: (r["_date"], r["slot_time"]) in own_keys, axis=1)
            ]
        if not claimed.empty:
            claimed["task_type"] = "evaluation"
            claimed["default_task"] = "evaluation"
            claimed["is_default"] = True
            claimed["other_note"] = None
            claimed["ref_selection_id"] = claimed["id"]
            claimed["set_by"] = None
            claimed["slot_name"] = None
            claimed["c_alias"] = claimed["module"]
            claimed["program_name"] = None
            claimed["_locked_mi"] = False
            cal = pd.concat([cal, claimed[_SYNTH_COLS]], ignore_index=True, sort=False)

    if cal.empty:
        st.info("No CMIS slots found for this member in this week — nothing to default onto.")
        return
    if "_locked_mi" not in cal.columns:
        cal["_locked_mi"] = False
    cal["_locked_mi"] = cal["_locked_mi"].fillna(False)

    counts = cal["task_type"].value_counts().to_dict()
    chip_row = " ".join(
        f"<span class='tchip tchip-{_task_css(tt)}'>{_cal_label(tt)} · {counts.get(tt, 0)}</span>"
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
                            <span class="tchip tchip-{css}">{_cal_label(task)}</span></div>
                          <div class="tcard-sub">{sub_line}</div>
                        </div>""",
                        unsafe_allow_html=True,
                    )
                with cB:
                    key = f"{r['_date']}|{card['_members'][0]['slot_time']}"
                    is_locked_mi = bool(r.get("_locked_mi"))
                    if task == "evaluation":
                        st.markdown(
                            "<div class='locked-status'>🔒 via Evaluation<br>"
                            "<span style='font-weight:400;opacity:.75'>change on Sessions tab</span></div>",
                            unsafe_allow_html=True,
                        )
                    elif task == "teaching" or (r.get("default_task") == "teaching" and not is_locked_mi):
                        # Mandatory: a scheduled class is always taken by the
                        # faculty of record -- no dropdown, nothing to choose.
                        st.markdown(
                            "<div class='locked-status'>🔒 Training<br>"
                            "<span style='font-weight:400;opacity:.75'>mandatory</span></div>",
                            unsafe_allow_html=True,
                        )
                    elif is_locked_mi:
                        # Confirmed on the Mock Interview section -- also
                        # mandatory, and not this member's own CMIS slot to
                        # override in the first place.
                        st.markdown(
                            "<div class='locked-status'>🔒 Confirmed MI<br>"
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
                        st.markdown(f"<div class='locked-status'>{_cal_label(task)}</div>",
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


def _cal_label(task_type: str) -> str:
    """Calendar-only display label. 'teaching' shows as 'Training' here per
    the AE-facing naming for this tab; every other type keeps its normal
    db.TASK_LABELS text (including the separate 'training' override type,
    which is a different underlying task and keeps its own 📚 icon)."""
    if task_type == "teaching":
        return "🏫 Training"
    return db.TASK_LABELS.get(task_type, task_type)


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

    # Mock Interviews live BELOW the session selection now, for both roles.
    _render_mock_interviews(user, role, core_ae_email, date_from, date_to)


def _render_mock_interviews(user, role, core_ae_email, date_from, date_to):
    """Mock Interview section, shown under the session list.

    Extended AE  -> editable list of their auto-assigned MIs, one of three
                    states each:
                      Pending      (default) awaiting a decision -- sits in
                                   the MI pool, not yet on the calendar.
                      Selected     confirmed -- appears on the Calendar tab.
                      Not Selected declined -- released back to the MI pool
                                   for reassignment.
                    Changing a dropdown reruns immediately so the card
                    recolours to match before Save.
    Core AE/admin -> read-only view of what their Extended AE team has picked.
    """
    mi_opts = ["Pending", "Selected", "Not Selected"]
    mi_labels = {"Pending": "Default", "Selected": "Selected", "Not Selected": "Not Selected"}
    mi_card_cls = {"Pending": "scard-avail", "Selected": "scard-mine", "Not Selected": "scard-declined"}

    if role == "extended_ae":
        my_mi = db.get_my_mock_interview_claims(user["email"], date_from, date_to)
        if not my_mi.empty:
            st.markdown("#### 🎯 My Mock Interviews")
            st.caption(
                "Auto-assigned Mock Interview sessions for you to observe/evaluate — "
                "these can be from any trainer, not just your own Core AE's pod. "
                "Each starts as **Default** (pending) — pick **Selected** to put it "
                "on your Calendar, or **Not Selected** to send it back to the MI pool "
                "for someone else, then Save."
            )
            my_mi = my_mi.sort_values(["_date", "slot_time"]).reset_index(drop=True)
            row_meta: dict[str, tuple] = {}   # widget key -> (row, saved status)
            for _, r in my_mi.iterrows():
                trainer = f"{r.get('f_name') or ''} {r.get('l_name') or ''}".strip() or "Unknown trainer"
                day_lbl = pd.to_datetime(r["_date"]).strftime("%a, %d %b")
                wkey = f"mi_{r['id']}"
                cur = r["status"] if r["status"] in mi_opts else "Pending"
                # Live value: whatever the dropdown holds this run (falls back to
                # the saved status on first render). Drives the card colour.
                live = st.session_state.get(wkey, cur)
                card_cls = mi_card_cls.get(live, "scard-avail")
                meta_bits = [trainer, r.get("batch_code") or "", r.get("c_alias") or "",
                             r.get("program_name") or ""]
                meta = " · ".join(b for b in meta_bits if b)
                cA, cB = st.columns([4, 1.3])
                with cA:
                    st.markdown(
                        f"<div class='scard {card_cls}'>"
                        f"<div class='scard-top'>🕑 {day_lbl} · {r['slot_time']}"
                        f"<span class='scard-meta'>· {meta}</span></div></div>",
                        unsafe_allow_html=True,
                    )
                with cB:
                    # No st.form here — a plain selectbox reruns on change, so the
                    # card can recolour instantly. Save is a normal button below.
                    st.selectbox(
                        "status", mi_opts, index=mi_opts.index(cur),
                        format_func=lambda o: mi_labels.get(o, o),
                        key=wkey, label_visibility="collapsed",
                    )
                row_meta[wkey] = (r, cur)

            if st.button("💾  Save my Mock Interview choices", type="primary", key="save_my_mi"):
                changed = 0
                for wkey, (row, cur) in row_meta.items():
                    new_status = st.session_state.get(wkey, cur)
                    if new_status == cur:
                        continue
                    db.upsert_mock_interview_assignment(
                        user["email"], row["session_date"], row["slot_time"],
                        row["batch_code"], row["c_alias"], row.get("trainer_email"),
                        row.get("trainer_name"), row.get("program_name"),
                        status=new_status, source="manual",
                    )
                    changed += 1
                if changed:
                    db.clear_app_caches()
                    st.success(f"Updated {changed} Mock Interview selection"
                               f"{'s' if changed != 1 else ''}.")
                    st.rerun()
                else:
                    st.info("No changes to save.")

    # A Core AE (and admin) can see the Mock Interviews their paired Extended
    # AEs have selected — e.g. what Pulak picks is visible to Arnab. Read-only.
    if role in ("core_ae", "admin"):
        ext_aes = {e.lower() for e in db.extended_aes_for_core(core_ae_email)}
        # One DB call for everyone in the range, then filter to this team —
        # cheaper than one query per Extended AE.
        all_mi = db.get_mock_interview_assignments(None, date_from, date_to)
        if not all_mi.empty and ext_aes:
            team_mi = all_mi[
                all_mi["extended_ae_email"].fillna("").str.lower().isin(ext_aes)
                & all_mi["status"].isin(list(CLAIMED))
            ]
        else:
            team_mi = all_mi.iloc[0:0]

        if not team_mi.empty:
            st.markdown("#### 🎯 Team Mock Interviews")
            st.caption(
                "Mock Interview sessions your Extended AE team has selected in "
                "this date range (read-only)."
            )
            team_mi = team_mi.sort_values(["extended_ae_email", "session_date", "slot_time"])
            for _, r in team_mi.iterrows():
                ae_name = str(r["extended_ae_email"] or "").split("@")[0]
                trainer = (r.get("trainer_name") or "Unknown trainer")
                day_lbl = pd.to_datetime(r["session_date"]).strftime("%a, %d %b")
                st.markdown(
                    f"<div class='scard scard-mock'>"
                    f"<div class='scard-top'>🕑 {day_lbl} · {r['slot_time']} "
                    f"· <b>{ae_name}</b></div>"
                    f"<div class='scard-sub'>{trainer} · {r.get('batch_code') or ''} · "
                    f"{r.get('c_alias') or ''} · {r.get('program_name') or ''}</div></div>",
                    unsafe_allow_html=True,
                )


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

    if status_by_key:
        # Fast path: a plain loop building three lists. The old
        # df.apply(_row_state, axis=1) allocated a pandas Series PER ROW over
        # the whole filtered set on every rerun, which was the main source of
        # lag on wide date ranges. Same "a claimed member wins" logic.
        _dates = df["_date"].tolist()
        _batches = df["batch_code"].tolist()
        _slots = df["slot_time"].tolist()
        _members_col = df["_members"].tolist() if "_members" in df.columns else [None] * len(df)
        statuses, owners, oroles = [], [], []
        for i in range(len(df)):
            b = _batches[i] or ""
            m = _members_col[i]
            mems = ([str(x) for x in m]
                    if isinstance(m, (list, tuple)) and len(m) > 0
                    else [str(_slots[i])])
            chosen = None
            for mm in mems:
                k = f"{_dates[i]}|{mm}|{b}"
                stt = status_by_key.get(k, "Not Selected")
                if stt in CLAIMED or stt == "Choosing":
                    chosen = (stt, owner_by_key.get(k), ownrole_by_key.get(k))
                    break
            if chosen is None:
                k0 = f"{_dates[i]}|{mems[0]}|{b}"
                chosen = (status_by_key.get(k0, "Not Selected"),
                          owner_by_key.get(k0), ownrole_by_key.get(k0))
            statuses.append(chosen[0]); owners.append(chosen[1]); oroles.append(chosen[2])
        df["Status"] = statuses
        df["_owner"] = owners
        df["_ownrole"] = oroles
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
    # Mock Interviews are a different kind of work from a routine class
    # observation, so they get their own clearly-headed section instead of
    # being interleaved. Sorting on _is_mi FIRST keeps each section
    # contiguous, so a section never splits across a page boundary.
    _mi_aliases = {a.lower() for a in db.MOCK_INTERVIEW_ALIASES}
    df["_is_mi"] = df["c_alias"].fillna("").str.lower().isin(_mi_aliases)
    df["_first_ts"] = df.groupby(["_is_mi", "Trainer"])["_ts"].transform("min")
    df = df.sort_values(
        ["_is_mi", "_first_ts", "Trainer", "_ts", "batch_code"], kind="stable"
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
          <div class="stat stat-mi"><div class="stat-num">{int(df['_is_mi'].sum()):,}</div><div class="stat-lbl">🎯 Mock Interviews</div></div>
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
    # ---- renderer --------------------------------------------------------
    # Cards are the only view. (The old "Table (fast)" data_editor toggle was
    # removed on request.)
    pending: dict = {}  # key -> (new status, row) — collected then saved together

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
        shown_section = None
        for (is_mi, trainer), grp in chunk.groupby(["_is_mi", "Trainer"], sort=False):
            if is_mi != shown_section:
                st.markdown(
                    "<div class='sec-head sec-mi'>🎯 Mock Interviews"
                    "<span class='sec-note'>Placement modules — the whole "
                    "interview goes to one observer. Full ladder on the "
                    "<b>MI Pool</b> tab.</span></div>"
                    if is_mi else
                    "<div class='sec-head sec-obs'>📋 Class observations"
                    "<span class='sec-note'>Routine teaching sessions."
                    "</span></div>",
                    unsafe_allow_html=True,
                )
                shown_section = is_mi
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
                mi_tag = "<span class='pill pill-mi'>🎯 MI</span>" if r["_is_mi"] else ""
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
                        f"""<div class="scard {'scard-mine' if (owner and owner.lower()==user_email.lower()) else ('scard-lock' if claimed_row else 'scard-avail')}{' scard-mi' if r['_is_mi'] else ''}">
                          <div class="scard-top">🕑 {day_lbl} &nbsp;·&nbsp; {_txt(r.get('slot_time'))} {mi_tag} {who}</div>
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
