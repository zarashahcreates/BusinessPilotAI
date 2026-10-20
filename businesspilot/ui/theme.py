"""Visual theme: CSS and tiny HTML components. All user-supplied text is escaped before it reaches HTML."""
from __future__ import annotations

import html

import streamlit as st

CSS = """
<style>
:root { --navy:#0B1F3A; --blue:#2563EB; --teal:#0D9488; --slate:#475569; --line:#E2E8F0; --bg:#F8FAFC; }
.block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1180px; }
h1, h2, h3 { color: var(--navy); letter-spacing: -0.01em; }
[data-testid="stSidebar"] { background: var(--navy); }
[data-testid="stSidebar"] * { color: #E2E8F0; }
[data-testid="stSidebar"] .stRadio label p { font-size: 0.95rem; }
[data-testid="stSidebar"] input, [data-testid="stSidebar"] textarea { color: #0B1F3A !important; }
.bp-brand { font-size: 1.25rem; font-weight: 700; color: #fff; margin-bottom: .1rem; }
.bp-brand span { color: #60A5FA; }
.bp-tag { font-size: .78rem; color: #94A3B8; margin-bottom: 1rem; }
.bp-hero { background: linear-gradient(135deg, #0B1F3A 0%, #1E3A8A 100%); color: #fff; border-radius: 16px; padding: 2rem 2.2rem; margin-bottom: 1.2rem; }
.bp-hero h1 { color: #fff; font-size: 2rem; margin: 0 0 .4rem 0; }
.bp-hero p { color: #CBD5E1; font-size: 1.02rem; max-width: 640px; margin: 0; }
.bp-card { border: 1px solid var(--line); border-radius: 12px; padding: 1rem 1.1rem; background: #fff; height: 100%; }
.bp-card h4 { margin: 0 0 .3rem 0; color: var(--navy); font-size: 1rem; }
.bp-card p { margin: 0; color: var(--slate); font-size: .88rem; line-height: 1.45; }
.bp-step { display:inline-flex; align-items:center; justify-content:center; width:26px; height:26px; border-radius:50%; background: var(--blue); color:#fff; font-size:.8rem; font-weight:700; margin-bottom:.4rem; }
.bp-progress { display:flex; gap:.4rem; flex-wrap:wrap; margin: .2rem 0 1.2rem 0; }
.bp-pill { padding:.28rem .7rem; border-radius:999px; font-size:.8rem; border:1px solid var(--line); color: var(--slate); background:#fff; }
.bp-pill.done { background:#DCFCE7; border-color:#BBF7D0; color:#166534; }
.bp-pill.now { background: var(--blue); border-color: var(--blue); color:#fff; font-weight:600; }
.bp-badge { display:inline-block; padding:.08rem .5rem; border-radius:6px; font-size:.72rem; font-weight:600; margin-left:.4rem; vertical-align: middle; }
.bp-verified { background:#DCFCE7; color:#166534; } .bp-observed { background:#DBEAFE; color:#1E40AF; }
.bp-interpretation { background:#F3E8FF; color:#6B21A8; } .bp-forecast { background:#FEF3C7; color:#92400E; }
.bp-muted { color: var(--slate); font-size: .88rem; }
[data-testid="stMetric"] { background:#fff; border:1px solid var(--line); border-radius:12px; padding:.8rem 1rem; }
[data-testid="stMetricLabel"] p { color: var(--slate); font-size:.82rem; }
@media (max-width: 760px) { .bp-hero { padding: 1.3rem; } .bp-hero h1 { font-size: 1.5rem; } .block-container { padding-left: 1rem; padding-right: 1rem; } }
</style>
"""

STEPS = ["Upload", "Review", "Analyze", "Insights", "Report"]


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def esc(s: object) -> str:
    return html.escape(str(s))


def hero(title: str, text: str) -> None:
    st.markdown(f'<div class="bp-hero"><h1>{esc(title)}</h1><p>{esc(text)}</p></div>', unsafe_allow_html=True)


def card(title: str, text: str, step: int | None = None) -> None:
    badge = f'<div class="bp-step">{step}</div>' if step else ""
    st.markdown(f'<div class="bp-card">{badge}<h4>{esc(title)}</h4><p>{esc(text)}</p></div>', unsafe_allow_html=True)


def progress(current: str, done: set[str]) -> None:
    pills = []
    for s in STEPS:
        cls = "now" if s == current else ("done" if s in done else "")
        mark = "✓ " if s in done and s != current else ""
        pills.append(f'<span class="bp-pill {cls}">{mark}{s}</span>')
    st.markdown('<div class="bp-progress">' + "".join(pills) + "</div>", unsafe_allow_html=True)


def kind_badge(kind: str, label: str) -> str:
    return f'<span class="bp-badge bp-{kind}">{esc(label)}</span>'
