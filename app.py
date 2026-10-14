from __future__ import annotations

import html
import io
import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import streamlit as st
import streamlit.components.v1 as components

# ============================================================================
# BACKEND IMPORT (isolated so the app still opens if agent.py / API keys are
# missing. pipeline.py is never modified or reimplemented here.)
# ============================================================================
PIPELINE_IMPORT_ERROR: Optional[str] = None
try:
    from pipeline import run_research_pipeline  # noqa: F401
    PIPELINE_AVAILABLE = True
except Exception as exc:  # pragma: no cover - environment dependent
    PIPELINE_AVAILABLE = False
    PIPELINE_IMPORT_ERROR = str(exc)

    def run_research_pipeline(topic: str) -> dict:  # type: ignore
        raise RuntimeError(
            "pipeline.py could not be loaded: "
            f"{PIPELINE_IMPORT_ERROR}. Make sure pipeline.py and agent.py "
            "(with build_search_agent, build_reader_agent, writer_chain, "
            "critic_chain) are in the app folder and that any required API keys are set."
        )


APP_NAME = "Waypoint"
TAGLINE = "Multi-agent research briefings, sourced and reviewed"
EXAMPLE_TOPICS = [
    "Generative AI in healthcare",
    "Solid-state batteries",
    "Space economy",
    "Cybersecurity trends",
    "Future of remote work",
]
PAGES = ["Home", "Research", "Reports", "Workflow", "Settings", "About"]

URL_PATTERN = re.compile(r"https?://[^\s\)\]\"'>,]+")

AGENTS = [
    ("Search", "Finds recent, reliable sources.", [
        "Searches trusted sources across the internet.",
        "Finds reliable websites.",
        "Filters duplicate links.",
        "Ranks search results.",
        "Returns verified resources.",
    ]),
    ("Reader", "Pulls out the useful text.", [
        "Reads webpages.",
        "Extracts useful information.",
        "Removes HTML.",
        "Cleans text.",
        "Creates structured summaries.",
    ]),
    ("Writer", "Drafts the structured report.", [
        "Uses extracted knowledge.",
        "Generates a professional research report.",
        "Creates sections and headings.",
        "Adds a conclusion.",
        "Produces references.",
    ]),
    ("Critic", "Reviews it and flags gaps.", [
        "Evaluates report quality.",
        "Detects weaknesses.",
        "Suggests improvements.",
        "Provides a final quality assessment.",
    ]),
]

CAPABILITIES = [
    ("Source search", "Finds recent, reliable sources across the web for any topic."),
    ("Page reading", "Scrapes and cleans the most relevant source into structured text."),
    ("Report writing", "Turns the research into a structured, well-referenced report."),
    ("Independent review", "A critic agent reads the report and lists what to improve."),
    ("Live web grounding", "Works from current web content, not only training data."),
    ("One call, four agents", "A single pipeline call runs every agent from start to finish."),
]

esc = html.escape


# ============================================================================
# DATA HELPERS (only normalize / measure what pipeline.py already returns)
# ============================================================================
def to_text(value: Any) -> str:
    """Normalize whatever pipeline.py returns for a field into plain text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    content = getattr(value, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(value, dict):
        for key in ("content", "text", "output", "report"):
            if key in value and isinstance(value[key], str):
                return value[key]
    return str(value)


def extract_urls(text: str) -> List[str]:
    if not text:
        return []
    seen: List[str] = []
    for match in URL_PATTERN.findall(text):
        cleaned = match.rstrip(".,;:")
        if cleaned not in seen:
            seen.append(cleaned)
    return seen


def count_words(text: str) -> int:
    return len(text.split()) if text else 0


def estimate_reading_time(word_count: int, words_per_minute: int = 200) -> int:
    return max(1, round(word_count / words_per_minute)) if word_count > 0 else 0


def try_extract_score(feedback_text: str) -> Optional[str]:
    """Best-effort score extraction; returns None rather than a fake number."""
    if not feedback_text:
        return None
    patterns = [
        r"(?:overall\s+score|score|rating)\s*[:\-]?\s*(\d{1,3}\s*/\s*\d{1,3})",
        r"(?:overall\s+score|score|rating)\s*[:\-]?\s*(\d{1,3}\s*(?:%|percent))",
        r"(?:overall\s+score|score|rating)\s*[:\-]?\s*(\d(?:\.\d)?\s*/\s*10)",
    ]
    for pattern in patterns:
        match = re.search(pattern, feedback_text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


@dataclass
class ResearchRun:
    id: str
    topic: str
    created_at: str
    search_results: str
    scraped_content: str
    report: str
    feedback: str
    execution_seconds: float
    error: Optional[str] = None

    @property
    def word_count(self) -> int:
        return count_words(self.report)

    @property
    def reading_minutes(self) -> int:
        return estimate_reading_time(self.word_count)

    @property
    def sources(self) -> List[str]:
        return extract_urls(self.search_results)

    @property
    def score(self) -> Optional[str]:
        return try_extract_score(self.feedback)

    @property
    def file_stem(self) -> str:
        return re.sub(r"[^A-Za-z0-9_-]+", "_", self.topic.strip()).strip("_") or "report"


def run_pipeline_safely(topic: str) -> ResearchRun:
    """Call the real backend, timing it, never fabricating data on failure."""
    start = time.perf_counter()
    run_id = str(uuid.uuid4())[:8]
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        state: Dict[str, Any] = run_research_pipeline(topic)
        elapsed = time.perf_counter() - start
        return ResearchRun(
            id=run_id, topic=topic, created_at=created_at,
            search_results=to_text(state.get("search_results", "")),
            scraped_content=to_text(state.get("scraped_content", "")),
            report=to_text(state.get("report", "")),
            feedback=to_text(state.get("feedback", "")),
            execution_seconds=elapsed, error=None,
        )
    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - start
        return ResearchRun(
            id=run_id, topic=topic, created_at=created_at,
            search_results="", scraped_content="", report="", feedback="",
            execution_seconds=elapsed, error=str(exc),
        )


# ============================================================================
# EXPORT BUILDERS
# ============================================================================
def build_markdown_document(run: ResearchRun) -> str:
    urls = run.sources
    sources_block = "\n".join(f"- {u}" for u in urls) if urls else "_No source URLs detected in search output._"
    return f"""# Research Report: {run.topic}

