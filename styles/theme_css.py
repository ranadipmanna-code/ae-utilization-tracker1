"""
theme_css.py — all portal CSS, extracted from app.py, with a polished
UI/UX upgrade layer appended (Anudip palette: teal / navy-black / white).

Streamlit can't <link> a stylesheet and the CSS is theme-templated ({t[...]}),
so it stays a Python function. app.py imports build_css() from here.
Edit ALL visual styling in this file.
"""


def build_css(t: dict, name: str = "light") -> str:
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
         is nearly invisible against the page background. The COLLAPSED-state
         arrow (shown when the sidebar is closed) lives in the header and uses
         a different test-id than the expanded one, so we target both, plus
         a stable aria-label fallback, and force a teal fill + light glyph. */
      [data-testid="stSidebarCollapsedControl"] button,
      [data-testid="stSidebarCollapseButton"] button,
      [data-testid="stExpandSidebarButton"],
      [data-testid="stExpandSidebarButton"] button,
      [data-testid="collapsedControl"] button,
      [data-testid="stSidebarCollapsedControl"] > button,
      button[aria-label="Open sidebar"],
      button[aria-label="Show sidebar"],
      button[aria-label="keyboard_double_arrow_right"] {{
        background:{t['accent']} !important;
        border:1px solid {t['accent']} !important;
        border-radius:8px !important;
      }}
      [data-testid="stSidebarCollapsedControl"] button *,
      [data-testid="stSidebarCollapseButton"] button *,
      [data-testid="stExpandSidebarButton"] *,
      [data-testid="collapsedControl"] button *,
      button[aria-label="Open sidebar"] *,
      button[aria-label="Show sidebar"] *,
      [data-testid="stSidebarCollapsedControl"] svg,
      [data-testid="stSidebarCollapsedControl"] svg *,
      [data-testid="stSidebarCollapseButton"] svg,
      [data-testid="stSidebarCollapseButton"] svg *,
      [data-testid="stExpandSidebarButton"] svg,
      [data-testid="stExpandSidebarButton"] svg *,
      [data-testid="collapsedControl"] svg,
      [data-testid="collapsedControl"] svg * {{
        color:{t['on_accent']} !important; fill:{t['on_accent']} !important;
        stroke:{t['on_accent']} !important; opacity:1 !important;
      }}
      [data-testid="stSidebarCollapsedControl"] button:hover,
      [data-testid="stSidebarCollapseButton"] button:hover,
      [data-testid="stExpandSidebarButton"]:hover,
      [data-testid="collapsedControl"] button:hover {{
        background:{t['accent_hover']} !important;
        border-color:{t['accent_hover']} !important;
      }}
      /* Tooltip (the ? / help bubble on buttons): the default dark box made
         its text nearly invisible. Give it a solid light card with dark ink
         so the help text is readable. */
      [data-testid="stTooltipContent"],
      [data-baseweb="tooltip"] div,
      div[role="tooltip"] {{
        background:{t['surface']} !important; color:{t['text']} !important;
        border:1px solid {t['border']} !important; border-radius:8px !important;
        box-shadow:0 4px 14px rgba(22,40,60,.18) !important;
        font-size:.82rem !important; opacity:1 !important;
      }}
      [data-testid="stTooltipContent"] * ,
      div[role="tooltip"] * {{ color:{t['text']} !important; }}
      /* Refresh + Sync: force a readable teal filled style in ALL states so
         neither renders dark-on-dark. Both are type="primary" in the sidebar. */
      [data-testid="stSidebar"] .stButton > button[kind="primary"] {{
        background:{t['accent']} !important; color:{t['on_accent']} !important;
        border:1.5px solid {t['accent']} !important; font-weight:600 !important;
        opacity:1 !important;
      }}
      [data-testid="stSidebar"] .stButton > button[kind="primary"] * {{
        color:{t['on_accent']} !important; opacity:1 !important;
      }}
      [data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {{
        background:{t['accent_hover']} !important; color:{t['on_accent']} !important;
        border-color:{t['accent_hover']} !important;
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
      .st-key-sync_btn .stButton > button {{
        background:{t['accent']} !important; color:{t['on_accent']} !important;
        border:1.5px solid {t['accent']} !important; font-weight:600 !important;
      }}
      .st-key-sync_btn .stButton > button:hover {{
        background:{t['accent_hover']} !important; color:{t['on_accent']} !important;
        border-color:{t['accent_hover']} !important;
      }}
      .st-key-sync_btn .stButton > button * {{ color:{t['on_accent']} !important; }}
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
      /* Training is scheduled delivery -- always shown, its own blue tint so
         it reads as "on your calendar", distinct from a claimed evaluation. */
      .scard-training {{ border-left-color:{t['train_border']}; background:{t['train_bg']}; }}
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
      .pill-training {{ background:{t['train_border']}; color:#ffffff; }}
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


      /* ========================================================= */
      /* ===============  UI/UX UPGRADE LAYER  ==================== */
      /* Palette locked to Anudip: teal (accent), navy/black, white. */
      /* Appended last so it refines the look without touching the  */
      /* functional structure above.                                */
      /* ========================================================= */

      /* Page canvas: a whisper of teal so white doesn't feel flat. */
      .stApp {{
        background:
          radial-gradient(1200px 600px at 100% -10%, {t['accent']}0d, transparent 60%),
          radial-gradient(900px 500px at -10% 110%, {t['accent']}0a, transparent 55%),
          {t['bg']} !important;
      }}

      /* Brand header bar: deeper navy with a soft teal glow underline. */
      .brandbar {{
        border-radius:16px !important;
        box-shadow:0 10px 30px rgba(12,23,37,.18), inset 0 0 0 1px rgba(255,255,255,.03) !important;
        position:relative; overflow:hidden;
      }}
      .brandbar::after {{
        content:""; position:absolute; left:0; right:0; bottom:0; height:3px;
        background:linear-gradient(90deg, {t['accent']}, {t['accent_lite']} 60%, transparent);
      }}

      /* Section headings get a short teal rule beneath, like the site. */
      h1 {{ position:relative; }}
      h1::after {{
        content:""; display:block; width:64px; height:4px; margin-top:.5rem;
        border-radius:99px; background:linear-gradient(90deg, {t['accent']}, {t['accent_lite']});
      }}

      /* Tabs: pill-style with a clean teal active state. */
      .stTabs [data-baseweb="tab-list"] {{
        gap:.35rem !important; padding:.35rem !important;
        background:{t['surface']} !important; border:1px solid {t['border']} !important;
        border-radius:14px !important;
      }}
      .stTabs [data-baseweb="tab"] {{
        border-radius:10px !important; padding:.5rem 1rem !important;
        transition:background .15s ease, color .15s ease;
      }}
      .stTabs [aria-selected="true"] {{
        background:{t['accent']}14 !important;
        box-shadow:inset 0 -2px 0 {t['accent']} !important;
        color:{t['accent']} !important; font-weight:600 !important;
      }}
      .stTabs [aria-selected="true"] * {{ color:{t['accent']} !important; }}

      /* Primary buttons -> solid teal with depth (never red).
         This Streamlit build renders NO kind="primary" attribute (only
         emotion-cache classes), so we match ALL of these forms to be safe:
         the kind attr, the data-testid, AND the aria/emotion "primary" class. */
      .stButton > button[kind="primary"],
      .stButton > button[data-testid="stBaseButton-primary"],
      .stButton > button.st-emotion-cache-1krtkoa,
      button[data-testid="baseButton-primary"],
      .stFormSubmitButton > button[kind="primaryFormSubmit"],
      .stFormSubmitButton > button[data-testid="stBaseButton-primaryFormSubmit"] {{
        background:linear-gradient(180deg, {t['accent_lite']}, {t['accent']}) !important;
        color:#ffffff !important; border:1px solid {t['accent']} !important;
        box-shadow:0 6px 16px {t['accent']}38 !important;
      }}
      .stButton > button[kind="primary"] *,
      .stButton > button.st-emotion-cache-1krtkoa *,
      .stFormSubmitButton > button[kind="primaryFormSubmit"] * {{ color:#ffffff !important; }}
      .stButton > button[kind="primary"]:hover,
      .stButton > button.st-emotion-cache-1krtkoa:hover,
      .stFormSubmitButton > button[kind="primaryFormSubmit"]:hover {{
        background:linear-gradient(180deg, {t['accent']}, {t['accent_hover']}) !important;
        box-shadow:0 10px 24px {t['accent']}55 !important; transform:translateY(-1px);
      }}

      /* Sidebar Refresh + Sync -> teal. This build has no kind="primary" attr,
         so we colour the primary-looking sidebar buttons by matching the
         emotion class AND fall back to type=primary forms. Sign out (secondary)
         is quieted right after so it stays outlined. */
      [data-testid="stSidebar"] .stButton > button[kind="primary"],
      [data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"],
      [data-testid="stSidebar"] .stButton > button.st-emotion-cache-1krtkoa {{
        background:linear-gradient(180deg, {t['accent_lite']}, {t['accent']}) !important;
        color:#ffffff !important; border:1px solid {t['accent']} !important;
        box-shadow:0 6px 16px {t['accent']}38 !important;
      }}
      [data-testid="stSidebar"] .stButton > button[kind="primary"] *,
      [data-testid="stSidebar"] .stButton > button.st-emotion-cache-1krtkoa * {{ color:#ffffff !important; }}
      [data-testid="stSidebar"] .stButton > button[kind="primary"]:hover,
      [data-testid="stSidebar"] .stButton > button.st-emotion-cache-1krtkoa:hover {{
        background:linear-gradient(180deg, {t['accent']}, {t['accent_hover']}) !important;
        box-shadow:0 10px 24px {t['accent']}55 !important;
      }}
      /* Broadest cross-version fallback: Streamlit tags primary buttons with
         a data-testid that has varied by version -- match every known form. */
      [data-testid="stSidebar"] button[data-testid*="rimary"],
      button[data-testid*="baseButton-primary"],
      button[data-testid*="BaseButton-primary"] {{
        background:linear-gradient(180deg, {t['accent_lite']}, {t['accent']}) !important;
        color:#ffffff !important; border:1px solid {t['accent']} !important;
        box-shadow:0 6px 16px {t['accent']}38 !important;
      }}
      [data-testid="stSidebar"] button[data-testid*="rimary"] * ,
      button[data-testid*="baseButton-primary"] * {{ color:#ffffff !important; }}

      /* Session / info cards: lift on hover, crisper teal left-accent. */
      .scard {{
        border-radius:14px !important;
        box-shadow:0 1px 2px rgba(12,23,37,.05) !important;
        transition:box-shadow .18s ease, transform .18s ease;
      }}
      .scard:hover {{
        box-shadow:0 8px 22px rgba(12,23,37,.12) !important; transform:translateY(-1px);
      }}

      /* Metric cards (st.metric) get a subtle card treatment. */
      [data-testid="stMetric"] {{
        background:{t['surface']} !important; border:1px solid {t['border']} !important;
        border-radius:14px !important; padding:1rem 1.1rem !important;
        box-shadow:0 1px 2px rgba(12,23,37,.05);
      }}
      [data-testid="stMetricValue"] {{ color:{t['accent']} !important; font-weight:700 !important; }}

      /* Inputs / selects: teal focus ring instead of Streamlit red. */
      [data-baseweb="input"]:focus-within,
      [data-baseweb="select"]:focus-within,
      .stTextInput input:focus, .stDateInput input:focus {{
        border-color:{t['accent']} !important;
        box-shadow:0 0 0 3px {t['accent']}33 !important;
      }}

      /* Radio / toggle selected dot -> teal (was red). */
      [data-baseweb="radio"] [aria-checked="true"] div:first-child {{
        background:{t['accent']} !important; border-color:{t['accent']} !important;
      }}

      /* Dividers: faint teal tint. */
      hr, [data-testid="stDivider"] {{ border-color:{t['accent']}22 !important; }}

      /* Sidebar collapse / expand control -> teal, always visible. */
      [data-testid="stSidebarCollapsedControl"] button,
      [data-testid="stSidebarCollapseButton"] button,
      [data-testid="stExpandSidebarButton"],
      [data-testid="collapsedControl"] button,
      button[aria-label="Open sidebar"],
      button[aria-label="Show sidebar"] {{
        background:{t['accent']} !important; border:1px solid {t['accent']} !important;
        border-radius:9px !important;
      }}
      [data-testid="stSidebarCollapsedControl"] svg *,
      [data-testid="stSidebarCollapseButton"] svg *,
      [data-testid="stExpandSidebarButton"] svg *,
      [data-testid="collapsedControl"] svg *,
      button[aria-label="Open sidebar"] svg *,
      button[aria-label="Show sidebar"] svg * {{
        fill:#ffffff !important; stroke:#ffffff !important; color:#ffffff !important;
      }}

      /* Tooltip: readable light card (not dark-on-dark). */
      [data-testid="stTooltipContent"], div[role="tooltip"] {{
        background:{t['surface']} !important; color:{t['text']} !important;
        border:1px solid {t['border']} !important; border-radius:9px !important;
        box-shadow:0 6px 18px rgba(12,23,37,.20) !important;
      }}
      [data-testid="stTooltipContent"] *, div[role="tooltip"] * {{ color:{t['text']} !important; }}

    </style>
    """
