"""Streamlit UI for the AI Research Assistant (v3: dark glass redesign).

Same API contract as before: /auth/*, /sessions, /sessions/{id}/messages,
/sessions/{id}/chat, /tasks/{id}, /sessions/{id}/export and /dashboard.

What is new in this version
- Every colour is set explicitly, so the UI looks the same in browser light or dark mode.
- Animated login page with a scripted product preview.
- Chats no longer pile up as "New chat": an empty chat is reused, empty chats are hidden,
  and chats are titled from your first question.
- Animated confidence ring, typewriter answers, orbit empty state, SVG dashboard charts.
"""

import html
import json
import os
import time

import requests
import streamlit as st
import streamlit.components.v1 as components

API_BASE = os.getenv("API_BASE_URL") or ""

SUGGESTIONS = [
    ("travel_explore", "Summarize the current state of retrieval-augmented generation"),
    ("compare_arrows", "Compare LangGraph and CrewAI for multi-agent workflows"),
    ("article", "Write a final report on how LLM evaluation is done in production"),
]

# ---------------------------------------------------------------------------
# Inline SVG icons (stroke icons, 24x24 grid)
# ---------------------------------------------------------------------------

ICON_PATHS = {
    "sparkle": '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 16l.7 1.8L21.5 18.5l-1.8.7L19 21l-.7-1.8-1.8-.7 1.8-.7z"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
    "database": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
    "gauge": '<path d="M12 14l4-4"/><path d="M3.3 19a10 10 0 1 1 17.4 0"/>',
    "hub": '<circle cx="12" cy="5" r="2.5"/><circle cx="5" cy="18" r="2.5"/><circle cx="19" cy="18" r="2.5"/><path d="M11 7.3 6 15.8M13 7.3l5 8.5M7.5 18h9"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
    "lock": '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    "message": '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
    "chart": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    "bolt": '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    "layers": '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
}


def icon(name: str, size: int = 18) -> str:
    return (
        f'<svg class="ic" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true">{ICON_PATHS[name]}</svg>'
    )


# ---------------------------------------------------------------------------
# Global styling (all colours explicit, independent of the Streamlit theme)
# ---------------------------------------------------------------------------

STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700&family=Instrument+Sans:wght@400;500;600&display=swap');

:root {
  color-scheme: dark;
  --bg: #060A18;
  --panel: rgba(255,255,255,0.045);
  --panel-2: rgba(255,255,255,0.075);
  --line: rgba(255,255,255,0.10);
  --text: #E8EDFB;
  --muted: #93A0C4;
  --teal: #2DD4BF;
  --violet: #8B7CFF;
  --grad: linear-gradient(135deg, #2DD4BF 0%, #8B7CFF 100%);
}

html, body { background: var(--bg) !important; }

.stApp {
  color: var(--text) !important;
  font-family: 'Instrument Sans', system-ui, -apple-system, 'Segoe UI', sans-serif;
  background:
    radial-gradient(900px 600px at 12% -5%, rgba(45,212,191,0.20), transparent 60%),
    radial-gradient(800px 600px at 92% 0%, rgba(139,124,255,0.22), transparent 60%),
    radial-gradient(700px 500px at 60% 105%, rgba(45,212,191,0.12), transparent 60%),
    var(--bg) !important;
  background-size: 130% 130%, 130% 130%, 130% 130%, auto !important;
  animation: aurora 28s ease-in-out infinite alternate;
}
@keyframes aurora {
  from { background-position: 0% 0%, 100% 0%, 50% 100%, 0 0; }
  to   { background-position: 30% 20%, 70% 30%, 40% 80%, 0 0; }
}

#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
header[data-testid="stHeader"] { background: transparent !important; }
header[data-testid="stHeader"] button, [data-testid="stSidebarCollapseButton"] button,
[data-testid="stExpandSidebarButton"] { color: var(--text) !important; }

.stMainBlockContainer, .block-container { padding-top: 2rem; padding-bottom: 7rem; }

h1, h2, h3, h4 {
  font-family: 'Bricolage Grotesque', 'Instrument Sans', system-ui, sans-serif;
  color: #FFFFFF !important;
  letter-spacing: -0.02em;
  font-weight: 700;
}
a { color: var(--teal) !important; }
.ic { flex: 0 0 auto; }

*::-webkit-scrollbar { width: 8px; height: 8px; }
*::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.16); border-radius: 8px; }
button:focus-visible, input:focus-visible, textarea:focus-visible, summary:focus-visible {
  outline: 2px solid var(--teal) !important; outline-offset: 2px;
}

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"], [data-testid="stSidebar"] > div {
  background: linear-gradient(180deg, rgba(11,17,40,0.94), rgba(6,10,24,0.97)) !important;
}
[data-testid="stSidebar"] { border-right: 1px solid var(--line); }
[data-testid="stSidebarUserContent"] { padding-top: 0.6rem; }