*Generated by {APP_NAME} on {run.created_at}*

---

## Report

{run.report}

---

## Critic Review

{run.feedback}

---

## Sources Referenced

{sources_block}

---

*Word count: {run.word_count} | Estimated reading time: {run.reading_minutes} min | Generation time: {run.execution_seconds:.1f}s*
"""


def build_plain_text_document(run: ResearchRun) -> str:
    urls = run.sources
    sources_block = "\n".join(f"- {u}" for u in urls) if urls else "No source URLs detected."
    return (
        f"RESEARCH REPORT: {run.topic}\nGenerated: {run.created_at}\n{'=' * 60}\n\n"
        f"REPORT\n{'-' * 60}\n{run.report}\n\n"
        f"CRITIC REVIEW\n{'-' * 60}\n{run.feedback}\n\n"
        f"SOURCES\n{'-' * 60}\n{sources_block}\n"
    )


def build_pdf_bytes(run: ResearchRun) -> Optional[bytes]:
    """Render to PDF via fpdf2 if installed; returns None otherwise."""
    try:
        from fpdf import FPDF
    except Exception:
        return None

    def sanitize(text: str) -> str:
        return text.encode("latin-1", "replace").decode("latin-1") if text else ""

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_left_margin(10)
    pdf.set_right_margin(10)
    page_width = pdf.w - pdf.l_margin - pdf.r_margin

    def section(title: str, body: str) -> None:
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 13)
        pdf.multi_cell(page_width, 8, sanitize(title))
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(page_width, 5.5, sanitize(body or "Not available."))
        pdf.ln(3)

    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(page_width, 10, sanitize(f"Research Report: {run.topic}"))
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(page_width, 6, sanitize(f"Generated: {run.created_at}"))
    pdf.ln(4)

    section("Report", run.report)
    section("Critic Review", run.feedback)
    urls = run.sources
    section("Sources Referenced", "\n".join(urls) if urls else "No source URLs detected.")

    # fpdf2 returns a bytearray from output(); convert for st.download_button.
    return bytes(pdf.output())


# ============================================================================
# THEME / CSS
# Direction: midnight navy ground with slate panels. Indigo is the action
# colour; cyan marks AI highlights and progress.
# Flat surfaces, hairline rules, small radii. No shadows or gradients.
# ============================================================================
FONT_SCALES = {"Small": "0.92rem", "Medium": "1rem", "Large": "1.1rem"}

_LIGHT = {
    "bg": "#0F172A", "nav": "#111827", "surface": "#1E293B", "ink": "#F8FAFC", "muted": "#94A3B8",
    "line": "#334155", "cobalt": "#6366F1", "cobalt_ink": "#FFFFFF", "signal": "#22D3EE",
    "signal_ink": "#0F172A", "ok": "#34D399", "warn": "#E3B341", "bad": "#F07C7C",
}
_DARK = dict(_LIGHT)

_BASE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap');

html, body, .stApp, [data-testid="stAppViewContainer"] {
    background: var(--wp-bg) !important; color: var(--wp-ink) !important;
    font-family: 'Bricolage Grotesque', system-ui, sans-serif !important;
}
header[data-testid="stHeader"], [data-testid="stSidebar"], [data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"], #MainMenu, footer, [data-testid="stToolbar"] { display: none !important; }
.block-container { max-width: 1080px !important; padding: 1.6rem 1.5rem 4rem !important; }
.stApp p, .stApp li, .stApp label, .stApp span { font-size: var(--wp-fs); }
h1, h2, h3, h4 { font-family: 'Bricolage Grotesque', sans-serif !important; color: var(--wp-ink) !important; letter-spacing: -0.015em; }
a { color: var(--wp-signal) !important; text-decoration: underline; text-underline-offset: 3px; }
[data-testid="stMarkdownContainer"] { color: var(--wp-ink); }
[data-testid="stWidgetLabel"] p, [data-testid="stToggle"] p, [data-testid="stCheckbox"] p { color: var(--wp-ink) !important; }
[data-testid="stCaptionContainer"] { color: var(--wp-muted) !important; }

/* masthead */
.wp-brand { display: flex; align-items: baseline; gap: 0.75rem; padding-top: 0.35rem; }
.wp-brand-name { font-size: 1.55rem; font-weight: 700; letter-spacing: -0.03em; }
.wp-brand-name i { display: inline-block; width: 0.55rem; height: 0.55rem; border-radius: 50%; background: var(--wp-signal); margin-left: 0.2rem; }
div[data-testid="stHorizontalBlock"]:has(.wp-brand) { background: var(--wp-nav); box-shadow: 0 0 0 0.3rem var(--wp-nav); }
.wp-masthead-rule { border: 0; border-top: 1px solid var(--wp-line); margin: 0.4rem 0 2rem; }

/* top navigation: plain text tabs with an underline on the current page */
div[data-testid="stRadio"] > label { display: none !important; }
div[data-testid="stRadio"] div[role="radiogroup"] { gap: 1.4rem; justify-content: flex-end; flex-wrap: wrap; }
div[data-testid="stRadio"] label[data-baseweb="radio"] { padding: 0.35rem 0; margin: 0; border-bottom: 2px solid transparent; cursor: pointer; }
div[data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child { display: none !important; }
div[data-testid="stRadio"] label[data-baseweb="radio"] p { color: var(--wp-muted); font-weight: 500; }
div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) { border-bottom-color: var(--wp-cobalt); }
div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) p { color: var(--wp-ink); font-weight: 700; }

/* hero */
.wp-hero { padding: 1.5rem 0 0.5rem; max-width: 760px; }
.wp-hero h1 { font-size: clamp(2.4rem, 6vw, 4.1rem); line-height: 1.02; font-weight: 700; margin: 0 0 1.1rem; }
.wp-lede { font-size: 1.12rem; line-height: 1.6; color: var(--wp-muted); max-width: 60ch; margin: 0; }

/* the route: the four agents as stops on one line (this is a real sequence) */
.wp-route { display: grid; grid-template-columns: repeat(4, 1fr); position: relative; margin: 2.6rem 0 3rem; }
.wp-route::before { content: ""; position: absolute; left: 0; right: 0; top: 11px; height: 2px; background: var(--wp-line); }
.wp-route::after { content: ""; position: absolute; left: 0; right: 0; top: 11px; height: 2px; background: var(--wp-signal); transform-origin: left; }
.wp-stop { position: relative; padding-right: 1.4rem; }
.wp-pin { position: relative; z-index: 1; width: 24px; height: 24px; border-radius: 50%; background: var(--wp-bg);
    border: 2px solid var(--wp-cobalt); color: var(--wp-ink); font-size: 0.72rem; font-weight: 700;
    display: flex; align-items: center; justify-content: center; }
.wp-stop:last-child .wp-pin { background: var(--wp-signal); border-color: var(--wp-signal); color: var(--wp-signal-ink); }
.wp-stop-name { font-weight: 700; font-size: 1.05rem; margin: 0.7rem 0 0.15rem; }
.wp-stop-desc { color: var(--wp-muted); font-size: 0.93rem; line-height: 1.45; margin: 0; }

/* ruled capability list */
.wp-caps { display: grid; grid-template-columns: 1fr 1fr; column-gap: 3rem; margin: 0.5rem 0 1.5rem; }
.wp-cap { padding: 1rem 0; border-top: 1px solid var(--wp-line); }
.wp-cap b { display: block; font-size: 1.02rem; margin-bottom: 0.2rem; }
.wp-cap span { color: var(--wp-muted); font-size: 0.95rem; line-height: 1.5; }
.wp-section-title { font-size: 1.35rem; font-weight: 700; margin: 0 0 0.3rem; }
.wp-muted { color: var(--wp-muted); }

/* vertical rail (Workflow page) */
.wp-rail { border-left: 2px solid var(--wp-line); margin: 1.5rem 0 1rem 12px; }
.wp-rail-step { position: relative; padding: 0 0 2rem 1.8rem; }
.wp-rail-step .wp-pin { position: absolute; left: -13px; top: 0; }
.wp-rail-step:last-child .wp-pin { background: var(--wp-signal); border-color: var(--wp-signal); color: var(--wp-signal-ink); }
.wp-rail-step h3 { font-size: 1.25rem; margin: 0 0 0.1rem; }
.wp-rail-step ul { margin: 0.5rem 0 0; padding-left: 1.1rem; color: var(--wp-muted); }
.wp-rail-step li { line-height: 1.6; }

/* results header + stat strip */
.wp-result-title { font-size: clamp(1.7rem, 3.4vw, 2.4rem); font-weight: 700; margin: 0.2rem 0 0.9rem; line-height: 1.1; }
.wp-stats { display: flex; flex-wrap: wrap; border-top: 1px solid var(--wp-line); border-bottom: 1px solid var(--wp-line); margin: 0.4rem 0 1.2rem; }
.wp-stat { padding: 0.8rem 1.6rem 0.8rem 0; margin-right: 1.6rem; }
.wp-stat + .wp-stat { padding-left: 1.6rem; border-left: 1px solid var(--wp-line); }
.wp-stat-value { font-size: 1.5rem; font-weight: 700; line-height: 1.1; }
.wp-stat-label { color: var(--wp-muted); font-size: 0.85rem; }

/* status text */
.wp-status { display: inline-flex; align-items: center; gap: 0.45rem; font-weight: 600; font-size: 0.92rem; }
.wp-dot { width: 0.6rem; height: 0.6rem; border-radius: 50%; display: inline-block; }
.wp-dot.ok { background: var(--wp-ok); } .wp-dot.warn { background: var(--wp-warn); } .wp-dot.bad { background: var(--wp-bad); }
.wp-score { display: inline-block; margin-left: 0.8rem; padding: 0.1rem 0.6rem; border-radius: 4px; background: var(--wp-signal); color: var(--wp-signal-ink); border: 1px solid var(--wp-cobalt); font-weight: 700; font-size: 0.9rem; }

/* comfortable reading column for generated text */
[class*="st-key-reading"] { max-width: 68ch; }
[class*="st-key-reading"] p, [class*="st-key-reading"] li { font-family: 'Source Serif 4', Georgia, serif !important; font-size: 1.06rem; line-height: 1.75; }
[class*="st-key-reading"] h1, [class*="st-key-reading"] h2, [class*="st-key-reading"] h3 { margin-top: 1.6rem; }

/* streamlit widgets */
div[data-baseweb="input"] > div, div[data-baseweb="select"] > div, div[data-baseweb="base-input"] {
    background: var(--wp-surface) !important; border: 1px solid var(--wp-line) !important; border-radius: 6px !important; }
div[data-baseweb="input"] input { color: var(--wp-ink) !important; font-size: 1.05rem !important; padding: 0.7rem 0.8rem !important; }
div[data-baseweb="input"]:focus-within > div { border-color: var(--wp-cobalt) !important; }
[data-testid="stTextInput"] label p, [data-testid="stSelectbox"] label p { font-weight: 600; }

div[data-testid="stButton"] button, div[data-testid="stDownloadButton"] button {
    border-radius: 6px !important; border: 1px solid var(--wp-line) !important; background: var(--wp-surface) !important;
    color: var(--wp-ink) !important; font-weight: 600 !important; box-shadow: none !important; }
div[data-testid="stButton"] button:hover, div[data-testid="stDownloadButton"] button:hover { border-color: var(--wp-cobalt) !important; color: var(--wp-signal) !important; }
div[data-testid="stButton"] button[kind="primary"], div[data-testid="stButton"] button[data-testid="stBaseButton-primary"] {
    background: var(--wp-cobalt) !important; color: var(--wp-cobalt-ink) !important; border: 1px solid var(--wp-cobalt) !important; }
div[data-testid="stButton"] button[kind="primary"] p, div[data-testid="stButton"] button[data-testid="stBaseButton-primary"] p { color: var(--wp-cobalt-ink) !important; }
div[data-testid="stButton"] button[kind="primary"]:hover { filter: brightness(1.08); }
.st-key-topics button { min-height: 0 !important; padding: 0.25rem 0.5rem !important; }
.st-key-topics button p { font-size: 0.85rem !important; font-weight: 500 !important; }

button[data-baseweb="tab"] { color: var(--wp-muted) !important; font-weight: 600 !important; }
button[data-baseweb="tab"][aria-selected="true"] { color: var(--wp-ink) !important; }
div[data-baseweb="tab-highlight"] { background-color: var(--wp-cobalt) !important; }
div[data-baseweb="tab-border"] { background-color: var(--wp-line) !important; }

div[data-testid="stExpander"] { border: 1px solid var(--wp-line) !important; border-radius: 8px !important; background: var(--wp-surface); }
div[data-testid="stExpander"] summary p { font-weight: 600; }
div[data-testid="stAlert"] { border-radius: 6px !important; }
div[data-testid="stStatus"] { border-radius: 8px !important; border: 1px solid var(--wp-line) !important; background: var(--wp-surface) !important; }
code, pre { font-family: ui-monospace, 'SF Mono', Menlo, monospace !important; }
.wp-hr { border: 0; border-top: 1px solid var(--wp-line); margin: 2rem 0; }

.wp-avatar { width: 88px; height: 88px; border-radius: 50%; background: var(--wp-cobalt); color: var(--wp-cobalt-ink);
    display: flex; align-items: center; justify-content: center; font-size: 2rem; font-weight: 700; }
.wp-links a { margin-right: 1.4rem; font-weight: 600; text-decoration: underline; text-underline-offset: 3px; }

@media (max-width: 760px) {
    .wp-route { grid-template-columns: 1fr; margin-left: 11px; }
    .wp-route::before, .wp-route::after { left: 11px; right: auto; top: 0; bottom: 0; width: 2px; height: auto; transform-origin: top; }
    .wp-stop { padding: 0 0 1.5rem 2.2rem; }
    .wp-stop .wp-pin { position: absolute; left: -1px; top: 0; }
    .wp-stop-name { margin-top: 0; }
    .wp-caps { grid-template-columns: 1fr; }
    div[data-testid="stRadio"] div[role="radiogroup"] { justify-content: flex-start; }
    .wp-stat + .wp-stat { padding-left: 1rem; }
}
"""

