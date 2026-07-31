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
        # MI Pool spreadsheet-style table (mirrors the Google Sheet's look)
        "sheet_head_bg": "#4a86c8", "sheet_head_text": "#ffffff",
        "sheet_border": "#c3cbd4", "sheet_zebra": "#f7f9fb",
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
        # MI Pool spreadsheet-style table (mirrors the Google Sheet's look)
        "sheet_head_bg": "#2b4c70", "sheet_head_text": "#e9eef4",
        "sheet_border": "#31404f", "sheet_zebra": "#18232f",
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
         is nearly invisible against the page background in either theme.
         Target the button AND every svg/path inside it (newer Streamlit
         renders the arrow as an svg <path> that uses stroke, not fill), and
         cover both the old and new test-ids so the arrow always shows. */
      [data-testid="stSidebarCollapsedControl"] button,
      [data-testid="stSidebarCollapsedControl"] svg,
      [data-testid="stSidebarCollapsedControl"] svg *,
      [data-testid="stSidebarCollapseButton"] button,
      [data-testid="stSidebarCollapseButton"] svg,
      [data-testid="stSidebarCollapseButton"] svg *,
      [data-testid="collapsedControl"] svg,
      [data-testid="collapsedControl"] svg * {{
        color:{t['text']} !important; fill:{t['text']} !important;
        stroke:{t['text']} !important; opacity:1 !important;
      }}
      [data-testid="stSidebarCollapsedControl"] button,
      [data-testid="stSidebarCollapseButton"] button,
      [data-testid="collapsedControl"] button {{
        background:{t['surface']} !important;
        border:1px solid {t['border']} !important;
      }}
      [data-testid="stSidebarCollapsedControl"] button:hover,
      [data-testid="stSidebarCollapseButton"] button:hover,
      [data-testid="collapsedControl"] button:hover {{
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
    
      /* ---------- MI POOL: SPREADSHEET-STYLE TABLE ----------
         Deliberately mimics the "MI Details New" Google Sheet the team
         already works from: a bordered grid, a blue header strip, and
         colour-coded status cells. Uses the theme's own surface colours so
         it never renders as a black slab inside a light page. */
      .mi-sheet-wrap {{ overflow-x:auto; margin:10px 0 18px; }}
      table.mi-sheet {{
        border-collapse:collapse; width:100%; font-size:.78rem;
        background:{t['surface']}; color:{t['text']};
      }}
      table.mi-sheet th {{
        background:{t['sheet_head_bg']}; color:{t['sheet_head_text']} !important;
        font-weight:700; font-size:.74rem; letter-spacing:.01em;
        padding:7px 9px; border:1px solid {t['sheet_border']};
        text-align:left; white-space:nowrap; position:sticky; top:0;
      }}
      table.mi-sheet td {{
        padding:6px 9px; border:1px solid {t['sheet_border']};
        vertical-align:middle; white-space:nowrap;
      }}
      table.mi-sheet tr:nth-child(even) td {{ background:{t['sheet_zebra']}; }}
      table.mi-sheet td.mi-wrap {{ white-space:normal; min-width:210px; }}
      /* status cells -- same colour language as the sheet */
      .mi-cell {{
        display:inline-block; padding:2px 10px; border-radius:6px;
        font-weight:600; font-size:.74rem;
      }}
      .mi-accepted  {{ background:{t['claim_border']}; color:#04301f; }}
      .mi-claimed   {{ background:{t['accent']}; color:{t['on_accent']}; }}
      .mi-rejected  {{ background:{t['other_border']}; color:#fff; }}
      .mi-notsel    {{ background:{t['chip_bg']}; color:{t['muted']}; }}
      .mi-resched   {{ background:{t['teach_border']}; color:#3a2400; }}
      .mi-takenby   {{ background:{t['accent_soft']}; color:{t['accent_text']}; }}
      .mi-yes       {{ background:{t['claim_border']}; color:#04301f; }}
      .mi-no        {{ background:{t['other_border']}; color:#fff; }}
      .mi-open      {{ background:{t['chip_bg']}; color:{t['muted']}; }}

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

        with st.expander("🔑 Change password"):
            st.caption(
                "Change your password without signing in. Enter your email and "
                "current password, then your new one. New password: at least 8 "
                "characters, with at least one letter and one number."
            )
            with st.form("login_change_pwd", clear_on_submit=True):
                cp_email = st.text_input("Email", key="lcp_email",
                                         placeholder="you@anudip.org").strip().lower()
                cp_cur = st.text_input("Current password", type="password", key="lcp_cur")
                cp_new1 = st.text_input("New password", type="password", key="lcp_new1")
                cp_new2 = st.text_input("Confirm new password", type="password", key="lcp_new2")
                cp_ok = st.form_submit_button("Update password", use_container_width=True)
            if cp_ok:
                roles = db.get_user_roles()
                if roles[roles["email"].str.lower() == cp_email].empty:
                    st.error("Email not found.")
                else:
                    auth = db.get_user_auth(cp_email)
                    has_pw = bool(auth and auth.get("password_hash") and auth.get("password_salt"))
                    cur_ok = (
                        db.verify_password(cp_cur, auth["password_salt"], auth["password_hash"])
                        if has_pw else cp_cur == st.secrets["auth"]["shared_password"]
                    )
                    pw_valid = (len(cp_new1) >= 8 and re.search(r"[A-Za-z]", cp_new1)
                                and re.search(r"[0-9]", cp_new1))
                    if not cur_ok:
                        st.error("Current password is incorrect.")
                    elif not pw_valid:
                        st.error("New password must be at least 8 characters, "
                                 "with at least one letter and one number.")
                    elif cp_new1 != cp_new2:
                        st.error("New passwords don't match.")
                    else:
                        db.set_user_password(cp_email, cp_new1)
                        st.success("Password updated — sign in with your new password.")

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
            if st.button("🔄 Refresh", use_container_width=True, type="primary",
                         help="Re-pull the latest data from CMIS and the app DB. "
                              "Does not sign you out."):
                db.clear_all_caches()
                st.rerun()
        with c_signout:
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

    # Restructured: Calendar (wizard) and Mock Interview (nationwide pool,
    # manual-only now that auto-assign is removed) are shared entry points
    # for everyone. "My Mock Interviews" and the old MI Pool tab are folded
    # into the single Mock Interview tab below. The old free-range Calendar
    # tab is gone too — replaced by the single-day wizard.
    if role == "admin":
        made = st.tabs(["📅  Calendar", "📝  Evaluations", "🎯  Mock Interview",
                        "👥  My Extended AE Team"])
        with made[0]:
            _admin_utilization_tab(user, role)
        with made[1]:
            _sessions_tab(user, role)
        with made[2]:
            mi_pool.render_mi_pool_tab(user, role)
        with made[3]:
            _rollup_tab(user, role)
    elif role == "core_ae":
        made = st.tabs(["📅  Calendar", "📝  Evaluations", "🎯  Mock Interview",
                        "👥  My Extended AE Team", "📊  Weekly Summary"])
        with made[0]:
            _calendar_wizard_tab(user, role)
        with made[1]:
            _sessions_tab(user, role)
        with made[2]:
            mi_pool.render_mi_pool_tab(user, role)
        with made[3]:
            _rollup_tab(user, role)
        with made[4]:
            _summary_tab(user, role)
    else:  # extended_ae
        made = st.tabs(["📅  Calendar", "📝  Evaluations", "🎯  Mock Interview",
                        "🧭  My Alignment"])
        with made[0]:
            _calendar_wizard_tab(user, role)
        with made[1]:
            _sessions_tab(user, role)
        with made[2]:
            mi_pool.render_mi_pool_tab(user, role)
        with made[3]:
            _my_core_tab(user)


def _light_df_table(df, right_align=None):
    """Render any DataFrame as a LIGHT, readable HTML table (white cells, dark
    ink, navy header) — a drop-in replacement for st.dataframe, which follows
    the app theme and goes black in dark mode. Colours are inline per cell so
    they survive even if injected CSS is stripped. `right_align` is an optional
    set of column names to right-align (numbers)."""
    if df is None or len(df) == 0:
        st.info("Nothing to show.")
        return
    right_align = set(right_align or [])
    cols = list(df.columns)

    td = ("padding:10px 16px;border-bottom:1px solid #eef1f4;"
          "background:#ffffff;color:#16283c;")
    th = ("padding:12px 16px;background:#16283c;color:#ffffff;"
          "white-space:nowrap;font-weight:700;text-align:left;")

    head = "<tr>" + "".join(
        f"<th style='{th}{'text-align:right;' if c in right_align else ''}'>{c}</th>"
        for c in cols
    ) + "</tr>"

    body = []
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            val = "" if pd.isna(r[c]) else r[c]
            align = "text-align:right;" if c in right_align else ""
            cells.append(f"<td style='{td}{align}white-space:nowrap;'>{val}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")

    st.markdown(
        "<style>.lite-scroll{width:100%;overflow:auto;border:1px solid #e3e7ec;"
        "border-radius:12px;box-shadow:0 1px 3px rgba(22,40,60,.06);background:#fff;}"
        ".lite-scroll::-webkit-scrollbar{height:12px;width:12px;}"
        ".lite-scroll::-webkit-scrollbar-track{background:#eef2f5;border-radius:8px;}"
        ".lite-scroll::-webkit-scrollbar-thumb{background:#14b8a6;border-radius:8px;"
        "border:2px solid #eef2f5;}"
        ".lite-scroll{scrollbar-color:#14b8a6 #eef2f5;scrollbar-width:thin;}</style>"
        "<div class='lite-scroll'><table style='width:100%;border-collapse:collapse;"
        "font-size:.93rem;background:#ffffff;'>"
        f"<thead>{head}</thead><tbody>{''.join(body)}</tbody></table></div>",
        unsafe_allow_html=True,
    )


@st.fragment
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
                st.rerun(scope="fragment")
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
    _light_df_table(view, right_align={"Available", "Selected", "Observed"})


@st.fragment
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
    _light_df_table(view, right_align={"Score", "CMIS slots"})

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


@st.fragment
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


@st.fragment
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




def _status_options_for(saved_status: str, live_status: str) -> list[str]:
    """The dropdown choices available to a row, given its SAVED status (in
    the DB) and its LIVE status (currently shown). The 'back out' option is
    'Rejected' once the row has EVER been Selected -- otherwise it's
    'Not Selected'. Same progression the Evaluations tab uses:

    - fresh (never touched): Not Selected / Selected
    - has been Selected (Selected or Rejected): Selected / Rejected

    Once something is Selected, the person must explicitly Reject it rather
    than quietly sliding back to "Not Selected" -- so the audit trail shows
    whether an interview was never wanted or was taken and then dropped.
    """
    ever_selected = saved_status in ("Selected", "Rejected") or live_status in ("Selected", "Rejected")
    if ever_selected:
        return ["Selected", "Rejected"]
    return ["Not Selected", "Selected"]


def _render_mi_cards(df: pd.DataFrame, user_email: str, key_prefix: str) -> bool:
    """Mock Interview candidates as cards (scard / pill-mine / pill-lock /
    pill-avail / slot-head CSS classes) -- grouped by trainer, one card per
    merged session.

    ALL cards live inside ONE st.form with a single Save button at the
    bottom, so picking statuses for several interviews only takes one
    click to commit -- not one Save per card. Widgets inside a form don't
    trigger a rerun on change either, so switching a dropdown or editing a
    reason box causes no loading at all; the whole batch reruns exactly
    once, when Save is pressed.

    Returns whether anything was actually saved this run.
    """
    if df.empty:
        return False

    existing = db.get_mock_interview_assignments(None, df["_date"].min(), df["_date"].max())
    status_by_key: dict[str, dict] = {}
    if not existing.empty:
        for _, s in existing.iterrows():
            k = f"{s['session_date']}|{s['slot_time']}|{s['batch_code'] or ''}"
            status_by_key[k] = {
                "status": s["status"], "owner": s["extended_ae_email"],
                "remarks": s.get("remarks"),
            }

    def _txt(v) -> str:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        s = str(v).strip()
        return "" if s.lower() in ("nan", "none", "null") else s

    d = df.copy()
    d["Trainer"] = (d["f_name"].fillna("") + " " + d["l_name"].fillna("")).str.strip()
    d["Duration"] = d.apply(_fmt_duration, axis=1)

    # (row dict, row_key, original status, original remarks) for every
    # editable row -- collected while drawing the cards, then written out
    # in one pass after the single Save button is pressed.
    pending: list[tuple[dict, str, str, str]] = []

    with st.form(f"{key_prefix}_mi_form"):
        for trainer, grp in d.groupby("Trainer", sort=False):
            first = grp.iloc[0]
            st.markdown(
                f"<div class='slot-head'>\U0001F464 {trainer or _txt(first.get('email_id')) or 'Unknown trainer'}"
                f" &nbsp;\u00b7&nbsp; <span class='slot-count'>{len(grp)} session"
                f"{'s' if len(grp) != 1 else ''}</span></div>",
                unsafe_allow_html=True,
            )
            for _, r in grp.iterrows():
                b = r.get("batch_code") or ""
                # KEY BY THE WHOLE MERGED SPAN, not per 30-min fragment --
                # mock_interview_assignment stores one row per whole block
                # (matching merge_mi_blocks' mi_key, which the Mock Interview
                # pool table also keys on).
                k = f"{r['_date']}|{r['slot_time']}|{b}"
                existing_row = status_by_key.get(k, {})
                status = existing_row.get("status", "Not Selected")
                owner = existing_row.get("owner")
                saved_remarks = existing_row.get("remarks") or ""

                claimed_row = status in CLAIMED
                editable = (not owner) or (owner.lower() == user_email.lower())
                if owner and claimed_row:
                    who = ("<span class='pill pill-mine'>\u2605 Mine</span>"
                           if owner.lower() == user_email.lower()
                           else f"<span class='pill pill-lock'>\U0001F512 {owner.split('@')[0]}</span>")
                elif not claimed_row:
                    who = "<span class='pill pill-avail'>\u25f7 Available</span>"
                else:
                    who = ""

                day_lbl = pd.to_datetime(r["_date"]).strftime("%a, %d %b")
                sub_bits = [r["Duration"], f"<b>{_txt(r.get('batch_code'))}</b>"]
                for extra in (_txt(r.get("c_alias")), _txt(r.get("program_name"))):
                    if extra:
                        sub_bits.append(extra)
                sub_line = " \u00b7 ".join(bit for bit in sub_bits if bit and bit != "<b></b>")

                # Card background must agree with the pill above -- a row
                # saved as Not Selected/Rejected always gets an owner
                # (upsert writes it regardless of status), but that
                # shouldn't paint the card teal "mine" when the pill next
                # to it says "Available".
                if claimed_row and owner and owner.lower() == user_email.lower():
                    card_cls = "scard-mine"
                elif claimed_row and owner:
                    card_cls = "scard-lock"
                else:
                    card_cls = "scard-avail"

                cA, cB = st.columns([4, 1.3])
                with cA:
                    st.markdown(
                        f"""<div class="scard {card_cls} scard-mi">
                          <div class="scard-top">\U0001F551 {day_lbl} &nbsp;\u00b7&nbsp; {_txt(r.get('slot_time'))} {who}</div>
                          <div class="scard-sub">{sub_line}</div>
                        </div>""",
                        unsafe_allow_html=True,
                    )
                with cB:
                    if not editable:
                        st.markdown(f"<div class='locked-status'>{status}</div>", unsafe_allow_html=True)

                if not editable:
                    st.divider()
                    continue

                # Own independent status control + remarks -- a key
                # collision between two different rows is impossible since
                # k already encodes date|slot_time|batch_code.
                row_key = f"{key_prefix}_{k}"
                options = _status_options_for(status, status)
                default_idx = options.index(status) if status in options else 0

                c1, c2 = st.columns([1.3, 3.2])
                with c1:
                    st.selectbox(
                        "Status", options, index=default_idx,
                        key=f"{row_key}_sel", label_visibility="collapsed",
                    )
                with c2:
                    # Always shown (a form can't reactively hide this based
                    # on the dropdown above without a rerun) -- it's only
                    # actually saved when the final status is Not
                    # Selected/Rejected, same as before.
                    st.text_input(
                        "Remarks", value=saved_remarks,
                        key=f"{row_key}_remarks", label_visibility="collapsed",
                        placeholder="Reason for not taking this interview (optional)",
                    )
                pending.append((r.to_dict(), row_key, status, saved_remarks))
                st.divider()

        submitted = st.form_submit_button(
            "\U0001F4BE Save all changes", type="primary", use_container_width=True,
        )

    any_saved = False
    if submitted:
        if not pending:
            st.info("Nothing here for you to save.")
            return False
        n_changed = 0
        for row, row_key, orig_status, orig_remarks in pending:
            sel = st.session_state.get(f"{row_key}_sel", orig_status)
            remarks_val = st.session_state.get(f"{row_key}_remarks", "") or ""
            if sel == orig_status and remarks_val == (orig_remarks or ""):
                continue  # untouched -- skip the write entirely
            try:
                db.upsert_mock_interview_assignment(
                    extended_ae_email=user_email,
                    session_date=row["_date"],
                    slot_time=row["slot_time"],
                    batch_code=row.get("batch_code"),
                    c_alias=row.get("c_alias"),
                    trainer_email=row.get("email_id"),
                    trainer_name=(str(row.get("f_name") or "") + " " + str(row.get("l_name") or "")).strip(),
                    program_name=row.get("program_name"),
                    status=sel,
                    source="manual",
                    remarks=remarks_val if sel in ("Not Selected", "Rejected") else None,
                )
                n_changed += 1
            except Exception as exc:
                st.error(f"Could not save one of the interviews: {exc}")
        if n_changed:
            # Only the MI assignment/claim + pool caches change on this
            # write. Clearing just those (instead of the old
            # clear_app_caches() sledgehammer, which also dumped the member
            # calendar, CMIS session pull and evaluation caches) keeps the
            # rest of the day warm. One clear and one rerun for the WHOLE
            # batch, not one per card.
            db.clear_mock_interview_caches()
            st.success(f"Saved {n_changed} change{'s' if n_changed != 1 else ''}.")
            any_saved = True
            st.rerun(scope="fragment")
        else:
            st.info("No changes to save.")

    return any_saved


def _render_training_cards(df: pd.DataFrame, key_prefix: str) -> None:
    """Training sessions as the SAME card style as the Evaluation/Mock
    Interview cards (scard / slot-head CSS classes) -- view-only, no status
    control, since training is fixed and never claimable.
    """
    if df.empty:
        return

    def _txt(v) -> str:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        s = str(v).strip()
        return "" if s.lower() in ("nan", "none", "null") else s

    d = df.copy()
    d["Trainer"] = (d["f_name"].fillna("") + " " + d["l_name"].fillna("")).str.strip() \
        if "f_name" in d.columns else d.get("trainer_name", "")
    d["Duration"] = d.apply(_fmt_duration, axis=1)

    for trainer, grp in d.groupby("Trainer", sort=False) if "Trainer" in d.columns else []:
        first = grp.iloc[0]
        st.markdown(
            f"<div class='slot-head'>\U0001F464 {trainer or 'You'}"
            f" &nbsp;\u00b7&nbsp; <span class='slot-count'>{len(grp)} session"
            f"{'s' if len(grp) != 1 else ''}</span></div>",
            unsafe_allow_html=True,
        )
        for _, r in grp.iterrows():
            day_lbl = pd.to_datetime(r["_date"]).strftime("%a, %d %b")
            sub_bits = [r["Duration"], f"<b>{_txt(r.get('batch_code'))}</b>"]
            for extra in (_txt(r.get("c_alias")), _txt(r.get("slot_name")), _txt(r.get("program_name"))):
                if extra:
                    sub_bits.append(extra)
            sub_line = " \u00b7 ".join(b for b in sub_bits if b and b != "<b></b>")
            st.markdown(
                f"""<div class="scard scard-lock">
                  <div class="scard-top">\U0001F551 {day_lbl} &nbsp;\u00b7&nbsp; {_txt(r.get('slot_time'))}
                  <span class="pill pill-lock">\U0001F3EB Training</span></div>
                  <div class="scard-sub">{sub_line}</div>
                </div>""",
                unsafe_allow_html=True,
            )


# Working-day boundaries for the Calendar wizard's free-time calculation.
# HARD CAP, deliberately independent of whatever CMIS happens to have data
# for on a given day: a half-hour slot with nobody's session recorded in it
# is still free time within the working day, not "outside the day" -- and a
# stray CMIS row after hours (if one ever exists) should not stretch what
# counts as the visible working day either. Update these two if working
# hours change.
WORKING_DAY_START_MIN = 10 * 60   # 10:00 AM
WORKING_DAY_END_MIN = 18 * 60      # 06:00 PM


def _minutes_to_ampm(mins: int) -> str:
    h, m = divmod(mins, 60)
    period = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12:02d}:{m:02d} {period}"


def _canonical_working_day_slots(
    start_min: int = WORKING_DAY_START_MIN,
    end_min: int = WORKING_DAY_END_MIN,
    step: int = 30,
) -> list[str]:
    """Half-hour slot_time strings covering the fixed working day, in the
    exact 'HH:MM AM/PM - HH:MM AM/PM' format CMIS uses (e.g.
    '10:00 AM - 10:30 AM'), so they match real CMIS slot_time values
    directly for filtering/membership checks.
    """
    slots = []
    t = start_min
    while t < end_min:
        slots.append(f"{_minutes_to_ampm(t)} - {_minutes_to_ampm(t + step)}")
        t += step
    return slots


def _render_day_schedule_summary(
    training_display: pd.DataFrame,
    eval_claims_display: pd.DataFrame,
    mi_claims_display: pd.DataFrame,
) -> None:
    """Training + whatever Evaluation/Mock Interview is already saved for
    this day, merged into ONE chronological list -- so after saving a pick
    in either section below, the person can see their whole day's committed
    schedule lined up together at a glance, instead of having to piece it
    together from three separate sections.
    """
    rows = []

    def _txt(v) -> str:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        s = str(v).strip()
        return "" if s.lower() in ("nan", "none", "null") else s

    if not training_display.empty:
        for _, r in training_display.iterrows():
            detail = " \u00b7 ".join(x for x in (_txt(r.get("c_alias")), _txt(r.get("batch_code"))) if x)
            rows.append((r["slot_time"], "\U0001F3EB Training", "You", detail, "scard-lock"))

    if not eval_claims_display.empty:
        for _, r in eval_claims_display.iterrows():
            detail = " \u00b7 ".join(x for x in (_txt(r.get("module")), _txt(r.get("batch_code"))) if x)
            rows.append((r["slot_time"], "\U0001F4DD Evaluation", "You", detail, "scard-mine"))

    if not mi_claims_display.empty:
        for _, r in mi_claims_display.iterrows():
            trainer = _txt(r.get("trainer_name")) or _txt(r.get("trainer_email")) or "Unknown trainer"
            detail = " \u00b7 ".join(x for x in (_txt(r.get("c_alias")), _txt(r.get("batch_code"))) if x)
            rows.append((r["slot_time"], "\U0001F3AF Mock Interview", trainer, detail, "scard-mine"))

    if not rows:
        st.caption("Nothing booked yet for this day.")
        return

    rows.sort(key=lambda row: _slot_start_minutes(row[0]))
    for slot_time, kind, who, detail, css in rows:
        sub = who if not detail else f"{who} \u00b7 {detail}"
        st.markdown(
            f"""<div class="scard {css}">
              <div class="scard-top">\U0001F551 {slot_time} &nbsp;\u00b7&nbsp; {kind}</div>
              <div class="scard-sub">{sub}</div>
            </div>""",
            unsafe_allow_html=True,
        )


@st.fragment
def _calendar_wizard_tab(user, role):
    """Single-day view: a top "Your Schedule Today" summary (Training +
    whatever Evaluation/Mock Interview you've already saved, merged into one
    chronological list) followed by Training (fixed) -> Mock Interview ->
    Evaluation, each independently pickable.

    A slot counts as TRAINING only when its CMIS-derived default is
    'teaching' -- everything else is free time within the fixed working day
    (see _canonical_working_day_slots), available for evaluation/MI picking.

    Cross-exclusion: once a slot is saved as a Mock Interview, it drops out
    of the Evaluation candidate list for this day, and vice versa -- a
    single half-hour can't be booked as both at once. This is recomputed
    from the DB on every render, so it updates the moment either side saves.

    Contiguous 30-min CMIS rows (same trainer/date/batch, back-to-back) are
    merged into one row per real class -- same _merge_consecutive() the
    Evaluations tab uses.
    """
    st.markdown("### \U0001F4C5 Calendar")
    email = user["email"]

    # Evaluation candidates must be scoped to the trainers this person is
    # actually aligned with -- exactly the same core_ae_faculty_map lookup
    # the Evaluations tab uses. Mock Interview stays nationwide by design.
    core_options = _core_options_for(role, email)
    core_ae_email = core_options[0] if core_options else None
    if len(core_options) > 1:
        core_ae_email = st.selectbox("Core AE Member", core_options, key="cal_wizard_core_ae")
    aligned_faculty = set()
    if core_ae_email:
        aligned_faculty = {f.lower() for f in db.faculty_emails_for_core(core_ae_email)}
    if not aligned_faculty:
        st.warning("No Core AE mapping found for your account in core_ae_faculty_map.")
        return

    w_lo, w_hi = db.visible_window()
    picked_day = st.date_input(
        "Choose a day", value=w_lo, min_value=w_lo, max_value=w_hi,
        key="cal_wizard_day",
    )

    with st.spinner("Loading this day's schedule\u2026"):
        own_cal = db.resolve_member_calendar(email, picked_day, picked_day)
        all_day = db.fetch_sessions_all(picked_day, picked_day, limit=5000)
    if not all_day.empty:
        all_day = all_day.copy()
        all_day["_date"] = pd.to_datetime(all_day["s_date"]).dt.date

    # ---- Training: fixed, no choice offered --------------------------
    training = pd.DataFrame()
    if not own_cal.empty:
        training = own_cal[own_cal["default_task"] == "teaching"].copy()
    training_slot_times = set(training["slot_time"]) if not training.empty else set()
    training_display = pd.DataFrame()
    if not training.empty:
        # resolve_member_calendar's own_cal never selects email_id (it's
        # only used in the WHERE filter, not returned) -- but
        # _merge_consecutive requires it for grouping/sorting. Every row
        # here already belongs to this one person, so it's always safe to
        # fill it in with their own address.
        training = training.copy()
        training["email_id"] = email
        training_display = _merge_consecutive(training)

    # ---- Already-saved Evaluation / Mock Interview picks for this day,
    # merged the same way, so the top summary reads like real classes and
    # the cross-exclusion below works on whole merged blocks. ----------
    eval_claims_raw = db.get_selections_for_role(role, email, picked_day, picked_day)
    eval_claims_raw = eval_claims_raw[eval_claims_raw["status"].isin(CLAIMED)].copy() \
        if not eval_claims_raw.empty else eval_claims_raw
    eval_claimed_slots = set()
    eval_claims_display = pd.DataFrame()
    if not eval_claims_raw.empty:
        eval_claims_raw["email_id"] = email
        eval_claims_raw["_date"] = pd.to_datetime(eval_claims_raw["session_date"]).dt.date
        eval_claimed_slots = set(eval_claims_raw["slot_time"])
        eval_claims_display = _merge_consecutive(eval_claims_raw)

    mi_claims_raw = db.get_mock_interview_assignments(email, picked_day, picked_day)
    mi_claims_raw = mi_claims_raw[mi_claims_raw["status"].isin(CLAIMED)].copy() \
        if not mi_claims_raw.empty else mi_claims_raw
    mi_claimed_slots = set()
    mi_claims_display = pd.DataFrame()
    if not mi_claims_raw.empty:
        mi_claims_raw["email_id"] = email
        mi_claims_raw["_date"] = pd.to_datetime(mi_claims_raw["session_date"]).dt.date
        mi_claimed_slots = set(mi_claims_raw["slot_time"])
        mi_claims_display = _merge_consecutive(mi_claims_raw)

    # ---- Top summary: Training + saved Evaluation + saved Mock Interview,
    # merged into one chronological "Your Schedule Today" list -----------
    st.markdown("#### \U0001F5D3\uFE0F Your Schedule Today")
    _render_day_schedule_summary(training_display, eval_claims_display, mi_claims_display)
    st.divider()

    # ---- Training (fixed) section, card view, no choice offered --------
    st.markdown("#### \U0001F3EB Training (fixed)")
    if training_display.empty:
        st.caption("No teaching slots on this day.")
    else:
        _render_training_cards(training_display, key_prefix="cal_wizard_train")

    # ---- The day's slot grid is the FIXED working day (10 AM-6 PM), not
    # whatever CMIS happens to have data for -- a slot nobody's scheduled in
    # is still free time, and the working day shouldn't silently stretch if
    # a stray CMIS row exists after hours.
    day_grid = set(_canonical_working_day_slots())
    free_slots = day_grid - training_slot_times

    if not free_slots:
        st.info("No free time on this day \u2014 fully booked with training.")
        return

    st.divider()

    # ---- Mock Interview -- FIRST, nationwide, in free time NOT already
    # taken by a saved Evaluation pick today -----------------------------
    st.markdown("#### \U0001F3AF Mock Interview")
    mi_free_slots = free_slots - eval_claimed_slots
    mi_candidates = db.get_all_mock_interview_sessions(picked_day, picked_day)
    if not mi_candidates.empty:
        mi_candidates = mi_candidates[mi_candidates["slot_time"].isin(mi_free_slots)].copy()
        mi_candidates["_date"] = pd.to_datetime(mi_candidates["s_date"]).dt.date

    if mi_candidates.empty:
        st.caption("No Mock Interview sessions in the remaining free time on this day.")
    else:
        mi_display = _merge_consecutive(mi_candidates)
        # Saving now happens per-card, independently, inside
        # _render_mi_cards itself (including its own st.rerun()) -- no
        # pending/session_state hand-off needed here anymore.
        _render_mi_cards(mi_display, email, key_prefix="cal_wizard_mi")

    st.divider()

    # ---- Evaluation -- reuses the SAME card component (and its built-in
    # Available/Mine/Teammate's status handling + Save) as the Evaluations
    # tab -- scoped to this day's free time NOT already taken by a saved
    # Mock Interview pick today. ------------------------------------------
    st.markdown("#### \U0001F4DD Evaluation")
    eval_free_slots = free_slots - mi_claimed_slots
    eval_candidates = pd.DataFrame()
    if not all_day.empty:
        eval_candidates = all_day[
            all_day["slot_time"].isin(eval_free_slots)
            & (all_day["email_id"].fillna("").str.lower() != email.lower())
            & (all_day["email_id"].fillna("").str.lower().isin(aligned_faculty))
        ].copy()

    if eval_candidates.empty:
        st.caption("No sessions from your aligned faculty are available to evaluate in the remaining free time on this day.")
    else:
        eval_display = _merge_consecutive(eval_candidates)
        _sessions_table(eval_display, core_ae_email, picked_day, picked_day, role, email, key_prefix="cal_wizard_eval_")


def _week_day_strip(date_from, date_to, key: str):
    """Horizontal 'next 7 days' filter strip: an 'All days' pill plus one
    pill per day in [date_from, date_to]. Returns the selected date, or
    None for 'All days'.

    Purely a display filter on top of whatever 7-day window the tab
    already fetches -- it doesn't change the date range itself, and it
    doesn't touch the Calendar tab's own day picker at all.
    """
    days = [date_from + timedelta(days=i) for i in range((date_to - date_from).days + 1)]
    state_key = f"_daystrip_{key}"
    if state_key not in st.session_state:
        st.session_state[state_key] = None

    cols = st.columns(len(days) + 1)
    with cols[0]:
        if st.button(
            "All", key=f"{state_key}_all", use_container_width=True,
            type="primary" if st.session_state[state_key] is None else "secondary",
        ):
            st.session_state[state_key] = None
    for i, d in enumerate(days):
        with cols[i + 1]:
            is_sel = st.session_state[state_key] == d
            if st.button(
                d.strftime("%a %d"), key=f"{state_key}_{i}", use_container_width=True,
                type="primary" if is_sel else "secondary",
            ):
                st.session_state[state_key] = d

    return st.session_state[state_key]


# ===========================================================================
# ADMIN EVALUATIONS TAB  —  now a READ-ONLY utilization dashboard.
#
# The admin login no longer selects or assigns individual sessions here (that
# lived in _admin_evaluations_sheet, still used by non-admin roles via
# _sessions_table). Instead the admin sees a count-only information table plus
# a unique visualization of how many Evaluations, Training sessions and Mock
# Interviews each Core AE and Extended AE is carrying — viewable both DAILY
# and WEEKLY. Nothing on this tab writes to any database.
# ===========================================================================

# Fixed metric order + brand-aligned colours reused by the table and the chart.
_UTIL_METRICS = ["Evaluation", "Training", "Mock Interview"]
_UTIL_COLORS = {
    "Evaluation":     BRAND["teal"],    # primary teal
    "Training":       BRAND["sky"],     # secondary blue
    "Mock Interview": BRAND["orange"],  # secondary orange
}


def _slot_rows(df, date_col, email, metric, role_label, name):
    """Normalise one source frame into per-slot detail rows.

    We count EACH 30-minute CMIS slot as one session (so Aarti's twelve
    half-hour rows on a day read as 12, matching CMIS row-for-row). Every row
    keeps its date, slot time, batch code and trainer so the details table can
    show exactly which sessions make up the count."""
    cols = ["name", "email", "role", "metric", "_d", "slot_time",
            "batch_code", "trainer", "module"]
    if df is None or df.empty:
        return pd.DataFrame(columns=cols)
    d = df.copy()
    d["_d"] = pd.to_datetime(d[date_col]).dt.date

    def pick(*names, default=""):
        for n in names:
            if n in d.columns:
                return d[n].fillna("").astype(str)
        return pd.Series([default] * len(d), index=d.index)

    out = pd.DataFrame({
        "name": name,
        "email": email,
        "role": role_label,
        "metric": metric,
        "_d": d["_d"].values,
        "slot_time": pick("slot_time").values,
        "batch_code": pick("batch_code").values,
        "trainer": pick("trainer_name", "trainer", "module").values,
        "module": pick("module", "c_alias", "program_name").values,
    })
    return out


def _member_metric_frames(email, role, d_from, d_to, name="", role_label=""):
    """Return per-slot detail rows for one member across the three metrics.
    Each 30-minute CMIS slot is one row (one session)."""
    # --- Evaluations: claimed rows in this member's own selection table ---
    sel = db.get_selections_for_role(role, email, d_from, d_to)
    if sel is not None and not sel.empty:
        sel = sel[sel["status"].isin(CLAIMED)]
    ev = _slot_rows(sel, "session_date", email, "Evaluation", role_label, name)

    # --- Mock Interviews: only Extended AEs hold MI assignments ------------
    mi = pd.DataFrame()
    if role == "extended_ae":
        mi_raw = db.get_mock_interview_assignments(email, d_from, d_to)
        if mi_raw is not None and not mi_raw.empty:
            mi_raw = mi_raw[mi_raw["status"].isin(CLAIMED)]
            mi = _slot_rows(mi_raw, "session_date", email, "Mock Interview",
                            role_label, name)

    # --- Training: the member's OWN teaching slots from CMIS ---------------
    tr = pd.DataFrame()
    cal = db.resolve_member_calendar(email, d_from, d_to)
    if cal is not None and not cal.empty:
        teach = cal[cal["task_type"] == "teaching"]
        tr = _slot_rows(teach, "_date", email, "Training", role_label, name)

    return ev, mi, tr


def _build_utilization_long(members, d_from, d_to, granularity):
    """members: list of (email, name, role_key, role_label).
    Returns (long_df, detail_df):
      long_df  -> name, email, role, period, metric, count  (per 30-min slot)
      detail_df-> every counted slot with date/slot_time/batch/trainer.
    period is a day (Daily) or the week's Monday (Weekly)."""
    def period_key(dt):
        if granularity == "Daily":
            return dt.isoformat()
        monday = dt - timedelta(days=dt.weekday())
        return monday.isoformat()

    detail_parts = []
    for email, name, role_key, role_label in members:
        ev, mi, tr = _member_metric_frames(
            email, role_key, d_from, d_to, name=name, role_label=role_label
        )
        for frame in (ev, mi, tr):
            if frame is not None and not frame.empty:
                detail_parts.append(frame)

    detail_cols = ["name", "email", "role", "metric", "_d", "slot_time",
                   "batch_code", "trainer", "module"]
    long_cols = ["name", "email", "role", "period", "metric", "count"]
    if not detail_parts:
        return (pd.DataFrame(columns=long_cols),
                pd.DataFrame(columns=detail_cols))

    detail = pd.concat(detail_parts, ignore_index=True)
    # keep only rows inside the window (defensive)
    detail = detail[(detail["_d"] >= d_from) & (detail["_d"] <= d_to)].copy()
    if detail.empty:
        return (pd.DataFrame(columns=long_cols),
                pd.DataFrame(columns=detail_cols))

    detail["period"] = detail["_d"].apply(period_key)
    long_df = (
        detail.groupby(["name", "email", "role", "period", "metric"])
        .size().reset_index(name="count")
    )
    return long_df, detail


@st.cache_data(ttl=120, show_spinner=False)
def _build_utilization_long_cached(members_key, d_from, d_to, granularity):
    """Cached front door to _build_utilization_long.

    The admin utilization tab used to re-run the whole per-member DB tally on
    every rerun -- and with 'All teams' that's 2-3 queries per member, so the
    tab felt like it stalled. `members_key` is a hashable tuple of
    (email, name, role_key, role_label) tuples so st.cache_data can memoise
    the assembled frames; a 2-minute TTL keeps it fresh without re-querying on
    every tab switch or widget nudge. Writes elsewhere clear this via the
    normal cache-clear path.
    """
    members = [tuple(m) for m in members_key]
    return _build_utilization_long(members, d_from, d_to, granularity)


def _utilization_chart(long_df, granularity):
    """Unique, light, full-width visualization:
      (1) a horizontal stacked bar per member — total activity split by type;
      (2) a per-period activity heatmap (one column per day/week).
    Uses Altair (bundled with Streamlit); falls back to st.bar_chart if
    Altair isn't importable in this environment."""
    if long_df.empty:
        st.info("Nothing to visualize for this window yet.")
        return

    plot = long_df.copy()
    if granularity == "Daily":
        plot["period_label"] = pd.to_datetime(plot["period"]).dt.strftime("%a %d %b")
    else:
        plot["period_label"] = "Wk of " + pd.to_datetime(plot["period"]).dt.strftime("%d %b")
    plot["_pk"] = plot["period"]
    plot["who"] = plot["name"] + "  ·  " + plot["role"]

    try:
        import altair as alt

        color_scale = alt.Scale(
            domain=_UTIL_METRICS,
            range=[_UTIL_COLORS[m] for m in _UTIL_METRICS],
        )

        # ---- (1) Stacked horizontal bars: total per member by activity ----
        totals_by_member = (
            plot.groupby(["who", "name", "role", "metric"])["count"].sum()
            .reset_index()
        )
        member_order = (
            totals_by_member.groupby("who")["count"].sum()
            .sort_values(ascending=False).index.tolist()
        )
        bars = (
            alt.Chart(totals_by_member)
            .mark_bar(cornerRadiusEnd=4, height={"band": 0.7})
            .encode(
                y=alt.Y("who:N", title=None, sort=member_order,
                        axis=alt.Axis(labelLimit=260, labelFontSize=12)),
                x=alt.X("count:Q", title="Sessions",
                        axis=alt.Axis(grid=True, gridColor="#eef1f4")),
                color=alt.Color("metric:N", title="Activity", scale=color_scale,
                                legend=alt.Legend(orient="top", direction="horizontal")),
                order=alt.Order("metric:N", sort="ascending"),
                tooltip=[
                    alt.Tooltip("name:N", title="Member"),
                    alt.Tooltip("role:N", title="Role"),
                    alt.Tooltip("metric:N", title="Activity"),
                    alt.Tooltip("count:Q", title="Sessions"),
                ],
            )
            .properties(height=max(220, 30 * len(member_order)),
                        background="transparent")
            .configure_view(strokeWidth=0)
            .configure_axis(labelColor="#16283c", titleColor="#5d7085")
        )
        st.altair_chart(bars, use_container_width=True)

        # ---- (2) Per-period heatmap (only the active metrics) -------------
        label = "day" if granularity == "Daily" else "week"
        st.caption(f"Activity by {label} — deeper shade = more sessions")

        order = sorted(plot["_pk"].unique())
        label_map = dict(zip(plot["_pk"], plot["period_label"]))
        order_labels = [label_map[p] for p in order]

        # Keep only metrics that actually have activity, so empty facets don't
        # waste space / read as blank.
        active_metrics = [m for m in _UTIL_METRICS
                          if plot.loc[plot["metric"] == m, "count"].sum() > 0]
        heat_src = plot[plot["metric"].isin(active_metrics)] if active_metrics else plot

        base = alt.Chart(heat_src).encode(
            x=alt.X("period_label:N", title=None, sort=order_labels,
                    axis=alt.Axis(labelAngle=-40, labelFontSize=11)),
            y=alt.Y("who:N", title=None, sort=member_order,
                    axis=alt.Axis(labelLimit=260, labelFontSize=11)),
        )
        heat = base.mark_rect(stroke="#ffffff", strokeWidth=2, cornerRadius=3).encode(
            color=alt.Color("count:Q", title="Sessions",
                            scale=alt.Scale(scheme="teals")),
            tooltip=[
                alt.Tooltip("name:N", title="Member"),
                alt.Tooltip("metric:N", title="Activity"),
                alt.Tooltip("period_label:N", title="Period"),
                alt.Tooltip("count:Q", title="Sessions"),
            ],
        )
        txt = base.mark_text(baseline="middle", fontSize=10, fontWeight="bold").encode(
            text=alt.condition("datum.count > 0", alt.Text("count:Q"), alt.value("")),
            color=alt.condition("datum.count > 8", alt.value("white"), alt.value("#16283c")),
        )
        heat_chart = (
            (heat + txt)
            .properties(height=max(220, 26 * len(member_order)),
                        background="transparent")
            .facet(column=alt.Column("metric:N", title=None, sort=_UTIL_METRICS,
                                     header=alt.Header(labelFontSize=13,
                                                       labelFontWeight="bold",
                                                       labelColor="#16283c")))
            .resolve_scale(x="independent")
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(heat_chart, use_container_width=True)
    except Exception:
        wide = (long_df.groupby(["name", "metric"])["count"].sum()
                .unstack(fill_value=0).reindex(columns=_UTIL_METRICS, fill_value=0))
        st.bar_chart(wide, color=[_UTIL_COLORS[m] for m in _UTIL_METRICS])


_UTIL_TD = ("padding:10px 18px;border-bottom:1px solid #eef1f4;"
            "background:#ffffff;color:#16283c;")
_UTIL_TH = ("padding:12px 18px;background:#16283c;color:#ffffff;"
            "white-space:nowrap;text-align:left;font-weight:700;")


def _util_scrollbar_css():
    """Inject once: a visible, teal-tinted scrollbar for the wide tables.
    Colours on the tables themselves are set INLINE per cell (below), so the
    tables stay readable even if this stylesheet is stripped/ignored."""
    st.markdown(
        """
        <style>
        .util-scroll{width:100%;overflow:auto;border:1px solid #e3e7ec;
            border-radius:14px;box-shadow:0 1px 3px rgba(22,40,60,.06);
            background:#ffffff;}
        .util-scroll::-webkit-scrollbar{height:12px;width:12px;}
        .util-scroll::-webkit-scrollbar-track{background:#eef2f5;border-radius:8px;}
        .util-scroll::-webkit-scrollbar-thumb{background:#14b8a6;border-radius:8px;
            border:2px solid #eef2f5;}
        .util-scroll::-webkit-scrollbar-thumb:hover{background:#0d9488;}
        .util-scroll{scrollbar-color:#14b8a6 #eef2f5;scrollbar-width:thin;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_utilization_table(totals):
    """Full-width, light HTML table grouped by role. EVERY cell carries an
    explicit inline light background + dark ink so it never renders black in
    the dark theme and doesn't depend on any injected stylesheet."""
    _util_scrollbar_css()
    metric_bg = {"Evaluation": "#e6faf6", "Training": "#e7f2fb",
                 "Mock Interview": "#fdefe2"}
    metric_ink = {"Evaluation": "#0f766e", "Training": "#1b5f96",
                  "Mock Interview": "#ad4f0f"}

    def _num(v, bg, ink):
        v = int(v)
        strong = "font-weight:700;" if v > 0 else "opacity:.5;font-weight:500;"
        return (f"<td style='padding:10px 18px;border-bottom:1px solid #eef1f4;"
                f"text-align:right;background:{bg};color:{ink};{strong}'>{v}</td>")

    rows_html = []
    ordered = totals.sort_values(["Role", "Member"], ascending=[True, True])
    current_role = None
    for _, r in ordered.iterrows():
        if r["Role"] != current_role:
            current_role = r["Role"]
            rows_html.append(
                f"<tr><td colspan='6' style='padding:12px 18px 6px;"
                f"background:#f2fbf9;color:#0d9488;font-size:.78rem;"
                f"letter-spacing:.06em;text-transform:uppercase;font-weight:800;"
                f"border-bottom:2px solid #14b8a6;'>{r['Role']}</td></tr>"
            )
        rows_html.append(
            "<tr>"
            f"<td style='{_UTIL_TD}font-weight:600;'>{r['Member']}</td>"
            f"<td style='{_UTIL_TD}color:#5d7085;font-size:.85rem;'>{r['Role']}</td>"
            + _num(r["Evaluation"], metric_bg["Evaluation"], metric_ink["Evaluation"])
            + _num(r["Training"], metric_bg["Training"], metric_ink["Training"])
            + _num(r["Mock Interview"], metric_bg["Mock Interview"], metric_ink["Mock Interview"])
            + f"<td style='padding:10px 18px;border-bottom:1px solid #eef1f4;"
              f"text-align:right;background:#f7f9fb;color:#16283c;font-weight:800;'>"
              f"{int(r['Total'])}</td>"
            "</tr>"
        )

    head = (
        "<tr>"
        f"<th style='{_UTIL_TH}'>Member</th>"
        f"<th style='{_UTIL_TH}'>Role</th>"
        f"<th style='{_UTIL_TH}text-align:right;'>Evaluation</th>"
        f"<th style='{_UTIL_TH}text-align:right;'>Training</th>"
        f"<th style='{_UTIL_TH}text-align:right;'>Mock Interview</th>"
        f"<th style='{_UTIL_TH}text-align:right;'>Total</th>"
        "</tr>"
    )
    table = (
        "<div class='util-scroll'>"
        "<table style='width:100%;border-collapse:collapse;font-size:.95rem;"
        "background:#ffffff;'>"
        f"<thead>{head}</thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table></div>"
    )
    st.markdown(table, unsafe_allow_html=True)


def _render_session_details(detail_df):
    """Full session-level breakdown: every counted 30-min slot with its date,
    time, batch code, trainer, module and which member/activity it belongs to.
    Rendered as a light, scrollable, brand-themed HTML table."""
    if detail_df is None or detail_df.empty:
        st.info("No sessions in this window.")
        return

    _util_scrollbar_css()
    metric_chip = {
        "Evaluation":     ("#e6faf6", "#0f766e"),
        "Training":       ("#e7f2fb", "#1b5f96"),
        "Mock Interview": ("#fdefe2", "#ad4f0f"),
    }

    d = detail_df.copy()
    d["_d"] = pd.to_datetime(d["_d"]).dt.date
    d = d.sort_values(["_d", "name", "metric", "slot_time"])

    def _chip(m):
        bg, ink = metric_chip.get(m, ("#eef1f4", "#16283c"))
        return (f"<span style='background:{bg};color:{ink};padding:2px 10px;"
                f"border-radius:999px;font-size:.8rem;font-weight:700;"
                f"white-space:nowrap;'>{m}</span>")

    rows = []
    for _, r in d.iterrows():
        batch = r["batch_code"] or "—"
        trainer = r["trainer"] or "—"
        module = r["module"] or "—"
        slot = r["slot_time"] or "—"
        rows.append(
            "<tr>"
            f"<td style='{_UTIL_TD}white-space:nowrap;'>{r['_d']}</td>"
            f"<td style='{_UTIL_TD}font-weight:600;'>{r['name']}</td>"
            f"<td style='{_UTIL_TD}color:#5d7085;font-size:.85rem;'>{r['role']}</td>"
            f"<td style='{_UTIL_TD}'>{_chip(r['metric'])}</td>"
            f"<td style='{_UTIL_TD}white-space:nowrap;'>{slot}</td>"
            f"<td style='{_UTIL_TD}font-weight:600;white-space:nowrap;'>{batch}</td>"
            f"<td style='{_UTIL_TD}'>{trainer}</td>"
            f"<td style='{_UTIL_TD}color:#5d7085;'>{module}</td>"
            "</tr>"
        )

    head = (
        "<tr>"
        f"<th style='{_UTIL_TH}'>Date</th>"
        f"<th style='{_UTIL_TH}'>Member</th>"
        f"<th style='{_UTIL_TH}'>Role</th>"
        f"<th style='{_UTIL_TH}'>Activity</th>"
        f"<th style='{_UTIL_TH}'>Slot (30 min)</th>"
        f"<th style='{_UTIL_TH}'>Batch Code</th>"
        f"<th style='{_UTIL_TH}'>Trainer</th>"
        f"<th style='{_UTIL_TH}'>Module</th>"
        "</tr>"
    )
    table = (
        "<div class='util-scroll' style='max-height:520px;'>"
        "<table style='width:100%;border-collapse:collapse;font-size:.95rem;"
        "background:#ffffff;'>"
        f"<thead>{head}</thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table></div>"
    )
    st.markdown(table, unsafe_allow_html=True)
    st.caption(f"{len(d)} sessions · each row is one 30-minute CMIS slot.")


@st.fragment
def _admin_utilization_tab(user, role):
    st.markdown("### 📅 Calendar")
    st.markdown("#### Utilization Overview")
    st.caption(
        "Read-only counts of Evaluations, Training and Mock Interviews carried "
        "by each Core AE and their Extended AE team. No sessions are selected "
        "here — switch between a daily and a weekly view below."
    )

    core_options = _core_options_for(role, user["email"])
    if not core_options:
        st.warning("No Core AE mapping found in core_ae_faculty_map.")
        return

    c1, c2 = st.columns([2, 1])
    with c1:
        team_pick = st.selectbox(
            "Team", ["All teams"] + core_options, key="util_team",
            help="Pick one Core AE's team, or 'All teams' for everyone.",
        )
    with c2:
        granularity = st.radio(
            "View", ["Daily", "Weekly"], horizontal=True, key="util_gran",
        )

    # Window:
    #   Daily  -> a SINGLE chosen day, so the counts line up exactly with what
    #             CMIS shows for that date (one merged class per batch block).
    #   Weekly -> the current Mon..Sun week, aggregated per week.
    #
    # The selectable range is fixed to the upcoming 7 days (today .. today+6),
    # regardless of the wider mirror horizon -- the tab should never let you
    # pick a day further out than the 7-day window the rest of the app shows.
    today = date.today()
    w_lo = today
    w_hi = today + timedelta(days=6)
    if granularity == "Daily":
        picked_day = st.date_input(
            "Day", value=w_lo,
            min_value=w_lo, max_value=w_hi, key="util_day",
        )
        d_from = d_to = picked_day
        st.caption(f"Showing {d_from} (single day — matches CMIS for that date)")
    else:
        # current week, clamped into the upcoming-7-day window
        ws, we = current_week_bounds(0)
        d_from = max(ws, w_lo)
        d_to = min(we, w_hi)
        st.caption(f"Showing week {d_from} → {d_to}")

    # ---- Assemble the member roster (Core AE + their Extended AEs) --------
    roles_df = db.get_user_roles()
    name_by = {}
    if roles_df is not None and not roles_df.empty:
        name_by = dict(zip(roles_df["email"].str.lower(), roles_df["name"]))

    def nm(email):
        return name_by.get(email.lower(), email.split("@")[0])

    cores = core_options if team_pick == "All teams" else [team_pick]
    members = []  # (email, name, role_key, role_label)
    seen = set()
    for core in cores:
        if core.lower() not in seen:
            members.append((core, nm(core), "core_ae", "Core AE"))
            seen.add(core.lower())
        for ext in db.extended_aes_for_core(core):
            if ext.lower() not in seen:
                members.append((ext, nm(ext), "extended_ae", "Extended AE"))
                seen.add(ext.lower())

    if not members:
        st.info("No AE members found for this selection.")
        return

    with st.spinner("Tallying utilization…"):
        members_key = tuple(tuple(m) for m in members)
        long_df, detail_df = _build_utilization_long_cached(
            members_key, d_from, d_to, granularity
        )

    # ---- INFORMATION TABLE: one row per member, count columns ------------
    st.markdown("#### 📋 Count Summary — sessions (30 min each)")
    base = pd.DataFrame(
        [(nm(e), r_lbl, e) for (e, _n, _rk, r_lbl) in members],
        columns=["Member", "Role", "email"],
    )
    if long_df.empty:
        totals = base.copy()
        for m in _UTIL_METRICS:
            totals[m] = 0
    else:
        piv = (long_df.groupby(["email", "metric"])["count"].sum()
               .unstack(fill_value=0))
        for m in _UTIL_METRICS:
            if m not in piv.columns:
                piv[m] = 0
        piv = piv[_UTIL_METRICS].reset_index()
        totals = base.merge(piv, on="email", how="left").fillna(0)
        for m in _UTIL_METRICS:
            totals[m] = totals[m].astype(int)
    totals["Total"] = totals[_UTIL_METRICS].sum(axis=1).astype(int)

    _render_utilization_table(totals)
    st.caption("Each session = one 30-minute CMIS slot.")

    # Quick top-line metrics across the whole selection.
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Evaluations", int(totals["Evaluation"].sum()))
    m2.metric("Training", int(totals["Training"].sum()))
    m3.metric("Mock Interviews", int(totals["Mock Interview"].sum()))
    m4.metric("Members", len(members))

    st.divider()

    # ---- SESSION DETAILS: batch code + trainer + slot time ---------------
    st.markdown("#### 🗂️ Session Details — batch, trainer & timing")
    _render_session_details(detail_df)


@st.fragment
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

    # Evaluations tab is now a FIXED rolling 7-day window (today .. today+6),
    # not a user-editable range — the free-range picker that used to live
    # here is gone; single-day drill-down now belongs to the Calendar tab.
    date_from = date.today()
    date_to = date_from + timedelta(days=6)

    lo_d, hi_d, n_total = db.faculty_date_bounds(tuple(faculty))
    if not lo_d or not hi_d:
        st.info("No CMIS sessions found for this Core AE's faculty.")
        return

    with st.expander(
        f"🔎  Filters · {date_from} → {date_to} (next 7 days)", expanded=True
    ):
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

    # The old Calendar tab used to read shared_from/shared_to from here — it's
    # been replaced by the single-day wizard, which has its own day picker,
    # so this cross-tab state hookup is gone.

    # Auto-assignment has been REMOVED. Mock Interviews are now purely a
    # manual pick — see the Mock Interview tab, which reads the nationwide
    # candidate pool via db.get_all_mock_interview_sessions() and lets the
    # person choose, with no session ever assigned on their behalf.


    if pick_trainer != "All trainers":
        sessions = sessions[sessions["_trainer"] == pick_trainer]
    if pick_batch != "All batches":
        sessions = sessions[sessions["batch_code"] == pick_batch]
    sessions = sessions[(sessions["_date"] >= date_from) & (sessions["_date"] <= date_to)]

    st.markdown("###### \U0001F4C5 Jump to a day")
    picked_day = _week_day_strip(date_from, date_to, key="eval_tab")
    if picked_day is not None:
        sessions = sessions[sessions["_date"] == picked_day]

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

    if role == "admin":
        # Admin doesn't self-claim -- same reasoning as the Mock Interview
        # Pool tab: an admin login isn't a real Extended AE/Core AE, so it
        # gets a sheet-style table (matching the MI Pool's own look) with a
        # simple Selected/Not Selected status, and assigns sessions to real
        # team members instead of claiming them itself.
        _admin_evaluations_sheet(sessions, core_ae_email, date_from, date_to, user["email"])
    else:
        _sessions_table(sessions, core_ae_email, date_from, date_to, role, user["email"], key_prefix="eval_tab_")


@st.fragment
def _mock_interview_tab(user, role):
    """Standalone 'My Mock Interviews' tab -- pulled out of the Sessions tab
    so it stands on its own alongside Sessions / MI Pool / Calendar. A
    person's Mock Interviews span every trainer, not just one Core AE's pod,
    so this tab has no Core AE selector -- just a date window."""
    st.markdown("### 🎯 My Mock Interviews")
    ws, we = current_week_bounds()
    c1, c2 = st.columns(2)
    with c1:
        date_from = st.date_input("From", value=ws, key="mi_tab_from")
    with c2:
        date_to = st.date_input("To", value=we + timedelta(days=7), key="mi_tab_to")
    if date_from > date_to:
        st.warning("‘From’ is after ‘To’.")
        return
    core_ae_email = db.core_ae_for_extended(user["email"]) if role == "extended_ae" else None
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
    # Status vocabulary and colours. "Rejected" is a distinct state from
    # "Not Selected": Not Selected = declined from the start (never
    # committed); Rejected = was Selected, then backed out. Both route to the
    # MI pool and both read as "declined" operationally -- the difference is
    # purely the audit trail in the Anudip DB, so we can tell whether someone
    # never wanted an interview or took it and dropped it.
    mi_labels = {"Pending": "Default", "Selected": "Selected",
                 "Not Selected": "Not Selected", "Rejected": "Rejected"}
    mi_card_cls = {"Pending": "scard-avail", "Selected": "scard-mine",
                   "Not Selected": "scard-declined", "Rejected": "scard-declined"}

    def _options_for(saved_status: str, live_status: str) -> list[str]:
        """The dropdown choices available to a row, given its SAVED status
        (what's in the DB) and its LIVE status (what the dropdown currently
        shows this run). The 'back out' option is 'Rejected' once the row has
        EVER been Selected -- i.e. its saved OR live status is Selected/
        Rejected -- otherwise it's 'Not Selected'.

        - fresh (Pending, never touched): Default / Not Selected / Selected
        - declined from start (Not Selected): Not Selected / Selected
        - has been Selected (Selected or Rejected): Selected / Rejected
        """
        ever_selected = saved_status in ("Selected", "Rejected") or \
            live_status in ("Selected", "Rejected")
        if ever_selected:
            return ["Selected", "Rejected"]
        if saved_status == "Not Selected" or live_status == "Not Selected":
            return ["Not Selected", "Selected"]
        return ["Pending", "Not Selected", "Selected"]

    if role == "extended_ae":
        my_mi = db.get_my_mock_interview_claims(user["email"], date_from, date_to)
        if not my_mi.empty:
            st.markdown("#### 🎯 My Mock Interviews")
            st.caption(
                "Auto-assigned Mock Interview sessions for you to observe/evaluate — "
                "these can be from any trainer, not just your own Core AE's pod. "
                "Each starts as **Default** — pick **Selected** to put it on your "
                "Calendar, or **Not Selected** to send it back to the MI pool. Once "
                "you've **Selected** one, backing out is recorded as **Rejected** "
                "(so we can tell it apart from one you never took). You must decide "
                "**every** interview (none left on Default) before saving."
            )
            my_mi = my_mi.sort_values(["_date", "slot_time"]).reset_index(drop=True)
            row_meta: dict[str, tuple] = {}   # widget key -> (row, saved status)
            for _, r in my_mi.iterrows():
                trainer = f"{r.get('f_name') or ''} {r.get('l_name') or ''}".strip() or "Unknown trainer"
                day_lbl = pd.to_datetime(r["_date"]).strftime("%a, %d %b")
                wkey = f"mi_{r['id']}"
                cur = r["status"] if r["status"] in mi_labels else "Pending"
                # Live value: whatever the dropdown holds this run (falls back to
                # the saved status on first render). Drives the card colour.
                live = st.session_state.get(wkey, cur)
                opts = _options_for(cur, live)
                # If the live value fell out of the allowed set (e.g. it was
                # "Pending" but the row has since been Selected), snap to the
                # first valid option.
                if live not in opts:
                    live = opts[0]
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
                        "status", opts, index=opts.index(live),
                        format_func=lambda o: mi_labels.get(o, o),
                        key=wkey, label_visibility="collapsed",
                    )
                row_meta[wkey] = (r, cur)

            if st.button("💾  Save my Mock Interview choices", type="primary", key="save_my_mi"):
                # Validation gate: every interview must be decided (Selected or
                # Not Selected) before ANY of them is saved. A list left with
                # "Default" (Pending) rows half-done shouldn't persist -- the
                # person has to consciously act on each one first.
                undecided = []
                for wkey, (row, cur) in row_meta.items():
                    live_val = st.session_state.get(wkey, cur)
                    if live_val == "Pending":
                        d = pd.to_datetime(row["_date"]).strftime("%a, %d %b")
                        tr = (f"{row.get('f_name') or ''} {row.get('l_name') or ''}".strip()
                              or "Unknown trainer")
                        undecided.append(f"• {d} · {row['slot_time']} — {tr}")

                if undecided:
                    st.error(
                        "Decide every interview before saving — set each to "
                        "**Selected** or **Not Selected** (none may stay on "
                        "**Default**). Still undecided:\n\n" + "\n".join(undecided)
                    )
                else:
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
                        st.success(f"Saved — {changed} Mock Interview decision"
                                   f"{'s' if changed != 1 else ''} recorded.")
                        st.rerun(scope="fragment")
                    else:
                        st.info("All interviews already decided — nothing new to save.")

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


def _sessions_table(sessions, core_ae_email, date_from, date_to, role, user_email, key_prefix=""):
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

    saved = _render_session_cards(df, user_email, can_select, pending, key_prefix=key_prefix)

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
            st.rerun(scope="fragment")


def _eval_sheet_row_html(r: dict) -> str:
    """One row of the admin Evaluations sheet table -- same visual language
    (mi-sheet / mi-cell classes) as the Mock Interview Pool's spreadsheet
    view, so both admin tables read as one consistent system."""
    d = pd.to_datetime(r["_date"])
    start, end = [s.strip() for s in str(r.get("slot_time") or "").split("-", 1)] \
        if "-" in str(r.get("slot_time") or "") else ("", "")
    status_display = r["_status_display"]
    status_cls = "mi-yes" if status_display == "Selected" else "mi-notsel"
    assigned = r.get("_owner_name") or "\u2014"

    def esc(v) -> str:
        s = "" if v is None else str(v)
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                 .replace('"', "&quot;"))

    return (
        "<tr>"
        f"<td>{d.strftime('%d %b %Y')}</td>"
        f"<td>{d.strftime('%a')}</td>"
        f"<td>{esc(r.get('Trainer'))}</td>"
        f"<td>{esc(r.get('batch_code'))}</td>"
        f"<td>{esc(r.get('m_code'))}</td>"
        f"<td>{esc(start)}</td>"
        f"<td>{esc(end)}</td>"
        f"<td>{esc(assigned)}</td>"
        f"<td><span class='mi-cell {status_cls}'>{status_display}</span></td>"
        "</tr>"
    )


def _admin_evaluations_sheet(sessions, core_ae_email, date_from, date_to, user_email):
    """Admin's Evaluations view: the same spreadsheet-style table as the
    Mock Interview Pool tab, status collapsed to a plain Selected /
    Not Selected (no Confirmed/Choosing distinctions to parse), and no
    self-claim -- admin ASSIGNS each session to a real Extended AE or Core
    AE instead, the same "Hand to ..." pattern as the MI Pool admin panel.
    """
    team = db.get_team_selections(core_ae_email, date_from, date_to)
    status_by_key, owner_by_key = {}, {}
    if not team.empty:
        for _, s in team.iterrows():
            k = f"{s['session_date']}|{s['slot_time']}|{s['batch_code'] or ''}"
            status_by_key[k] = s["status"]
            owner_by_key[k] = s["owner_email"]

    df = sessions.copy()
    df["Trainer"] = (df["f_name"].fillna("") + " " + df["l_name"].fillna("")).str.strip()

    def _resolve(row) -> tuple[str, str | None]:
        b = row.get("batch_code") or ""
        members = row.get("_members")
        mems = ([str(x) for x in members] if isinstance(members, (list, tuple)) and members
                else [str(row["slot_time"])])
        for mm in mems:
            k = f"{row['_date']}|{mm}|{b}"
            stt = status_by_key.get(k, "Not Selected")
            if stt in CLAIMED or stt == "Choosing":
                return stt, owner_by_key.get(k)
        k0 = f"{row['_date']}|{mems[0]}|{b}"
        return status_by_key.get(k0, "Not Selected"), owner_by_key.get(k0)

    resolved = df.apply(_resolve, axis=1)
    df["_raw_status"] = [x[0] for x in resolved]
    df["_owner"] = [x[1] for x in resolved]
    # Collapsed display: only ever "Selected" or "Not Selected", regardless
    # of the underlying Confirmed/Choosing/Rejected nuance -- that's what
    # was asked for, and it matches the Mock Interview table's own
    # two-state look.
    df["_status_display"] = df["_raw_status"].apply(
        lambda s: "Selected" if (s in CLAIMED or s == "Choosing") else "Not Selected"
    )

    roles_df = db.get_user_roles()
    name_by = {}
    if not roles_df.empty:
        name_by = dict(zip(roles_df["email"].str.lower(), roles_df["name"]))
    df["_owner_name"] = df["_owner"].apply(
        lambda e: name_by.get(str(e).lower(), str(e).split("@")[0]) if e else None
    )

    df = df.sort_values(["_date", "slot_time"]).reset_index(drop=True)

    total = len(df)
    selected_n = int((df["_status_display"] == "Selected").sum())
    st.markdown(
        f"""<div class="stat-row">
          <div class="stat stat-total"><div class="stat-num">{total:,}</div><div class="stat-lbl">Sessions</div></div>
          <div class="stat stat-claim"><div class="stat-num">{selected_n:,}</div><div class="stat-lbl">\u2713 Selected</div></div>
          <div class="stat stat-avail"><div class="stat-num">{total - selected_n:,}</div><div class="stat-lbl">\u25f7 Not Selected</div></div>
        </div>""",
        unsafe_allow_html=True,
    )

    PER_PAGE = 25
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    p1, p2 = st.columns([1, 4])
    with p1:
        page = st.number_input("Page", 1, pages, 1, key="eval_admin_page")
    with p2:
        st.caption(f"Page {int(page)} of {pages} \u00b7 {total:,} session(s)")
    lo = (int(page) - 1) * PER_PAGE
    chunk = df.iloc[lo:lo + PER_PAGE].reset_index(drop=True)

    cols = ["Date", "Day", "Trainer", "Batch Code", "Module", "Start", "End", "Assigned To", "Status"]
    head = "".join(f"<th>{c}</th>" for c in cols)
    rows_html = "".join(_eval_sheet_row_html(r.to_dict()) for _, r in chunk.iterrows())
    st.markdown(
        f"<div class='mi-sheet-wrap'><table class='mi-sheet'>"
        f"<thead><tr>{head}</tr></thead><tbody>{rows_html}</tbody></table></div>",
        unsafe_allow_html=True,
    )

    def _row_label(r) -> str:
        d = pd.to_datetime(r["_date"]).strftime("%d %b")
        return f"{d} \u00b7 {r.get('slot_time') or ''} \u00b7 {r.get('Trainer') or 'Unknown'} \u00b7 {r.get('batch_code') or ''}"

    chunk["_row_key"] = (
        chunk["_date"].astype(str) + "|" + chunk["slot_time"].astype(str)
        + "|" + chunk["batch_code"].fillna("").astype(str)
    )
    label_by_key = {r["_row_key"]: _row_label(r) for _, r in chunk.iterrows()}
    picked_keys = st.multiselect(
        "Select sessions to act on",
        options=list(label_by_key.keys()),
        format_func=lambda k: label_by_key.get(k, k),
        key=f"eval_admin_pick_{int(page)}",
    )
    picked = [r.to_dict() for _, r in chunk.iterrows() if r["_row_key"] in picked_keys]
    if not picked:
        st.caption("Nothing selected yet.")
        return

    st.markdown(f"**{len(picked)}** session(s) selected.")

    def _assign_to(role_for_target: str, target_email: str) -> None:
        for r in picked:
            members = r.get("_members")
            mems = members if isinstance(members, (list, tuple)) and members else [r["slot_time"]]
            for m_slot in mems:
                sel_id = db.upsert_selection_for_role(
                    role_for_target, target_email, r["_date"], m_slot,
                    r.get("m_code"), r.get("batch_code"), "Selected",
                )
                db.set_highlight_flag(
                    r["_date"], m_slot, r.get("batch_code"),
                    core_ae_email, target_email, True,
                )
                try:
                    db.sync_slot_task_from_evaluation(
                        target_email, role_for_target, r["_date"], m_slot, True, sel_id,
                    )
                except Exception:
                    pass

    acted = False

    st.markdown("##### \U0001F464 Hand to Extended AE")
    ext_members = extended_aes_for_core_safe(core_ae_email)
    if not ext_members:
        st.caption("No Extended AEs mapped to this Core AE.")
    else:
        c1, c2 = st.columns([3, 1])
        with c1:
            pick_ext = st.selectbox(
                "Extended AE", ext_members,
                format_func=lambda e: f"{name_by.get(e.lower(), e.split('@')[0])}  ({e})",
                key="eval_admin_pick_ext", label_visibility="collapsed",
            )
        with c2:
            if st.button("Assign", use_container_width=True, key="eval_admin_assign_ext"):
                try:
                    _assign_to("extended_ae", pick_ext)
                    acted = True
                except Exception as exc:
                    st.error(f"Could not assign: {exc}")

    st.markdown("##### \U0001F9D1\u200D\U0001F4BC Hand to Core AE")
    core_members = sorted(roles_df.loc[roles_df["role"] == "core_ae", "email"].tolist()) \
        if not roles_df.empty else []
    if not core_members:
        st.caption("No Core AE accounts found in user_roles.")
    else:
        c1, c2 = st.columns([3, 1])
        with c1:
            pick_core = st.selectbox(
                "Core AE", core_members,
                format_func=lambda e: f"{name_by.get(e.lower(), e.split('@')[0])}  ({e})",
                key="eval_admin_pick_core", label_visibility="collapsed",
            )
        with c2:
            if st.button("Assign", use_container_width=True, key="eval_admin_assign_core"):
                try:
                    _assign_to("core_ae", pick_core)
                    acted = True
                except Exception as exc:
                    st.error(f"Could not assign: {exc}")

    if acted:
        try:
            db.recompute_weekly_summary(core_ae_email, date_from)
        except Exception:
            pass
        db.clear_app_caches()
        st.success("Assigned.")
        st.rerun(scope="fragment")


def extended_aes_for_core_safe(core_ae_email: str) -> list[str]:
    """extended_aes_for_core, tolerant of a missing/unset Core AE."""
    if not core_ae_email:
        return []
    try:
        return db.extended_aes_for_core(core_ae_email)
    except Exception:
        return []


def _merge_rollup_sessions(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse back-to-back 30-min selection rows into one row per real
    session, the same way _merge_consecutive does for the Calendar/MI
    cards -- so a 2-hour class shows as ONE merged block instead of four
    separate 30-minute lines.

    A run breaks whenever the Extended AE, date, batch or module changes,
    or the previous slot's end time isn't this slot's start time.
    """
    if df.empty:
        return df

    d = df.copy()
    if "is_mi" not in d.columns:
        d["is_mi"] = False
    _slots = d["slot_time"].astype(str)
    d["_start"] = _slots.str.split("-").str[0].str.strip()
    d["_end"] = _slots.str.split("-").str[-1].str.strip()
    d["_sort"] = pd.to_datetime(d["_start"], format="%I:%M %p", errors="coerce")
    d = d.sort_values(
        ["owner_email", "session_date", "batch_code", "module", "is_mi", "_sort"]
    ).reset_index(drop=True)

    _bkey = (
        d["owner_email"].astype(str) + "\x1f"
        + d["session_date"].astype(str) + "\x1f"
        + d["batch_code"].fillna("").astype(str) + "\x1f"
        + d["module"].fillna("").astype(str) + "\x1f"
        + d["is_mi"].astype(str)
    )
    broke = (_bkey != _bkey.shift(1)) | (d["_start"] != d["_end"].shift(1))
    d["_grp"] = broke.cumsum()

    grouped = d.groupby("_grp", sort=False)
    res = grouped.head(1).copy().reset_index(drop=True)

    agg = grouped.agg(
        _merged_count=("slot_time", "size"),
        _span_end=("_end", "last"),
        _span_start=("_start", "first"),
    ).reset_index(drop=True)

    if "time_duration" in d.columns:
        dur_hours = grouped["time_duration"].apply(
            lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum()
        ).reset_index(drop=True)
        res["_duration_min"] = (dur_hours * 60).round()

    res["_merged_count"] = agg["_merged_count"]
    multi = agg["_merged_count"] > 1
    res.loc[multi, "slot_time"] = (
        agg.loc[multi, "_span_start"] + " - " + agg.loc[multi, "_span_end"]
    )

    return res.drop(columns=["_start", "_end", "_sort", "_grp"], errors="ignore")


def _team_rollup(core_ae_email, week_start, week_end):
    st.markdown("#### 👥 My Extended AE Team — Selected Sessions")

    # get_team_extended_ae_activity scopes BOTH frames to
    # extended_aes_for_core(core_ae_email) -- i.e. only the Extended AEs
    # actually paired to THIS Core AE. The previous version called
    # get_selections_for_role("extended_ae", None, ...) with email=None,
    # which pulls every Extended AE's selections SYSTEM-WIDE -- so anyone
    # not on this Core AE's own team (e.g. someone paired to a different
    # Core AE) could show up here by mistake. This also gets us the Mock
    # Interview assignments for free, which the old query never touched at
    # all -- that's why MI sessions were missing from this view entirely.
    sess_raw, mi_raw = db.get_team_extended_ae_activity(core_ae_email, week_start, week_end)

    sessions = sess_raw[sess_raw["status"].isin(list(CLAIMED) + ["Choosing"])].copy() \
        if not sess_raw.empty else sess_raw
    mi = mi_raw[mi_raw["status"].isin(CLAIMED)].copy() if not mi_raw.empty else mi_raw

    if sessions.empty and mi.empty:
        st.caption("No Extended AE selections yet for this week.")
        return

    # ---- enrich Evaluation rows with CMIS details (trainer, module alias,
    # programme, duration) -- the raw selection table only stores
    # owner/date/slot/module-code/batch/status, so on its own it can't show
    # "all the details". Joined on (date, slot_time, batch_code,
    # module=m_code), which is exactly what upsert_selection_for_role wrote
    # the row with. ----------------------------------------------------
    if not sessions.empty:
        sessions["session_date"] = pd.to_datetime(sessions["session_date"]).dt.date
        cmis = db.fetch_sessions_all(week_start, week_end)
        if not cmis.empty:
            cmis = cmis.copy()
            cmis["s_date"] = pd.to_datetime(cmis["s_date"]).dt.date
            cmis["Trainer"] = (cmis["f_name"].fillna("") + " " + cmis["l_name"].fillna("")).str.strip()
            lookup_cols = ["s_date", "slot_time", "batch_code", "m_code",
                           "Trainer", "c_alias", "program_name", "time_duration"]
            lookup = (
                cmis[lookup_cols]
                .drop_duplicates(subset=["s_date", "slot_time", "batch_code", "m_code"])
                .rename(columns={"s_date": "session_date", "m_code": "module"})
            )
            sessions = sessions.merge(
                lookup, on=["session_date", "slot_time", "batch_code", "module"], how="left",
            )
        else:
            sessions["Trainer"] = ""
            sessions["c_alias"] = ""
            sessions["program_name"] = ""
            sessions["time_duration"] = None
        sessions["is_mi"] = False

    # ---- Mock Interview rows already carry trainer_name/c_alias/
    # program_name straight from mock_interview_assignment -- no CMIS join
    # needed. module has no CMIS course-code equivalent for an MI block, so
    # c_alias (e.g. "plr_mi1") stands in for it in the Module slot, same as
    # everywhere else MI rows are displayed. time_duration is left blank --
    # the assignment table stores the whole merged slot_time span already,
    # so the duration-from-slot fallback (below) derives it correctly. ----
    if not mi.empty:
        mi = mi.rename(columns={"extended_ae_email": "owner_email"})
        mi["session_date"] = pd.to_datetime(mi["session_date"]).dt.date
        mi["module"] = mi["c_alias"]
        mi["Trainer"] = mi["trainer_name"]
        mi["time_duration"] = pd.Series([float("nan")] * len(mi), dtype="float64")
        mi["is_mi"] = True

    common_cols = ["owner_email", "session_date", "slot_time", "module", "batch_code",
                    "status", "Trainer", "c_alias", "program_name", "time_duration", "is_mi"]
    frames = [f[common_cols] for f in (sessions, mi) if not f.empty]
    claimed = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=common_cols)

    if claimed.empty:
        st.caption("No Extended AE selections yet for this week.")
        return

    # ---- merge consecutive 30-min rows into one card per real session ----
    merged = _merge_rollup_sessions(claimed)

    # ---- display names for the Extended AE header, same lookup the roster
    # section above already uses ----
    roles_df = db.get_user_roles()
    name_by = {}
    if not roles_df.empty:
        name_by = dict(zip(roles_df["email"].str.lower(), roles_df["name"]))

    def _txt(v) -> str:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        s = str(v).strip()
        return "" if s.lower() in ("nan", "none", "null") else s

    merged["_sort_min"] = merged["slot_time"].apply(_slot_start_minutes)
    merged = merged.sort_values(["owner_email", "session_date", "_sort_min"]).reset_index(drop=True)
    for owner, grp in merged.groupby("owner_email", sort=False):
        nm = name_by.get(str(owner).lower(), str(owner).split("@")[0])
        st.markdown(
            f"<div class='slot-head'>\U0001F464 {nm}"
            f" &nbsp;\u00b7&nbsp; <span style='opacity:.55;font-weight:400'>{owner}</span>"
            f" &nbsp;\u00b7&nbsp; <span class='slot-count'>{len(grp)} session"
            f"{'s' if len(grp) != 1 else ''}</span></div>",
            unsafe_allow_html=True,
        )
        for _, r in grp.iterrows():
            status = r["status"]
            is_mi = bool(r.get("is_mi"))
            is_claimed = status in CLAIMED
            day_lbl = pd.to_datetime(r["session_date"]).strftime("%a, %d %b")

            mins = r.get("_duration_min")
            if pd.notna(mins) and mins:
                dur_txt = _mins_to_text(int(mins))
            else:
                fallback = _parse_slot_minutes(r.get("slot_time"))
                dur_txt = _mins_to_text(fallback) if fallback else "\u2014"

            sub_bits = [dur_txt, f"<b>{_txt(r.get('batch_code'))}</b>", _txt(r.get("module"))]
            module_txt = _txt(r.get("module"))
            c_alias_txt = _txt(r.get("c_alias"))
            extras = [_txt(r.get("Trainer"))]
            if c_alias_txt and c_alias_txt != module_txt:
                extras.append(c_alias_txt)
            extras.append(_txt(r.get("program_name")))
            for extra in extras:
                if extra:
                    sub_bits.append(extra)
            sub_line = " \u00b7 ".join(b for b in sub_bits if b and b != "<b></b>")

            mi_tag = "<span class='pill pill-mi'>\U0001F3AF MI</span>" if is_mi else ""
            pill_cls = "pill-mine" if is_claimed else "pill-avail"
            card_cls = "scard-mine" if is_claimed else "scard-avail"
            if is_mi:
                card_cls += " scard-mi"
            st.markdown(
                f"""<div class="scard {card_cls}">
                  <div class="scard-top">\U0001F551 {day_lbl} &nbsp;\u00b7&nbsp; {_txt(r.get('slot_time'))}
                    {mi_tag} <span class="pill {pill_cls}">{_txt(status)}</span></div>
                  <div class="scard-sub">{sub_line}</div>
                </div>""",
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
def main():
    if "user" not in st.session_state:
        login_view()
    else:
        dashboard()


def _render_session_cards(df, user_email, can_select, pending, key_prefix="") -> bool:
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
            page = st.number_input("Page", 1, pages, 1, 1, key=f"{key_prefix}page_no")
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

    with st.form(f"{key_prefix}claim_form_{page}"):
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
                            key=f"{key_prefix}st_{key}_{page}", label_visibility="collapsed",
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