.brand { display: flex; align-items: center; gap: 0.7rem; padding: 0.3rem 0.2rem 1.1rem; }
.brand-mark {
  width: 38px; height: 38px; border-radius: 12px; background: var(--grad);
  display: grid; place-items: center; color: #06121A;
  box-shadow: 0 8px 24px rgba(45,212,191,0.35);
}
.brand-name { font-family: 'Bricolage Grotesque', sans-serif; font-weight: 700; font-size: 1.12rem; line-height: 1.1; color: #FFFFFF; }
.brand-sub { font-size: 0.78rem; color: var(--muted); }
.side-label { font-size: 0.8rem; color: #6F7EA8; padding: 1.1rem 0.4rem 0.35rem; }

[data-testid="stSidebar"] .stButton > button {
  width: 100%;
  justify-content: flex-start !important;
  gap: 0.6rem;
  background: transparent !important;
  border: 1px solid transparent !important;
  border-radius: 12px;
  padding: 0.55rem 0.75rem;
  font-weight: 500;
  color: #C7D2F0 !important;
  box-shadow: none !important;
  transition: background 0.15s ease, border-color 0.15s ease;
}
[data-testid="stSidebar"] .stButton > button [data-testid="stMarkdownContainer"] { flex: 1; width: 100%; }
[data-testid="stSidebar"] .stButton > button p { text-align: left !important; color: inherit !important; }
[data-testid="stSidebar"] .stButton > button:hover { background: rgba(255,255,255,0.07) !important; }
[data-testid="stSidebar"] .stButton > button[kind="primary"],
[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"] {
  background: rgba(45,212,191,0.12) !important;
  border-color: rgba(45,212,191,0.38) !important;
  color: #FFFFFF !important;
}
[data-testid="stSidebar"] .st-key-new_chat button {
  background: var(--grad) !important;
  color: #06121A !important;
  justify-content: center !important;
  font-weight: 600;
  box-shadow: 0 10px 28px rgba(45,212,191,0.28) !important;
}
[data-testid="stSidebar"] .st-key-new_chat button:hover { filter: brightness(1.08); }
[data-testid="stSidebar"] .st-key-new_chat button [data-testid="stMarkdownContainer"] { flex: 0 1 auto; width: auto; }
[data-testid="stSidebar"] .st-key-new_chat button p { text-align: center !important; }

.userchip {
  display: flex; align-items: center; gap: 0.6rem; margin-top: 1rem;
  padding: 0.6rem 0.7rem; border-radius: 12px; background: var(--panel); border: 1px solid var(--line);
}
.userchip .av {
  width: 30px; height: 30px; border-radius: 50%; background: var(--grad); color: #06121A;
  display: grid; place-items: center; font-weight: 700; font-size: 0.85rem;
}
.userchip .em { font-size: 0.82rem; color: #C7D2F0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ---------- Buttons (main area) ---------- */
[data-testid="stMain"] .stButton > button,
.stDownloadButton > button,
button[data-testid="stPopoverButton"],
.stFormSubmitButton > button {
  border-radius: 12px;
  font-weight: 500;
  background: var(--panel-2) !important;
  border: 1px solid var(--line) !important;
  color: var(--text) !important;
  transition: border-color 0.15s ease, transform 0.15s ease, background 0.15s ease;
}
[data-testid="stMain"] .stButton > button:hover,
.stDownloadButton > button:hover,
button[data-testid="stPopoverButton"]:hover { border-color: rgba(45,212,191,0.6) !important; background: rgba(45,212,191,0.08) !important; }
[data-testid="stMain"] .stButton > button p, .stDownloadButton > button p { color: inherit !important; }
[data-testid="stMain"] .stButton > button[kind="primary"],
[data-testid="stMain"] .stButton > button[data-testid="stBaseButton-primary"],
.stFormSubmitButton > button[kind="primaryFormSubmit"],
.stFormSubmitButton > button[data-testid="stBaseButton-primaryFormSubmit"] {
  background: var(--grad) !important;
  border: 0 !important;
  color: #06121A !important;
  font-weight: 600;
  box-shadow: 0 10px 28px rgba(45,212,191,0.25);
}
.stFormSubmitButton > button p { color: #06121A !important; }

/* ---------- Inputs ---------- */
[data-testid="stTextInput"] div[data-baseweb="input"],
[data-testid="stTextInput"] div[data-baseweb="base-input"] { background: transparent !important; border: 0 !important; }
[data-testid="stTextInput"] input {
  background: rgba(255,255,255,0.05) !important;
  color: #FFFFFF !important;
  border: 1px solid rgba(255,255,255,0.14) !important;
  border-radius: 12px !important;
  padding: 0.8rem 0.95rem !important;
  -webkit-text-fill-color: #FFFFFF;
}
[data-testid="stTextInput"] input:focus {
  border-color: var(--teal) !important;
  box-shadow: 0 0 0 3px rgba(45,212,191,0.2) !important;
}
[data-testid="stTextInput"] button { background: transparent !important; color: var(--muted) !important; border: 0 !important; }
input::placeholder, textarea::placeholder { color: #6E7BA3 !important; opacity: 1; -webkit-text-fill-color: #6E7BA3; }
[data-testid="stForm"] { border: 0 !important; padding: 0 !important; background: transparent !important; }

.stTabs [data-baseweb="tab-list"] { gap: 0.4rem; border-bottom: 1px solid var(--line); }
.stTabs [data-baseweb="tab"] { color: var(--muted) !important; background: transparent !important; padding: 0.6rem 0.9rem; }
.stTabs [aria-selected="true"] { color: #FFFFFF !important; }
.stTabs [data-baseweb="tab-highlight"] { background: var(--grad) !important; height: 3px; border-radius: 3px; }
.stTabs [data-baseweb="tab-border"] { background: transparent !important; }

.st-key-auth_card {
  background: linear-gradient(160deg, rgba(255,255,255,0.075), rgba(255,255,255,0.03));
  border: 1px solid var(--line);
  border-radius: 24px;
  padding: 2rem 1.9rem 1.6rem;
  backdrop-filter: blur(18px);
  box-shadow: 0 30px 80px rgba(0,0,0,0.45);
}
.auth-mark {
  width: 46px; height: 46px; border-radius: 14px; background: var(--grad); color: #06121A;
  display: grid; place-items: center; margin-bottom: 1rem; box-shadow: 0 10px 30px rgba(45,212,191,0.35);
}
.auth-title { font-family: 'Bricolage Grotesque', sans-serif; font-size: 1.9rem; font-weight: 700; color: #FFFFFF; letter-spacing: -0.02em; }
.auth-sub { color: var(--muted); margin: 0.25rem 0 0.9rem; line-height: 1.5; }
.field-label { display: flex; align-items: center; gap: 0.5rem; font-weight: 600; font-size: 0.95rem; color: #FFFFFF; margin-top: 0.7rem; }
.field-label .ic { color: var(--teal); }
.field-hint { font-size: 0.82rem; color: var(--muted); margin: 0.1rem 0 0.35rem 1.65rem; }
.auth-foot { color: var(--muted); font-size: 0.82rem; margin-top: 0.9rem; line-height: 1.5; }

/* ---------- Chat ---------- */
.page-title { font-family: 'Bricolage Grotesque', sans-serif; font-size: 2rem; font-weight: 700; color: #FFFFFF; line-height: 1.1; letter-spacing: -0.02em; }
.page-sub { color: var(--muted); font-size: 0.95rem; margin: 0.3rem 0 1.4rem; }

[data-testid="stChatMessage"] {
  background: var(--panel) !important;
  border: 1px solid var(--line);
  border-left: 2px solid var(--teal);
  border-radius: 16px;
  padding: 1rem 1.3rem 1.1rem;
  margin-bottom: 1rem;
  max-width: 52rem;
  backdrop-filter: blur(10px);
}
[data-testid="stChatMessage"] [data-testid^="stChatMessageAvatar"],
[data-testid="stChatMessage"] [data-testid^="chatAvatarIcon"] { display: none; }
[data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li {
  color: var(--text) !important; font-size: 1rem; line-height: 1.7;
}
[data-testid="stChatMessage"] code { background: rgba(255,255,255,0.09); color: #BFF6EE; border-radius: 6px; padding: 0.1rem 0.35rem; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]),
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
  background: linear-gradient(135deg, rgba(45,212,191,0.16), rgba(139,124,255,0.18)) !important;
  border-left: 1px solid var(--line);
  border-color: rgba(139,124,255,0.35);
  margin-left: auto;
  max-width: 38rem;
}

.msg-head { display: flex; align-items: center; gap: 0.55rem; font-size: 0.85rem; font-weight: 600; color: #B8C4E6; margin-bottom: 0.35rem; }
.msg-badge { width: 26px; height: 26px; border-radius: 8px; display: grid; place-items: center; background: var(--grad); color: #06121A; }
.msg-badge.you { background: rgba(255,255,255,0.14); color: #FFFFFF; }

[data-testid="stBottom"], [data-testid="stBottom"] > div, [data-testid="stBottomBlockContainer"] { background: transparent !important; }
[data-testid="stBottom"] { background: linear-gradient(180deg, transparent, rgba(6,10,24,0.92) 45%) !important; }
[data-testid="stChatInput"] {
  background: rgba(255,255,255,0.07) !important;
  border: 1px solid rgba(255,255,255,0.16) !important;
  border-radius: 18px !important;
  backdrop-filter: blur(14px);
}
[data-testid="stChatInput"]:focus-within { border-color: var(--teal) !important; box-shadow: 0 0 0 3px rgba(45,212,191,0.18); }
[data-testid="stChatInput"] div { background: transparent !important; }
[data-testid="stChatInput"] textarea { color: #FFFFFF !important; -webkit-text-fill-color: #FFFFFF; }
[data-testid="stChatInput"] button { background: var(--grad) !important; color: #06121A !important; border-radius: 12px !important; }

/* Thinking indicator */
.think { display: flex; align-items: center; gap: 1rem; padding: 0.3rem 0 0.2rem; }
.think-orb { width: 34px; height: 34px; border-radius: 50%; background: var(--grad); animation: pulse 1.6s infinite; }
@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(45,212,191,0.5); }
  70% { box-shadow: 0 0 0 16px rgba(45,212,191,0); }
  100% { box-shadow: 0 0 0 0 rgba(45,212,191,0); }
}
.think-title { font-weight: 600; color: #FFFFFF; }
.think-sub { font-size: 0.85rem; color: var(--muted); }
.think-bar { height: 4px; width: 230px; border-radius: 99px; background: rgba(255,255,255,0.08); overflow: hidden; margin-top: 0.55rem; }
.think-bar i { display: block; height: 100%; width: 40%; border-radius: 99px; background: var(--grad); animation: slide 1.4s ease-in-out infinite; }
@keyframes slide { 0% { transform: translateX(-100%); } 100% { transform: translateX(260%); } }

/* Confidence ring */
.confcard { display: flex; align-items: center; gap: 1rem; margin-top: 0.9rem; padding: 0.75rem 1rem; border-radius: 14px; background: rgba(255,255,255,0.05); border: 1px solid var(--line); width: fit-content; max-width: 100%; }
.ring { position: relative; width: 64px; height: 64px; flex: 0 0 auto; }
.ring svg { width: 100%; height: 100%; transform: rotate(-90deg); }
.ring-bg { fill: none; stroke: rgba(255,255,255,0.10); stroke-width: 6; }
.ring-fg { fill: none; stroke-width: 6; stroke-linecap: round; stroke-dasharray: 163.36; animation: ring-in 1.3s cubic-bezier(.2,.7,.2,1) both; }
@keyframes ring-in { from { stroke-dashoffset: 163.36; } }
.ring-pct { position: absolute; inset: 0; display: grid; place-items: center; font-weight: 700; font-size: 0.92rem; color: #FFFFFF; }
.conf-title { font-weight: 600; color: #FFFFFF; }
.conf-sub { font-size: 0.85rem; color: var(--muted); }

.bd-row { display: grid; grid-template-columns: 11rem 1fr 3rem; gap: 0.8rem; align-items: center; padding: 0.4rem 0; font-size: 0.9rem; color: var(--text); }
.bd-track { height: 7px; border-radius: 99px; background: rgba(255,255,255,0.09); overflow: hidden; }
.bd-fill { height: 100%; border-radius: 99px; transform-origin: left; animation: grow 1s cubic-bezier(.2,.7,.2,1) both; }
@keyframes grow { from { transform: scaleX(0); } }
.bd-val { text-align: right; font-weight: 600; color: #FFFFFF; }

[data-testid="stExpander"] { background: var(--panel) !important; border: 1px solid var(--line) !important; border-radius: 14px !important; }
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary p { color: var(--text) !important; }
div[data-baseweb="popover"] > div, [data-testid="stPopoverBody"] {
  background: #0D1430 !important; border: 1px solid var(--line) !important; border-radius: 14px !important;
}
[data-testid="stPopoverBody"] *, [data-testid="stRadio"] label, [data-testid="stRadio"] p { color: var(--text) !important; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * { color: var(--muted) !important; }
[data-testid="stAlert"] { border-radius: 12px; }
hr { border-color: var(--line) !important; }

/* Empty state */
.empty { text-align: center; padding: 1.2rem 0 0.6rem; }
.empty-title { font-family: 'Bricolage Grotesque', sans-serif; font-size: 2.3rem; font-weight: 700; color: #FFFFFF; letter-spacing: -0.02em; }
.empty-sub { color: var(--muted); margin: 0.35rem auto 1.4rem; max-width: 30rem; line-height: 1.55; }
.orbit { position: relative; width: 190px; height: 190px; margin: 0 auto 1.1rem; }
.orbit::before, .orbit::after { content: ""; position: absolute; border-radius: 50%; border: 1px dashed rgba(255,255,255,0.14); }
.orbit::before { inset: 0; }
.orbit::after { inset: 30px; }
.orbit .core {
  position: absolute; inset: 62px; border-radius: 50%; background: var(--grad); color: #06121A;
  display: grid; place-items: center; box-shadow: 0 0 60px rgba(45,212,191,0.5);
}
.arm { position: absolute; inset: 0; animation: spin 16s linear infinite; }
.arm.a2 { inset: 30px; animation-duration: 11s; animation-direction: reverse; }
.arm.a3 { animation-delay: -8s; }
.sat {
  position: absolute; top: -17px; left: calc(50% - 17px); width: 34px; height: 34px; border-radius: 50%;
  background: #0E1734; border: 1px solid rgba(255,255,255,0.2); color: var(--teal); display: grid; place-items: center;
  animation: spin 16s linear infinite reverse;
}
.arm.a2 .sat { animation-duration: 11s; animation-direction: normal; color: var(--violet); }
.arm.a3 .sat { animation-delay: -8s; color: #F5B84B; }
@keyframes spin { to { transform: rotate(360deg); } }

[class*="st-key-sug_"] button {
  min-height: 118px; align-items: flex-start !important; justify-content: flex-start !important;
  text-align: left; padding: 1rem 1.1rem !important; border-radius: 16px !important; line-height: 1.4;
  background: var(--panel) !important; backdrop-filter: blur(10px);
}
[class*="st-key-sug_"] button:hover { transform: translateY(-3px); box-shadow: 0 16px 40px rgba(0,0,0,0.35); }
[class*="st-key-sug_"] button p { text-align: left !important; }

/* ---------- Dashboard ---------- */
.stat { padding: 1.1rem 1.2rem; border-radius: 18px; background: var(--panel); border: 1px solid var(--line); backdrop-filter: blur(10px); height: 100%; }
.stat-top { display: flex; align-items: center; justify-content: space-between; }
.stat-icon { width: 38px; height: 38px; border-radius: 11px; display: grid; place-items: center; background: rgba(45,212,191,0.12); color: var(--teal); }
.stat-icon.v { background: rgba(139,124,255,0.15); color: var(--violet); }
.stat-icon.a { background: rgba(245,184,75,0.14); color: #F5B84B; }
.stat-num { font-family: 'Bricolage Grotesque', sans-serif; font-size: 2.3rem; font-weight: 700; color: #FFFFFF; line-height: 1.1; margin-top: 0.8rem; }
.stat-lbl { color: var(--muted); font-size: 0.9rem; }
.stat .ring { width: 58px; height: 58px; }
.panel { padding: 1.2rem 1.3rem; border-radius: 18px; background: var(--panel); border: 1px solid var(--line); backdrop-filter: blur(10px); margin-top: 1rem; }
.panel-title { font-family: 'Bricolage Grotesque', sans-serif; font-size: 1.2rem; font-weight: 700; color: #FFFFFF; margin-bottom: 0.7rem; }
.trend { width: 100%; height: auto; display: block; }
.trend .draw { stroke-dasharray: 1; stroke-dashoffset: 1; animation: draw 1.8s ease forwards; }
@keyframes draw { to { stroke-dashoffset: 0; } }
.tablewrap { overflow-x: auto; }
.runs { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
.runs th { color: var(--muted); font-weight: 500; text-align: left; padding: 0.6rem 0.8rem; border-bottom: 1px solid var(--line); white-space: nowrap; }
.runs td { padding: 0.7rem 0.8rem; border-bottom: 1px solid rgba(255,255,255,0.05); color: var(--text); }
.runs tr:hover td { background: rgba(255,255,255,0.03); }
.mini { display: flex; align-items: center; gap: 0.6rem; min-width: 9rem; }
.mini .bd-track { flex: 1; height: 6px; }
.mini b { font-weight: 600; color: #FFFFFF; width: 2.6rem; text-align: right; }

@media (max-width: 640px) {
  .bd-row { grid-template-columns: 7rem 1fr 2.6rem; }
  .empty-title { font-size: 1.8rem; }
}
@media (prefers-reduced-motion: reduce) {
  .stApp { animation: none; }
  .arm, .sat, .think-orb, .think-bar i, .ring-fg, .bd-fill, .trend .draw { animation: none !important; }
  .trend .draw { stroke-dashoffset: 0; }
}
</style>
"""

# ---------------------------------------------------------------------------
# Login showcase (rendered in an iframe so it can run JS animation)
# ---------------------------------------------------------------------------

LOGIN_SHOWCASE = r"""
<!doctype html>
<html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700&family=Instrument+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;background:transparent;color:#E8EDFB;font-family:'Instrument Sans',system-ui,sans-serif;overflow:hidden}
.stage{position:relative;height:100%;border-radius:26px;overflow:hidden;padding:30px 32px 24px;display:flex;flex-direction:column;gap:16px;
  background:linear-gradient(155deg,rgba(21,32,70,.85),rgba(7,11,26,.92));border:1px solid rgba(255,255,255,.10);box-shadow:0 30px 80px rgba(0,0,0,.45)}
canvas{position:absolute;inset:0;width:100%;height:100%;z-index:0}
.stage>*:not(canvas){position:relative;z-index:1}
.brand{display:flex;align-items:center;gap:10px;font-family:'Bricolage Grotesque',sans-serif;font-weight:700;font-size:18px}
.logo{width:34px;height:34px;border-radius:11px;background:linear-gradient(135deg,#2DD4BF,#8B7CFF);display:grid;place-items:center;color:#06121A;box-shadow:0 8px 24px rgba(45,212,191,.35)}
h1{font-family:'Bricolage Grotesque',sans-serif;font-weight:700;font-size:40px;line-height:1.04;letter-spacing:-.025em;color:#fff;max-width:560px}
.sub{color:#9BA8CB;font-size:15px;line-height:1.55;max-width:500px}
.win{flex:1;min-height:290px;border-radius:16px;background:rgba(9,14,32,.82);border:1px solid rgba(255,255,255,.12);
  box-shadow:0 30px 70px rgba(0,0,0,.5);display:flex;flex-direction:column;overflow:hidden;
  transform:perspective(1400px) rotateY(-4deg) rotateX(2deg);animation:float 7s ease-in-out infinite}
@keyframes float{50%{transform:perspective(1400px) rotateY(-4deg) rotateX(2deg) translateY(-8px)}}
.bar{display:flex;align-items:center;gap:7px;padding:11px 14px;border-bottom:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.03)}
.bar i{width:10px;height:10px;border-radius:50%;background:#3A4670}
.bar i:nth-child(1){background:#FF6B7A}.bar i:nth-child(2){background:#F5B84B}.bar i:nth-child(3){background:#34D399}
.url{margin-left:10px;font-size:12px;color:#8391B8;background:rgba(255,255,255,.05);padding:4px 12px;border-radius:99px}
.tag{margin-left:auto;font-size:11px;color:#8391B8}
.body{flex:1;padding:16px 18px;display:flex;flex-direction:column;gap:12px;overflow:hidden}
.q{align-self:flex-end;max-width:82%;padding:10px 14px;border-radius:14px;font-size:14px;line-height:1.45;color:#fff;min-height:40px;
  background:linear-gradient(135deg,rgba(45,212,191,.18),rgba(139,124,255,.22));border:1px solid rgba(139,124,255,.4)}
.pipe{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.node{display:flex;align-items:center;gap:7px;padding:5px 11px 5px 6px;border-radius:99px;font-size:12px;font-weight:600;color:#6F7EA8;
  background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);transition:all .3s}
.node .d{width:20px;height:20px;border-radius:50%;display:grid;place-items:center;background:rgba(255,255,255,.07)}
.node.active{color:#fff;border-color:#2DD4BF;box-shadow:0 0 0 4px rgba(45,212,191,.16)}
.node.active .d{background:#2DD4BF;color:#06121A;animation:blink 1s infinite}
.node.done{color:#BFF6EE;border-color:rgba(45,212,191,.35)}
.node.done .d{background:rgba(45,212,191,.2);color:#2DD4BF}
@keyframes blink{50%{opacity:.45}}
.link{width:10px;height:1px;background:rgba(255,255,255,.18)}
.ans{opacity:0;transition:opacity .4s;font-size:13.5px;line-height:1.6;color:#DCE4F8}
.ans.show{opacity:1}
.ans b{display:flex;align-items:center;gap:7px;font-size:12px;color:#B8C4E6;margin-bottom:5px;font-weight:600}
.ans b span{width:20px;height:20px;border-radius:6px;background:linear-gradient(135deg,#2DD4BF,#8B7CFF);display:grid;place-items:center;color:#06121A}
.caret{display:inline-block;width:7px;height:14px;background:#2DD4BF;margin-left:2px;vertical-align:-2px;animation:blink 1s infinite}
.score{display:flex;align-items:center;gap:12px;opacity:0;transition:opacity .5s;padding:9px 12px;border-radius:12px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);width:fit-content}
.score.show{opacity:1}
.ringw{position:relative;width:48px;height:48px}
.ringw svg{width:100%;height:100%;transform:rotate(-90deg)}
.ringw .bg{fill:none;stroke:rgba(255,255,255,.1);stroke-width:6}
.ringw .fg{fill:none;stroke:#34D399;stroke-width:6;stroke-linecap:round;stroke-dasharray:163.36;stroke-dashoffset:163.36;transition:stroke-dashoffset 1.4s cubic-bezier(.2,.7,.2,1)}
.ringw span{position:absolute;inset:0;display:grid;place-items:center;font-size:12px;font-weight:700;color:#fff}
.score strong{display:block;font-size:13px;color:#fff}
.score small{font-size:12px;color:#8FA0C8}
.chips{display:flex;gap:8px;flex-wrap:wrap}
.chip{display:flex;align-items:center;gap:6px;padding:6px 12px;border-radius:99px;font-size:12.5px;color:#C7D2F0;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1)}
.chip svg{color:#2DD4BF}
@media (prefers-reduced-motion:reduce){.win{animation:none}}
</style></head>
<body>
<div class="stage">
  <canvas id="bg"></canvas>
  <div class="brand"><div class="logo"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="5" r="2.5"/><circle cx="5" cy="18" r="2.5"/><circle cx="19" cy="18" r="2.5"/><path d="M11 7.3 6 15.8M13 7.3l5 8.5M7.5 18h9"/></svg></div>AI Research Assistant</div>
  <div>
    <h1>Research that shows how sure it is.</h1>
    <p class="sub" style="margin-top:10px">Ask a question. A team of agents searches the web, checks your earlier chat and writes a report with a confidence score you can act on.</p>
  </div>
  <div class="win">
    <div class="bar"><i></i><i></i><i></i><span class="url">research-assistant / new chat</span><span class="tag">Preview</span></div>
    <div class="body">
      <div class="q" id="q"></div>
      <div class="pipe" id="pipe">
        <div class="node"><span class="d"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16M4 12h10M4 18h6"/></svg></span>Plan</div><span class="link"></span>
        <div class="node"><span class="d"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg></span>Search</div><span class="link"></span>
        <div class="node"><span class="d"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/></svg></span>Memory</div><span class="link"></span>
        <div class="node"><span class="d"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg></span>Write</div><span class="link"></span>
        <div class="node"><span class="d"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 14l4-4"/><path d="M3.3 19a10 10 0 1 1 17.4 0"/></svg></span>Score</div>
      </div>
      <div class="ans" id="ans"><b><span><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/></svg></span>Research assistant</b><span id="a"></span><i class="caret" id="caret"></i></div>
      <div class="score" id="score">
        <div class="ringw"><svg viewBox="0 0 64 64"><circle class="bg" cx="32" cy="32" r="26"/><circle class="fg" id="fg" cx="32" cy="32" r="26"/></svg><span id="pct">0%</span></div>
        <div><strong>High confidence</strong><small>Well supported by the sources it found.</small></div>
      </div>
    </div>
  </div>
  <div class="chips">
    <span class="chip"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="5" r="2.5"/><circle cx="5" cy="18" r="2.5"/><circle cx="19" cy="18" r="2.5"/><path d="M11 7.3 6 15.8M13 7.3l5 8.5M7.5 18h9"/></svg>LangGraph agents</span>
    <span class="chip"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>MCP web search</span>
    <span class="chip"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/></svg>Session memory</span>
    <span class="chip"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 14l4-4"/><path d="M3.3 19a10 10 0 1 1 17.4 0"/></svg>Confidence scores</span>
  </div>
</div>
<script>
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const Q="How does LangGraph manage state between agents?";
const A="LangGraph models a workflow as a graph. Each node is a function that reads a shared state and returns updates to it, and edges decide which node runs next, including conditional routes. A checkpointer saves that state after every step, so a run can pause, resume or branch.";
const qEl=document.getElementById('q'),aEl=document.getElementById('a'),ans=document.getElementById('ans'),
      score=document.getElementById('score'),fg=document.getElementById('fg'),pct=document.getElementById('pct'),
      caret=document.getElementById('caret'),nodes=[...document.querySelectorAll('.node')];
const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
const C=163.36;
async function typeInto(el,text,ms){el.textContent='';for(const ch of text){el.textContent+=ch;await sleep(ms)}}
function setScore(v){fg.style.strokeDashoffset=C*(1-v/100);pct.textContent=Math.round(v)+'%'}
async function countUp(to){setScore(0);await sleep(60);fg.style.strokeDashoffset=C*(1-to/100);
  const t0=performance.now();await new Promise(res=>{(function f(t){const p=Math.min(1,(t-t0)/1400);pct.textContent=Math.round(to*p)+'%';p<1?requestAnimationFrame(f):res()})(t0)})}
function reset(){qEl.textContent='';aEl.textContent='';ans.classList.remove('show');score.classList.remove('show');caret.style.display='inline-block';
  nodes.forEach(n=>n.classList.remove('active','done'));setScore(0)}
async function loop(){
  while(true){
    reset();await sleep(700);
    await typeInto(qEl,Q,34);await sleep(400);
    for(const n of nodes){n.classList.add('active');await sleep(800);n.classList.remove('active');n.classList.add('done')}
    ans.classList.add('show');await typeInto(aEl,A,13);caret.style.display='none';await sleep(300);
    score.classList.add('show');await countUp(87);await sleep(5200);
  }
}
if(reduce){qEl.textContent=Q;nodes.forEach(n=>n.classList.add('done'));aEl.textContent=A;caret.style.display='none';ans.classList.add('show');score.classList.add('show');setScore(87)}
else loop();

const cv=document.getElementById('bg'),cx=cv.getContext('2d');let W,H,pts=[];
function size(){const r=window.devicePixelRatio||1;W=cv.clientWidth;H=cv.clientHeight;cv.width=W*r;cv.height=H*r;cx.setTransform(r,0,0,r,0,0);
  const n=Math.max(18,Math.round(W*H/17000));
  pts=Array.from({length:n},()=>({x:Math.random()*W,y:Math.random()*H,vx:(Math.random()-.5)*.28,vy:(Math.random()-.5)*.28,r:Math.random()*1.6+.7,c:Math.random()<.5?'45,212,191':'139,124,255'}))}
function draw(){cx.clearRect(0,0,W,H);
  for(const p of pts){p.x+=p.vx;p.y+=p.vy;if(p.x<0||p.x>W)p.vx*=-1;if(p.y<0||p.y>H)p.vy*=-1}
  for(let i=0;i<pts.length;i++)for(let j=i+1;j<pts.length;j++){const a=pts[i],b=pts[j],d=Math.hypot(a.x-b.x,a.y-b.y);
    if(d<130){cx.strokeStyle='rgba('+a.c+','+((1-d/130)*.3)+')';cx.lineWidth=1;cx.beginPath();cx.moveTo(a.x,a.y);cx.lineTo(b.x,b.y);cx.stroke()}}
  for(const p of pts){cx.fillStyle='rgba('+p.c+',.85)';cx.beginPath();cx.arc(p.x,p.y,p.r,0,7);cx.fill()}
  if(!reduce)requestAnimationFrame(draw)}
size();draw();addEventListener('resize',size);
</script>
</body></html>
"""

THINKING_HTML = (
    '<div class="think"><div class="think-orb"></div><div>'
    '<div class="think-title">Researching your question</div>'
    '<div class="think-sub">Searching, reading and writing your report. This can take a minute.</div>'
    '<div class="think-bar"><i></i></div></div></div>'
)


# ---------------------------------------------------------------------------
# API helpers (unchanged behaviour)
# ---------------------------------------------------------------------------


def _resolve_api_base() -> str:
    if API_BASE:
        return API_BASE.rstrip("/")
    for base in ("http://127.0.0.1:8000", "http://localhost:8000", "http://localhost:80"):
        try:
            resp = requests.get(f"{base}/openapi.json", timeout=1.5)
            if resp.ok and "/auth/register" in resp.text:
                return base
        except requests.RequestException:
            continue
    return "http://localhost:80"


def api_base() -> str:
    return _resolve_api_base()


def api_headers() -> dict:
    token = st.session_state.get("token")
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def api_post(path: str, json_body: dict | None = None):
    return requests.post(f"{api_base()}{path}", json=json_body, headers=api_headers(), timeout=60)


def api_get(path: str):
    return requests.get(f"{api_base()}{path}", headers=api_headers(), timeout=60)


def error_detail(resp: requests.Response) -> str:
    try:
        data = resp.json()
        detail = data.get("detail", data)
        if isinstance(detail, list):
            parts = []
            for item in detail:
                if isinstance(item, dict):
                    parts.append(item.get("msg") or str(item))
                else:
                    parts.append(str(item))
            return "; ".join(parts) or f"HTTP {resp.status_code}"
        return str(detail)
    except Exception:
        text = (resp.text or "").strip()
        if "Not Found" in text:
            return (
                f"API route not found ({resp.status_code} {resp.request.method} {resp.url}). "
                "Rebuild and restart the API containers so /auth/register is available."
            )
        return text or f"HTTP {resp.status_code}"


def poll_task(task_id: str, max_wait: int = 300) -> dict | None:
    started = time.time()
    while time.time() - started < max_wait:
        resp = api_get(f"/tasks/{task_id}")
        if resp.status_code != 200:
            st.error(error_detail(resp))
            return None
        data = resp.json()
        if data.get("status") in ("success", "failed"):
            return data
        time.sleep(2)
    st.warning("The assistant took too long to respond. Try again in a moment.")
    return None


def render_showcase() -> None:
    """Animated login preview. Uses st.iframe on new Streamlit, components.html on older ones."""
    if hasattr(st, "iframe"):
        st.iframe(LOGIN_SHOWCASE, height=730)
    else:
        components.html(LOGIN_SHOWCASE, height=730, scrolling=False)


def set_content_width(rem: int) -> None:
    st.markdown(
        f"<style>.stMainBlockContainer,.block-container{{max-width:{rem}rem !important}}</style>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Confidence rendering
# ---------------------------------------------------------------------------

RING_C = 163.36  # circumference for r=26


def _to_ratio(value) -> float | None:
    if isinstance(value, (bool, dict, list)) or value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v > 1:
        v = v / 100
    return max(0.0, min(1.0, v))


def confidence_tier(ratio: float) -> tuple[str, str, str]:
    """Return (label, colour, one-line meaning)."""
    if ratio >= 0.75:
        return "High", "#34D399", "Well supported by the sources it found."
    if ratio >= 0.5:
        return "Moderate", "#F5B84B", "Partly supported. Worth checking the key claims."
    return "Low", "#FF6B7A", "Weakly supported. Verify before you rely on it."


def ring_html(ratio: float, color: str) -> str:
    offset = RING_C * (1 - ratio)
    pct = round(ratio * 100)
    return (
        '<div class="ring"><svg viewBox="0 0 64 64">'
        '<circle class="ring-bg" cx="32" cy="32" r="26"/>'
        f'<circle class="ring-fg" cx="32" cy="32" r="26" style="stroke:{color};stroke-dashoffset:{offset:.2f}"/>'
        f'</svg><span class="ring-pct">{pct}%</span></div>'
    )


def confidence_html(score, source_count=None) -> str:
    ratio = _to_ratio(score)
    if ratio is None:
        return ""
    label, color, meaning = confidence_tier(ratio)
    if source_count is not None:
        meaning = f"{meaning} Grounded in {int(source_count)} source(s)."
    return (
        '<div class="confcard">'
        f"{ring_html(ratio, color)}"
        f'<div><div class="conf-title">{label} confidence</div><div class="conf-sub">{meaning}</div></div>'
        "</div>"
    )


def render_breakdown(breakdown) -> None:
    if not isinstance(breakdown, dict) or not breakdown:
        return
    rows = []
    extras = {}
    for key, val in breakdown.items():
        ratio = _to_ratio(val)
        if ratio is None:
            extras[key] = val
            continue
        _, color, _ = confidence_tier(ratio)
        pct = round(ratio * 100)
        name = html.escape(str(key).replace("_", " ").capitalize())
        rows.append(
            f'<div class="bd-row"><span>{name}</span>'
            f'<div class="bd-track"><div class="bd-fill" style="width:{pct}%;background:{color}"></div></div>'
            f'<span class="bd-val">{pct}%</span></div>'
        )
    if rows:
        st.markdown("".join(rows), unsafe_allow_html=True)
    if extras:
        st.json(extras)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def _authenticate(path: str, email: str, password: str) -> None:
    if not email or not password:
        st.error("Enter both your email and password.")
        return
    try:
        resp = api_post(path, {"email": email, "password": password})
    except requests.RequestException as exc:
        st.error(f"Can't reach the API at {api_base()}. {exc}")
        return
    if resp.status_code == 200:
        payload = resp.json()
        st.session_state.token = payload["access_token"]
        st.session_state.user = payload["user"]
        st.session_state.page = "chat"
        st.rerun()
    else:
        st.error(error_detail(resp))


def field_label(icon_name: str, label: str, hint: str) -> None:
    st.markdown(
        f'<div class="field-label">{icon(icon_name, 17)}<span>{html.escape(label)}</span></div>'
        f'<div class="field-hint">{html.escape(hint)}</div>',
        unsafe_allow_html=True,
    )


def login_screen():
    set_content_width(80)
    left, right = st.columns([1.35, 1], gap="large")

    with left:
        render_showcase()

    with right:
        with st.container(key="auth_card"):
            st.markdown(
                f'<div class="auth-mark">{icon("sparkle", 24)}</div>'
                '<div class="auth-title">Welcome</div>'
                '<div class="auth-sub">Sign in to pick up your research chats, or create an account to start.</div>',
                unsafe_allow_html=True,
            )
            tab_login, tab_register = st.tabs(["Sign in", "Create account"])

            with tab_login:
                with st.form("login_form"):
                    field_label("mail", "Email address", "The email you registered with.")
                    email = st.text_input(
                        "Email", key="login_email", placeholder="you@company.com", label_visibility="collapsed"
                    )
                    field_label("lock", "Password", "Your account password.")
                    password = st.text_input(
                        "Password",
                        type="password",
                        key="login_password",
                        placeholder="Enter your password",
                        label_visibility="collapsed",
                    )
                    submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
                if submitted:
                    _authenticate("/auth/login", email, password)

            with tab_register:
                with st.form("register_form"):
                    field_label("mail", "Email address", "Used to sign in and to keep your chats.")
                    email = st.text_input(
                        "Email", key="reg_email", placeholder="you@company.com", label_visibility="collapsed"
                    )
                    field_label("lock", "Password", "Choose something you don't use elsewhere.")
                    password = st.text_input(
                        "Password",
                        type="password",
                        key="reg_password",
                        placeholder="Create a password",
                        label_visibility="collapsed",
                    )
                    submitted = st.form_submit_button("Create account", type="primary", use_container_width=True)
                if submitted:
                    _authenticate("/auth/register", email, password)

            st.markdown(
                '<div class="auth-foot">Every report comes with a confidence score, '
                "so you can see how well it is supported.</div>",
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# Sessions (no more duplicate "New chat" entries)
# ---------------------------------------------------------------------------


def load_sessions() -> list:
    resp = api_get("/sessions")
    if resp.status_code != 200:
        return []
    sessions = resp.json()
    # Newest first when the API exposes a timestamp; otherwise keep the API order.
    return sorted(sessions, key=lambda s: s.get("updated_at") or s.get("created_at") or "", reverse=True)


def session_meta(session_id: str) -> dict:
    """Message count and first question for a session, cached per browser session."""
    cache = st.session_state.setdefault("session_meta", {})
    if session_id in cache:
        return cache[session_id]
    resp = api_get(f"/sessions/{session_id}/messages")
    if resp.status_code != 200:
        return {"count": None, "title": None}
    msgs = resp.json()
    first_user = next((m.get("content") for m in msgs if m.get("role") == "user"), None)
    cache[session_id] = {"count": len(msgs), "title": first_user}
    return cache[session_id]


def invalidate_meta(session_id: str) -> None:
    st.session_state.get("session_meta", {}).pop(session_id, None)


def create_session() -> str | None:
    resp = api_post("/sessions", {"title": "New chat"})
    if resp.status_code == 200:
        new_id = resp.json()["id"]
        st.session_state.setdefault("session_meta", {})[new_id] = {"count": 0, "title": None}
        return new_id
    st.error(error_detail(resp))
    return None


def ensure_session(sessions: list) -> bool:
    """Pick an active session. Reuse an empty chat before creating a new one.

    Returns True when a new session was created (so the caller reloads the list).
    """
    if st.session_state.get("active_session_id"):
        return False
    for s in sessions:
        if session_meta(s["id"]).get("count") == 0:
            st.session_state.active_session_id = s["id"]
            return False
    new_id = create_session()
    if new_id:
        st.session_state.active_session_id = new_id
        return True
    return False


def session_label(s: dict) -> str:
    meta = session_meta(s["id"])
    if meta.get("count") == 0:
        return "New chat"
    label = meta.get("title") or s.get("title") or "Chat"
    if s.get("title") and s["title"] != "New chat":
        label = s["title"]
    label = " ".join(str(label).split())
    return label if len(label) <= 32 else label[:31] + "…"


def render_sidebar(sessions: list, current_page: str) -> None:
    sb = st.sidebar
    sb.markdown(
        f'<div class="brand"><div class="brand-mark">{icon("hub", 20)}</div>'
        '<div><div class="brand-name">AI Research</div><div class="brand-sub">Assistant</div></div></div>',
        unsafe_allow_html=True,
    )

    active_id = st.session_state.get("active_session_id")
    if sb.button("New chat", key="new_chat", icon=":material/add:", use_container_width=True):
        if active_id and session_meta(active_id).get("count") == 0:
            # Already in a blank chat: don't create another one.
            st.session_state.page = "chat"
            st.rerun()
        new_id = create_session()
        if new_id:
            st.session_state.active_session_id = new_id
            st.session_state.page = "chat"
            st.rerun()

    visible = [
        s for s in sessions if s["id"] == active_id or session_meta(s["id"]).get("count") != 0
    ][:25]
    if visible:
        sb.markdown('<div class="side-label">Your chats</div>', unsafe_allow_html=True)
    for s in visible:
        is_active = current_page == "chat" and s["id"] == active_id
        if sb.button(
            session_label(s),
            key=f"sess_{s['id']}",
            icon=":material/chat_bubble:",
            type="primary" if is_active else "secondary",
            use_container_width=True,
        ):
            st.session_state.active_session_id = s["id"]
            st.session_state.page = "chat"
            st.rerun()

    sb.markdown('<div class="side-label">Workspace</div>', unsafe_allow_html=True)
    if sb.button(
        "Dashboard",
        key="nav_dashboard",
        icon=":material/bar_chart:",
        type="primary" if current_page == "dashboard" else "secondary",
        use_container_width=True,
    ):
        st.session_state.page = "dashboard"
        st.rerun()
    if sb.button("Log out", key="nav_logout", icon=":material/logout:", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    email = st.session_state.get("user", {}).get("email")
    if email:
        sb.markdown(
            f'<div class="userchip"><span class="av">{html.escape(email[:1].upper())}</span>'
            f'<span class="em">{html.escape(email)}</span></div>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


def msg_head(role: str) -> str:
    if role == "user":
        return f'<div class="msg-head"><span class="msg-badge you">{icon("user", 14)}</span>You</div>'
    return f'<div class="msg-head"><span class="msg-badge">{icon("sparkle", 14)}</span>Research assistant</div>'


def render_message(role: str, content: str, confidence=None) -> None:
    with st.chat_message(role):
        st.markdown(msg_head(role), unsafe_allow_html=True)
        st.markdown(content)
        if confidence is not None:
            st.markdown(confidence_html(confidence), unsafe_allow_html=True)


def export_menu(session_id: str) -> None:
    with st.popover("Export", icon=":material/ios_share:"):
        fmt = st.radio("Chat format", ["Markdown", "JSON"], horizontal=True, key="export_fmt")
        if st.button("Prepare chat file", key="prepare_export"):
            api_fmt = "md" if fmt == "Markdown" else "json"
            exp = api_get(f"/sessions/{session_id}/export?format={api_fmt}")
            if exp.status_code == 200:
                st.session_state.export = {"session_id": session_id, "fmt": fmt, "body": exp.json()}
            else:
                st.error(error_detail(exp))

        export = st.session_state.get("export")
        if export and export["session_id"] == session_id and export["fmt"] == fmt:
            body = export["body"]
            st.download_button(
                f"Save {body['filename']}",
                data=body["content"],
                file_name=body["filename"],
                mime=body["media_type"],
                key="save_export",
                icon=":material/download:",
            )

        report = st.session_state.get("last_report")
        if report and report["session_id"] == session_id:
            payload = report["payload"]
            st.divider()
            st.caption("Latest report")
            st.download_button(
                "Save report (.md)",
                data=payload.get("summary", ""),
                file_name="research_report.md",
                mime="text/markdown",
                key="save_report_md",
                icon=":material/download:",
            )
            st.download_button(
                "Save report (.json)",
                data=json.dumps(payload, indent=2, default=str),
                file_name="research_report.json",
                mime="application/json",
                key="save_report_json",
                icon=":material/download:",
            )


def empty_state() -> None:
    st.markdown(
        '<div class="empty"><div class="orbit">'
        f'<div class="core">{icon("sparkle", 30)}</div>'
        f'<div class="arm a1"><div class="sat">{icon("search", 16)}</div></div>'
        f'<div class="arm a2"><div class="sat">{icon("database", 16)}</div></div>'
        f'<div class="arm a3"><div class="sat">{icon("gauge", 16)}</div></div>'
        "</div>"
        '<div class="empty-title">What do you want to research?</div>'
        '<div class="empty-sub">Ask anything. The assistant searches the web, checks your earlier '
        "questions and scores its own report.</div></div>",
        unsafe_allow_html=True,
    )
    cols = st.columns(len(SUGGESTIONS))
    for i, (col, (ic, text)) in enumerate(zip(cols, SUGGESTIONS)):
        with col:
            if st.button(text, key=f"sug_{i}", icon=f":material/{ic}:", use_container_width=True):
                st.session_state.pending_prompt = text
                st.rerun()


def _typewriter(text: str):
    tokens = text.split(" ")
    delay = min(0.03, 3.0 / max(len(tokens), 1))
    for i, tok in enumerate(tokens):
        yield tok + (" " if i < len(tokens) - 1 else "")
        time.sleep(delay)


def run_research(session_id: str, prompt: str) -> None:
    render_message("user", prompt)
    with st.chat_message("assistant"):
        st.markdown(msg_head("assistant"), unsafe_allow_html=True)
        holder = st.empty()
        holder.markdown(THINKING_HTML, unsafe_allow_html=True)

        resp = api_post(f"/sessions/{session_id}/chat", {"prompt": prompt})
        if resp.status_code != 200:
            holder.empty()
            st.error(error_detail(resp))
            return
        result = poll_task(resp.json()["task_id"])
        holder.empty()
        if not result:
            return
        if result.get("status") == "failed":
            st.error(result.get("error") or "The task failed without an error message.")
            return

        payload = result.get("result") or {}
        answer = payload.get("summary", "")
        if answer:
            st.write_stream(_typewriter(answer))
        conf = payload.get("confidence_score")
        sources = payload.get("sources") or []
        if conf is not None:
            st.markdown(confidence_html(conf, len(sources) if sources else None), unsafe_allow_html=True)

    st.session_state.last_report = {"session_id": session_id, "payload": payload}
    invalidate_meta(session_id)
    time.sleep(1.2)  # let the confidence ring finish before the page refreshes
    st.rerun()


def chat_page():
    set_content_width(62)
    sessions = load_sessions()
    if ensure_session(sessions):
        sessions = load_sessions()
    render_sidebar(sessions, "chat")

    session_id = st.session_state.get("active_session_id")
    if not session_id:
        st.warning("Couldn't start a chat session. Check that the API is running, then select New chat.")
        return

    active = next((s for s in sessions if s.get("id") == session_id), {})
    meta = session_meta(session_id)
    title = "New chat" if meta.get("count") == 0 else (meta.get("title") or active.get("title") or "Chat")
    title = " ".join(str(title).split())
    if len(title) > 70:
        title = title[:69] + "…"

    head, tools = st.columns([5, 1])
    with head:
        st.markdown(
            f'<div class="page-title">{html.escape(title)}</div>'
            '<div class="page-sub">Research answers include evidence-derived confidence when sources support it.</div>',
            unsafe_allow_html=True,
        )
    with tools:
        export_menu(session_id)

    prompt = st.chat_input("Ask a research question or request a final report")
    if not prompt:
        prompt = st.session_state.pop("pending_prompt", None)

    messages_resp = api_get(f"/sessions/{session_id}/messages")
    messages = messages_resp.json() if messages_resp.status_code == 200 else []

    if not messages and not prompt:
        empty_state()

    for m in messages:
        render_message(m["role"], m["content"], m.get("confidence_score"))

    report = st.session_state.get("last_report")
    if report and report["session_id"] == session_id:
        breakdown = report["payload"].get("confidence_breakdown")
        if breakdown:
            with st.expander("How the latest confidence score was built"):
                render_breakdown(breakdown)

    if prompt:
        run_research(session_id, prompt)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def stat_card(icon_name: str, tone: str, value: str, label: str) -> str:
    return (
        '<div class="stat"><div class="stat-top">'
        f'<div class="stat-icon {tone}">{icon(icon_name, 20)}</div></div>'
        f'<div class="stat-num">{html.escape(str(value))}</div>'
        f'<div class="stat-lbl">{html.escape(label)}</div></div>'
    )


def confidence_stat_card(avg) -> str:
    ratio = _to_ratio(avg)
    if ratio is None:
        return (
            '<div class="stat"><div class="stat-top"><div class="stat-icon a">'
            f'{icon("gauge", 20)}</div></div><div class="stat-num">—</div>'
            '<div class="stat-lbl">Average confidence</div></div>'
        )
    label, color, _ = confidence_tier(ratio)
    return (
        '<div class="stat"><div class="stat-top">'
        f"{ring_html(ratio, color)}</div>"
        f'<div class="stat-num">{label}</div><div class="stat-lbl">Average confidence</div></div>'
    )


def trend_svg(values: list) -> str:
    w, h, pl, pr, pt, pb = 640, 200, 40, 14, 14, 24
    n = len(values)
    xs = [pl + (w - pl - pr) * (i / (n - 1) if n > 1 else 0.5) for i in range(n)]
    ys = [pt + (h - pt - pb) * (1 - v) for v in values]
    grid = ""
    for frac, lbl in ((1.0, "100%"), (0.5, "50%"), (0.0, "0%")):
        y = pt + (h - pt - pb) * (1 - frac)
        grid += (
            f'<line x1="{pl}" x2="{w - pr}" y1="{y:.1f}" y2="{y:.1f}" stroke="rgba(255,255,255,0.08)" />'
            f'<text x="{pl - 8}" y="{y + 4:.1f}" fill="#6F7EA8" font-size="11" text-anchor="end">{lbl}</text>'
        )
    line = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(zip(xs, ys)))
    area = f"{line} L{xs[-1]:.1f},{h - pb} L{xs[0]:.1f},{h - pb} Z"
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="#0D1430" stroke="#2DD4BF" stroke-width="2" />' for x, y in zip(xs, ys))
    return (
        f'<svg class="trend" viewBox="0 0 {w} {h}" role="img" aria-label="Confidence across recent runs">'
        '<defs><linearGradient id="tg" x1="0" x2="0" y1="0" y2="1">'
        '<stop offset="0" stop-color="#2DD4BF" stop-opacity="0.32"/><stop offset="1" stop-color="#2DD4BF" stop-opacity="0"/></linearGradient>'
        '<linearGradient id="tl" x1="0" x2="1" y1="0" y2="0"><stop offset="0" stop-color="#2DD4BF"/><stop offset="1" stop-color="#8B7CFF"/></linearGradient></defs>'
        f"{grid}"
        f'<path d="{area}" fill="url(#tg)" />'
        f'<path class="draw" pathLength="1" d="{line}" fill="none" stroke="url(#tl)" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" />'
        f"{dots}</svg>"
    )


def runs_table(runs: list) -> str:
    columns = list(runs[0].keys())
    head = "".join(f"<th>{html.escape(str(c).replace('_', ' ').capitalize())}</th>" for c in columns)
    body = ""
    for r in runs[:25]:
        cells = ""
        for c in columns:
            val = r.get(c)
            if c == "confidence_score" and _to_ratio(val) is not None:
                ratio = _to_ratio(val)
                _, color, _ = confidence_tier(ratio)
                pct = round(ratio * 100)
                cells += (
                    '<td><div class="mini"><div class="bd-track">'
                    f'<div class="bd-fill" style="width:{pct}%;background:{color}"></div></div><b>{pct}%</b></div></td>'
                )
            else:
                text = "" if val is None else str(val)
                text = text if len(text) <= 80 else text[:79] + "…"
                cells += f"<td>{html.escape(text)}</td>"
        body += f"<tr>{cells}</tr>"
    return f'<div class="tablewrap"><table class="runs"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def dashboard_page():
    set_content_width(66)
    render_sidebar(load_sessions(), "dashboard")

    st.markdown(
        '<div class="page-title">Dashboard</div>'
        '<div class="page-sub">How your research runs are performing.</div>',
        unsafe_allow_html=True,
    )

    resp = api_get("/dashboard")
    if resp.status_code != 200:
        st.error(error_detail(resp))
        return
    data = resp.json()
    runs = data.get("recent_runs") or []

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(stat_card("message", "", data.get("session_count", 0), "Chats"), unsafe_allow_html=True)
    c2.markdown(stat_card("layers", "v", data.get("message_count", 0), "Messages"), unsafe_allow_html=True)
    c3.markdown(stat_card("bolt", "a", len(runs), "Recent runs"), unsafe_allow_html=True)
    c4.markdown(confidence_stat_card(data.get("avg_confidence")), unsafe_allow_html=True)

    if not runs:
        st.markdown(
            '<div class="panel"><div class="panel-title">No research runs yet</div>'
            '<div class="page-sub" style="margin-bottom:0">Ask a question in a chat and your runs will appear here.</div></div>',
            unsafe_allow_html=True,
        )
        if st.button("Start a chat", type="primary", icon=":material/add:"):
            st.session_state.page = "chat"
            st.rerun()
        return

    values = [r for r in (_to_ratio(run.get("confidence_score")) for run in runs) if r is not None]
    if values:
        st.markdown(
            f'<div class="panel"><div class="panel-title">Confidence across recent runs</div>{trend_svg(values)}</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        f'<div class="panel"><div class="panel-title">Recent runs</div>{runs_table(runs)}</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    st.set_page_config(page_title="AI Research Assistant", page_icon="🔎", layout="wide")
    st.markdown(STYLE, unsafe_allow_html=True)

    if "page" not in st.session_state:
        st.session_state.page = "login"
    if not st.session_state.get("token"):
        login_screen()
        return
    if st.session_state.page == "dashboard":
        dashboard_page()
    else:
        chat_page()


if __name__ == "__main__":
    main()