_ANIM_CSS = """
/* one orchestrated moment: the route line draws itself when Home opens */
@keyframes wpDraw { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@keyframes wpDrawY { from { transform: scaleY(0); } to { transform: scaleY(1); } }
.wp-route::after { animation: wpDraw 1.4s ease-out both; }
@media (max-width: 760px) { .wp-route::after { animation-name: wpDrawY; } }
@media (prefers-reduced-motion: reduce) { .wp-route::after { animation: none; } }
"""


def get_custom_css(theme: str = "Light", font_size: str = "Medium", animations: bool = True) -> str:
    t = _DARK if theme == "Dark" else _LIGHT
    root = (
        ":root{"
        f"--wp-bg:{t['bg']};--wp-nav:{t['nav']};--wp-surface:{t['surface']};--wp-ink:{t['ink']};--wp-muted:{t['muted']};"
        f"--wp-line:{t['line']};--wp-cobalt:{t['cobalt']};--wp-cobalt-ink:{t['cobalt_ink']};"
        f"--wp-signal:{t['signal']};--wp-signal-ink:{t['signal_ink']};--wp-ok:{t['ok']};--wp-warn:{t['warn']};--wp-bad:{t['bad']};"
        f"--wp-fs:{FONT_SCALES.get(font_size, '1rem')};"
        "}"
    )
    return f"<style>{root}{_BASE_CSS}{_ANIM_CSS if animations else ''}</style>"


# ============================================================================
# SESSION STATE
# ============================================================================
def init_session_state() -> None:
    defaults = {
        "reports": [], "current_run": None, "theme": "Light",
        "font_size": "Medium", "animations": True, "topic_input": "",
        "nav_page": "Home",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def inject_css() -> None:
    st.markdown(
        get_custom_css(st.session_state["theme"], st.session_state["font_size"], st.session_state["animations"]),
        unsafe_allow_html=True,
    )


# ============================================================================
# SMALL REUSABLE UI HELPERS
# ============================================================================
def html_block(markup: str) -> None:
    """Render raw HTML; strips indentation so Markdown never treats it as code."""
    st.markdown(" ".join(line.strip() for line in markup.splitlines() if line.strip()), unsafe_allow_html=True)


def go_to(page: str) -> None:
    st.session_state["_nav_override"] = page
    st.rerun()


def copy_button(text: str, label: str, key: str) -> None:
    safe_text = json.dumps(text or "").replace("</", "<\\/")
    components.html(
        f"""
        <div style="font-family:system-ui,sans-serif;">
          <button id="b" style="width:100%;padding:0.5rem 0.9rem;border-radius:6px;border:1px solid rgba(128,128,128,0.4);
            background:transparent;color:inherit;cursor:pointer;font-weight:600;font-size:0.9rem;">{esc(label)}</button>
        </div>
        <script>
          (function() {{
            var b = document.getElementById("b");
            var original = b.innerText;
            b.addEventListener("click", function() {{
              navigator.clipboard.writeText({safe_text}).then(function() {{
                b.innerText = "Copied";
                setTimeout(function() {{ b.innerText = original; }}, 1500);
              }});
            }});
          }})();
        </script>
        """,
        height=44,
    )


def status_text(text: str, kind: str = "ok") -> str:
    return f'<span class="wp-status"><span class="wp-dot {kind}"></span>{esc(text)}</span>'


def stats_strip(items: List[tuple]) -> str:
    cells = "".join(
        f'<div class="wp-stat"><div class="wp-stat-value">{esc(value)}</div>'
        f'<div class="wp-stat-label">{esc(label)}</div></div>'
        for label, value in items
    )
    return f'<div class="wp-stats">{cells}</div>'


def agent_status(run: ResearchRun, has_content: bool) -> str:
    if run.error:
        return status_text("Failed", "bad")
    return status_text("Completed", "ok") if has_content else status_text("No data returned", "warn")


def route_markup() -> str:
    stops = "".join(
        f'<div class="wp-stop"><div class="wp-pin">{i}</div>'
        f'<div class="wp-stop-name">{esc(name)}</div><p class="wp-stop-desc">{esc(desc)}</p></div>'
        for i, (name, desc, _) in enumerate(AGENTS, start=1)
    )
    return f'<div class="wp-route">{stops}</div>'


# ============================================================================
# PAGES
# ============================================================================
def page_home() -> None:
    html_block(
        f"""
        <section class="wp-hero">
            <h1>Four agents. One sourced report.</h1>
            <p class="wp-lede">{esc(APP_NAME)} searches the web, reads the best sources, writes a structured
            research report, and has a second agent review it. Give it a topic and check the result
            against the sources it lists.</p>
        </section>
        """
    )

    if not PIPELINE_AVAILABLE:
        st.warning(
            "The research backend isn't connected yet. Add `pipeline.py` and `agent.py` "
            "(with `build_search_agent`, `build_reader_agent`, `writer_chain`, `critic_chain`) "
            f"to this folder to turn on research. Details: {PIPELINE_IMPORT_ERROR}"
        )

    cta, _ = st.columns([1, 2])
    with cta:
        if st.button("Start a research run", type="primary", use_container_width=True):
            go_to("Research")

    html_block(route_markup())

    html_block('<h2 class="wp-section-title">What it does</h2>')
    caps = "".join(f'<div class="wp-cap"><b>{esc(t)}</b><span>{esc(d)}</span></div>' for t, d in CAPABILITIES)
    html_block(f'<div class="wp-caps">{caps}</div>')


def render_run_results(run: ResearchRun) -> None:
    if run.error:
        st.error(
            f"The pipeline stopped with an error: {run.error}. "
            "Check that pipeline.py loads and your API keys are set, then run it again."
        )
        return

    html_block(f'<h2 class="wp-result-title">{esc(run.topic)}</h2>')
    html_block(
        stats_strip([
            ("Execution time", f"{run.execution_seconds:.1f}s"),
            ("Sources found", str(len(run.sources))),
            ("Report words", f"{run.word_count:,}"),
            ("Reading time", f"{run.reading_minutes} min"),
            ("Critic score", run.score or "n/a"),
        ])
    )

    dl = st.columns(4)
    with dl[0]:
        st.download_button("Download .md", build_markdown_document(run), file_name=f"{run.file_stem}_report.md",
                           mime="text/markdown", use_container_width=True, key=f"md_{run.id}")
    with dl[1]:
        st.download_button("Download .txt", build_plain_text_document(run), file_name=f"{run.file_stem}_report.txt",
                           mime="text/plain", use_container_width=True, key=f"txt_{run.id}")
    with dl[2]:
        pdf_bytes = build_pdf_bytes(run)
        if pdf_bytes:
            st.download_button("Download .pdf", pdf_bytes, file_name=f"{run.file_stem}_report.pdf",
                               mime="application/pdf", use_container_width=True, key=f"pdf_{run.id}")
        else:
            st.caption("Install `fpdf2` to enable PDF export.")
    with dl[3]:
        copy_button(run.report, "Copy report", key=f"copy_{run.id}")

    tab_report, tab_sources, tab_reader, tab_critic = st.tabs(["Report", "Sources", "Reader notes", "Critic review"])

    with tab_report:
        html_block(agent_status(run, bool(run.report)))
        st.caption(f"Writer agent. {run.word_count:,} words, about {run.reading_minutes} min to read.")
        with st.container(key=f"reading_{run.id}"):
            st.markdown(run.report or "_The writer agent returned no content._")

    with tab_sources:
        urls = run.sources
        if urls:
            st.caption(f"{len(urls)} link(s) found in the search agent's output.")
            for i, url in enumerate(urls, start=1):
                st.markdown(f"{i}. [{url}]({url})")
        else:
            st.info("No source URLs were found in the search output.")

    with tab_reader:
        html_block(agent_status(run, bool(run.scraped_content)))
        st.caption(f"Reader agent. {count_words(run.scraped_content):,} words extracted.")
        st.markdown(run.scraped_content or "_The reader agent returned no content._")

    with tab_critic:
        html_block(agent_status(run, bool(run.feedback)) + (f'<span class="wp-score">Score {esc(run.score)}</span>' if run.score else ""))
        st.caption("Critic agent review")
        with st.container(key=f"reading_critic_{run.id}"):
            st.markdown(run.feedback or "_The critic agent returned no content._")


def set_topic(value: str) -> None:
    """Button callback: runs before the text box is built, so it may set its value."""
    st.session_state["topic_input"] = value


def page_research() -> None:
    st.markdown("## Research")
    st.markdown('<p class="wp-muted">Enter a topic. The four agents search, read, write and review.</p>', unsafe_allow_html=True)

    topic = st.text_input(
        "What should we look into?", placeholder="For example: solid-state batteries", key="topic_input",
    )

    st.caption("Or start from a suggestion")
    with st.container(key="topics"):
        ex_cols = st.columns(len(EXAMPLE_TOPICS))
        for i, example in enumerate(EXAMPLE_TOPICS):
            with ex_cols[i]:
                st.button(example, key=f"example_{i}", use_container_width=True,
                          on_click=set_topic, args=(example,))

    start = st.button("Run research", type="primary", use_container_width=True, disabled=not PIPELINE_AVAILABLE)

    if not PIPELINE_AVAILABLE:
        st.warning(
            "The research backend isn't connected. Add `pipeline.py` and `agent.py` to this app's folder "
            f"to enable research. ({PIPELINE_IMPORT_ERROR})"
        )

    if start:
        if not topic.strip():
            st.error("Enter a research topic first.")
        else:
            with st.status(f"Running agents on “{topic.strip()}”", expanded=True) as status:
                st.write("Search, Reader, Writer and Critic run in order. This usually takes a minute or more.")
                run = run_pipeline_safely(topic.strip())
                if run.error:
                    status.update(label="Pipeline failed", state="error", expanded=False)
                else:
                    status.update(label=f"Finished in {run.execution_seconds:.1f}s", state="complete", expanded=False)

            st.session_state["current_run"] = run
            st.session_state["reports"].insert(0, run)

    st.markdown('<hr class="wp-hr">', unsafe_allow_html=True)

    current: Optional[ResearchRun] = st.session_state.get("current_run")
    if current:
        render_run_results(current)
    else:
        st.info("Nothing here yet. Enter a topic above and choose Run research.")


def page_reports() -> None:
    st.markdown("## Reports")
    reports: List[ResearchRun] = st.session_state["reports"]

    if not reports:
        st.info("No reports yet. Run a research query on the Research page and it will appear here.")
        return

    search_q = st.text_input("Search by topic", "")
    filtered = [r for r in reports if search_q.lower() in r.topic.lower()] if search_q else reports
    st.caption(f"Showing {len(filtered)} of {len(reports)} report(s). Reports last until the session ends.")

    for run in filtered:
        with st.expander(f"{run.topic}  ·  {run.created_at}"):
            if run.error:
                html_block(status_text("Failed", "bad"))
                st.error(run.error)
            else:
                html_block(status_text("Completed", "ok"))
                html_block(
                    stats_strip([
                        ("Words", f"{run.word_count:,}"),
                        ("Reading time", f"{run.reading_minutes} min"),
                        ("Sources", str(len(run.sources))),
                        ("Duration", f"{run.execution_seconds:.1f}s"),
                    ])
                )
                with st.container(key=f"reading_list_{run.id}"):
                    st.markdown(run.report[:1200] + ("..." if len(run.report) > 1200 else ""))

            btn_cols = st.columns(4)
            with btn_cols[0]:
                if not run.error and st.button("Open full report", key=f"open_{run.id}", use_container_width=True):
                    st.session_state["current_run"] = run
                    go_to("Research")
            with btn_cols[1]:
                if not run.error:
                    st.download_button("Download .md", build_markdown_document(run),
                                       file_name=f"{run.file_stem}.md", mime="text/markdown",
                                       use_container_width=True, key=f"rep_md_{run.id}")
            with btn_cols[2]:
                if not run.error:
                    copy_button(run.report, "Copy report", key=f"rep_copy_{run.id}")
            with btn_cols[3]:
                if st.button("Delete", key=f"del_{run.id}", use_container_width=True):
                    st.session_state["reports"] = [r for r in reports if r.id != run.id]
                    cur = st.session_state.get("current_run")
                    if cur and cur.id == run.id:
                        st.session_state["current_run"] = None
                    st.rerun()


def page_workflow() -> None:
    st.markdown("## Workflow")
    st.markdown(f'<p class="wp-muted">How {esc(APP_NAME)} turns a topic into a reviewed report.</p>', unsafe_allow_html=True)

    steps = "".join(
        f'<div class="wp-rail-step"><div class="wp-pin">{i}</div><h3>{esc(name)} agent</h3>'
        f'<div class="wp-muted">{esc(desc)}</div>'
        f'<ul>{"".join(f"<li>{esc(p)}</li>" for p in points)}</ul></div>'
        for i, (name, desc, points) in enumerate(AGENTS, start=1)
    )
    html_block(f'<div class="wp-rail">{steps}</div>')
    st.caption("You enter a topic, the agents run in this order, and the final report arrives with the critic's review.")


def page_settings() -> None:
    st.markdown("## Settings")
    st.markdown("#### Appearance")
    col1, col2 = st.columns(2)
    with col1:
        theme = st.selectbox("Theme", ["Light", "Dark"], index=["Light", "Dark"].index(st.session_state["theme"]))
    with col2:
        font_size = st.selectbox("Text size", ["Small", "Medium", "Large"],
                                 index=["Small", "Medium", "Large"].index(st.session_state["font_size"]))
    animations = st.toggle("Animate the workflow line", value=st.session_state["animations"])

    if (theme, font_size, animations) != (
        st.session_state["theme"], st.session_state["font_size"], st.session_state["animations"]
    ):
        st.session_state["theme"] = theme
        st.session_state["font_size"] = font_size
        st.session_state["animations"] = animations
        st.rerun()

    st.markdown('<hr class="wp-hr">', unsafe_allow_html=True)
    st.markdown("#### Data")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Clear report history", use_container_width=True):
            st.session_state["reports"] = []
            st.session_state["current_run"] = None
            st.success("Report history cleared.")
    with col2:
        if st.button("Reset session", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()


def page_about() -> None:
    st.markdown(f"## About {APP_NAME}")
    st.markdown(
        f"{APP_NAME} is a multi-agent research assistant that automates the full research "
        "workflow. It searches trusted sources, extracts the relevant information, writes a "
        "comprehensive research report, and critically evaluates the result to improve quality."
    )

    st.markdown('<hr class="wp-hr">', unsafe_allow_html=True)
    st.markdown("#### Developer")

    col1, col2 = st.columns([1, 4])
    with col1:
        html_block('<div class="wp-avatar">PR</div>')
    with col2:
        st.markdown("**Piyush Raj**  \nAI & Machine Learning Developer")
        st.markdown(
            "I am passionate about Artificial Intelligence, Machine Learning, RAG, Large "
            "Language Models, and Multi-Agent Systems. I enjoy building intelligent "
            "applications that solve real-world problems using modern AI technologies."
        )
        html_block(
            """
            <div class="wp-links">
                <a href="https://github.com/Piyush-Raj-05" target="_blank">GitHub</a>
                <a href="https://www.linkedin.com/in/piyush-raj-b1a193297" target="_blank">LinkedIn</a>
                <a href="https://x.com/piyushrajankit" target="_blank">X (Twitter)</a>
                <a href="https://mail.google.com/mail/?view=cm&fs=1&to=piyushrajankit@gmail.com" target="_blank">Email</a>
            </div>
            """
        )


# ============================================================================
# MASTHEAD / NAVIGATION
# ============================================================================
def render_masthead() -> str:
    override = st.session_state.pop("_nav_override", None)
    if override in PAGES:
        st.session_state["nav_page"] = override

    brand, nav = st.columns([2, 5])
    with brand:
        html_block(f'<div class="wp-brand"><span class="wp-brand-name">{esc(APP_NAME)}<i></i></span></div>')
    with nav:
        selected = st.radio("Navigate", PAGES, horizontal=True, key="nav_page", label_visibility="collapsed")
    html_block('<hr class="wp-masthead-rule">')
    return selected


# ============================================================================
# MAIN
# ============================================================================
def main() -> None:
    st.set_page_config(page_title=f"{APP_NAME}: {TAGLINE}", page_icon="🧭", layout="wide",
                       initial_sidebar_state="collapsed")
    init_session_state()
    inject_css()

    page = render_masthead()

    if page == "Home":
        page_home()
    elif page == "Research":
        page_research()
    elif page == "Reports":
        page_reports()
    elif page == "Workflow":
        page_workflow()
    elif page == "Settings":
        page_settings()
    elif page == "About":
        page_about()


if __name__ == "__main__":
    main()