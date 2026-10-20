"""Autonomous Cold-Chain Logistics Dispatch Console — Streamlit UI."""
from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import closing

import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from coldchain import db, rag
from coldchain.agent import FLEET_SWEEP_PROMPT, build_agent
from coldchain.config import (
    ALERT_MARGIN_C, AVAILABLE_MODELS, CARGO_PROFILES, HEATWAVE_REGIONS, OPENAI_MODEL, SOP_DIR,
)

st.set_page_config(page_title="Cold-Chain Dispatch Console", page_icon="❄️", layout="wide")

# ----------------------------------------------------------------------------- styling
st.markdown(
    """
<style>
.block-container {padding-top: 1.4rem; padding-bottom: 1rem;}
.hero {background: linear-gradient(120deg,#0e7490 0%,#1e3a8a 55%,#312e81 100%);
       border-radius: 14px; padding: 18px 24px; margin-bottom: 14px; color: #f8fafc;
       display:flex; justify-content:space-between; align-items:center;}
.hero h1 {font-size: 1.65rem; margin: 0; color:#f8fafc;}
.hero p {margin: 2px 0 0 0; opacity: .85; font-size: .92rem;}
.pill {background: rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.25);
       padding: 6px 12px; border-radius: 999px; font-size: .82rem; white-space: nowrap;}
.kpi {background:#111a2e; border:1px solid #1f2a44; border-radius:12px; padding:12px 16px;}
.kpi .lbl {font-size:.74rem; letter-spacing:.06em; text-transform:uppercase; color:#94a3b8;}
.kpi .val {font-size:1.7rem; font-weight:700; line-height:1.2;}
.kpi .sub {font-size:.75rem; color:#64748b;}
.badge {display:inline-block; padding:2px 9px; border-radius:999px; font-size:.75rem; font-weight:600;}
.b-ok {background:#14532d; color:#86efac;} .b-risk {background:#78350f; color:#fcd34d;}
.b-exc {background:#7f1d1d; color:#fca5a5;} .b-done {background:#334155; color:#cbd5e1;}
.step {display:inline-flex; align-items:center; justify-content:center; width:22px; height:22px;
       border-radius:50%; background:#e2e8f0; color:#0f172a; font-weight:700; font-size:.75rem;
       margin-right:8px;}
.flow {font-size:.82rem; color:#cbd5e1; line-height:1.9;}
.action-card {background:#111a2e; border:1px solid #1f2a44; border-left:4px solid #38bdf8;
              border-radius:10px; padding:10px 14px; margin-bottom:8px;}
.action-card.P1 {border-left-color:#ef4444;} .action-card.P2 {border-left-color:#f59e0b;}
.action-card .meta {color:#94a3b8; font-size:.78rem;}
</style>
""",
    unsafe_allow_html=True,
)

STATUS_COLORS = {"ON TRACK": [34, 197, 94], "AT RISK": [245, 158, 11],
                 "EXCURSION": [239, 68, 68], "DELIVERED": [148, 163, 184]}
STATUS_BADGE = {"ON TRACK": "b-ok", "AT RISK": "b-risk", "EXCURSION": "b-exc", "DELIVERED": "b-done"}
STATUS_ICON = {"ON TRACK": "🟢", "AT RISK": "🟡", "EXCURSION": "🔴", "DELIVERED": "⚪"}
TOOL_ICONS = {
    "query_telemetry_db": "🛰️", "get_fleet_overview": "🚚", "run_telemetry_sql": "🗄️",
    "get_route_weather": "🌦️", "search_compliance_sop": "📘", "find_nearest_cold_storage": "🏭",
    "get_dispatch_actions": "📋", "create_dispatch_action": "🚨",
}
DARK_MAP = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"

# ----------------------------------------------------------------------------- state
db.seed()
ss = st.session_state
ss.setdefault("messages", [])
ss.setdefault("thread_id", str(uuid.uuid4()))
ss.setdefault("checkpointer", MemorySaver())
ss.setdefault("last_tick", time.time())


def classify(row) -> str:
    if row["status"] == "DELIVERED":
        return "DELIVERED"
    p = CARGO_PROFILES[row["cargo_class"]]
    t = row["cargo_temp_c"]
    if t < p["min_c"] or t > p["max_c"]:
        return "EXCURSION"
    near_limit = t - p["min_c"] <= ALERT_MARGIN_C or p["max_c"] - t <= ALERT_MARGIN_C
    if near_limit or row["reefer_status"] in ("HIGH_LOAD", "DEGRADED", "FAULT") or row["door_open"]:
        return "AT RISK"
    return "ON TRACK"


def overview() -> pd.DataFrame:
    df = db.fleet_overview_df()
    df["health"] = df.apply(classify, axis=1)
    df["range"] = df["cargo_class"].map(lambda c: f"{CARGO_PROFILES[c]['min_c']:g} … {CARGO_PROFILES[c]['max_c']:g} °C")
    return df


def content_text(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)


# ----------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("## ❄️ FROST Control Panel")
    env_key = bool(os.getenv("OPENAI_API_KEY"))
    key_in = st.text_input(
        "OpenAI API key", type="password",
        placeholder="Loaded from .env ✓" if env_key else "sk-…",
        help="Leave blank to use OPENAI_API_KEY from the environment / .env file.",
    )
    if key_in:
        os.environ["OPENAI_API_KEY"] = key_in.strip()
    has_key = bool(os.getenv("OPENAI_API_KEY"))
    model = st.selectbox(
        "Reasoning model", AVAILABLE_MODELS,
        index=AVAILABLE_MODELS.index(OPENAI_MODEL) if OPENAI_MODEL in AVAILABLE_MODELS else 0,
    )
    st.caption("🟢 OpenAI key configured" if has_key else "🔴 No OpenAI key — copilot disabled")

    st.divider()
    st.markdown("#### 🌡️ Weather threat drill")
    hw_on = st.toggle("Inject simulated heatwave", value=False,
                      help="Overlays extra °C on LIVE Open-Meteo data inside a region to rehearse SOP-WX-003.")
    hw_region = st.selectbox("Region", list(HEATWAVE_REGIONS), disabled=not hw_on)
    hw_delta = st.slider("Heat overlay (+°C)", 3, 18, 12, disabled=not hw_on)
    scenario = {"enabled": hw_on, "region": hw_region, "delta_c": hw_delta} if hw_on else None

    st.divider()
    st.markdown("#### 📡 Telemetry stream")
    live = st.toggle("Live stream (auto-advance)", value=False)
    interval = st.select_slider("Tick interval", options=[5, 10, 20, 30, 60], value=10,
                                format_func=lambda s: f"{s}s real = 15 min fleet")
    c1, c2 = st.columns(2)
    if c1.button("⏭ +15 min", width="stretch", help="Advance fleet clock one tick"):
        db.simulate_tick()
    if c2.button("♻️ Reset", width="stretch", help="Re-seed the telemetry database"):
        db.seed(force=True)
        ss.messages, ss.thread_id = [], str(uuid.uuid4())
        st.toast("Telemetry database re-seeded")

    st.divider()
    st.markdown("#### 📚 SOP vector index")
    if rag.index_ready():
        st.caption(f"✅ {len(rag.get_store().chunks)} SOP sections embedded")
    else:
        st.caption("Index builds on first SOP search (cached on disk).")
    if st.button("Rebuild index", width="stretch", disabled=not has_key):
        with st.spinner("Embedding SOP rulebook…"):
            rag.get_store(force_rebuild=True)
        st.toast("SOP index rebuilt")
    if st.button("🧹 New conversation", width="stretch"):
        ss.messages, ss.thread_id = [], str(uuid.uuid4())

# ----------------------------------------------------------------------------- header
st.markdown(
    f"""<div class="hero"><div><h1>❄️ Cold-Chain Dispatch Console</h1>
<p>Autonomous reasoning over fleet telemetry · live route weather · SOP vector RAG — powered by LangGraph + OpenAI <b>{model}</b></p></div>
<div class="pill">🕒 Fleet clock {db.fleet_clock()} UTC{' · 🔥 Heatwave drill' if hw_on else ''}{' · 📡 LIVE' if live else ''}</div></div>""",
    unsafe_allow_html=True,
)

run_every = interval if live else None


@st.fragment(run_every=run_every)
def kpi_strip():
    if live and time.time() - ss.last_tick >= interval * 0.9:
        db.simulate_tick()
        ss.last_tick = time.time()
    df = overview()
    actions = db.actions_df()
    pending = int((actions["status"] == "PROPOSED").sum()) if not actions.empty else 0
    in_transit = df[df["status"] == "IN_TRANSIT"]
    cards = [
        ("Active shipments", len(in_transit), f"{len(df)} total · ${df['cargo_value_usd'].sum()/1e6:.1f}M cargo", "#e2e8f0"),
        ("On track", int((df["health"] == "ON TRACK").sum()), "inside SOP range", "#4ade80"),
        ("At risk", int((df["health"] == "AT RISK").sum()), "alert band / equipment / door", "#fbbf24"),
        ("Excursions", int((df["health"] == "EXCURSION").sum()), "outside SOP range", "#f87171"),
        ("Pending actions", pending, "awaiting dispatcher approval", "#38bdf8"),
    ]
    for col, (lbl, val, sub, color) in zip(st.columns(len(cards)), cards):
        col.markdown(f'<div class="kpi"><div class="lbl">{lbl}</div>'
                     f'<div class="val" style="color:{color}">{val}</div><div class="sub">{sub}</div></div>',
                     unsafe_allow_html=True)


kpi_strip()
st.write("")

tab_chat, tab_map, tab_tlm, tab_queue, tab_sop = st.tabs(
    ["🧠 AI Copilot", "🗺️ Live Fleet Map", "📈 Telemetry Explorer", "🚨 Dispatch Queue", "📚 SOP Rulebook"]
)


# ----------------------------------------------------------------------------- copilot
def render_step(step: dict, n: int) -> None:
    icon = TOOL_ICONS.get(step["tool"], "🔧")
    if step["kind"] == "call":
        args = ", ".join(f'{k}={json.dumps(v)}' for k, v in step["args"].items())
        st.markdown(f'<span class="step">{n}</span> **Agent → Tool** {icon} `{step["tool"]}({args})`',
                    unsafe_allow_html=True)
    else:
        body = step["content"]
        try:
            body = json.dumps(json.loads(body), indent=1)
        except (ValueError, TypeError):
            pass
        st.markdown(f'<span class="step">{n}</span> **Data → Agent** ↩ `{step["tool"]}` returned',
                    unsafe_allow_html=True)
        st.code(body if len(body) < 1800 else body[:1800] + "\n… (truncated)", language="json")


def get_graph():
    key = (model, hash(os.getenv("OPENAI_API_KEY", "")))
    if ss.get("graph_key") != key:
        ss.graph = build_agent(model, ss.checkpointer)
        ss.graph_key = key
    return ss.graph


def run_agent(prompt: str) -> None:
    with st.chat_message("user", avatar="🧑‍✈️"):
        st.markdown(prompt)
    trace, final = [], ""
    with st.chat_message("assistant", avatar="❄️"):
        status = st.status("FROST is reasoning…", expanded=True)
        cfg = {"configurable": {"thread_id": ss.thread_id, "weather_scenario": scenario},
               "recursion_limit": 60}
        try:
            stream = get_graph().stream({"messages": [HumanMessage(prompt)]}, cfg, stream_mode="updates")
            for update in stream:
                for _node, payload in update.items():
                    for msg in (payload or {}).get("messages", []):
                        if isinstance(msg, AIMessage):
                            for tc in msg.tool_calls:
                                trace.append({"kind": "call", "tool": tc["name"], "args": tc["args"]})
                                with status:
                                    render_step(trace[-1], len(trace))
                            if not msg.tool_calls:
                                final = content_text(msg.content)
                        elif isinstance(msg, ToolMessage):
                            trace.append({"kind": "result", "tool": msg.name, "content": content_text(msg.content)})
                            with status:
                                render_step(trace[-1], len(trace))
            calls = sum(1 for t in trace if t["kind"] == "call")
            status.update(label=f"✅ Reasoning complete · {calls} tool calls", state="complete", expanded=False)
        except Exception as exc:  # noqa: BLE001 - show any LLM/API failure in the UI
            status.update(label="❌ Agent error", state="error", expanded=True)
            final = f"⚠️ **Agent error:** `{type(exc).__name__}: {exc}`"
        st.markdown(final or "_No answer produced._")
    ss.messages.append({"role": "user", "content": prompt})
    ss.messages.append({"role": "assistant", "content": final, "trace": trace})


QUICK_PROMPTS = [
    "Is Shipment A42 on track?",
    "Check D23 — is the ice cream at risk and what should we do?",
    "Did anything happen to the B17 vaccine load in the last few hours?",
    "Are there any heatwave threats on F05's route to Las Vegas?",
    "Which trucks had door-open events today? Use SQL.",
    "What does the SOP say about reefer DEGRADED status?",
]

with tab_chat:
    chat_col, side_col = st.columns([2.3, 1], gap="large")
    with side_col:
        st.markdown("##### 🛰️ Autonomous mode")
        sweep = st.button("Run fleet-wide risk sweep", type="primary", width="stretch",
                          disabled=not has_key)
        st.caption("FROST inspects every truck, cross-checks SOPs + live weather, and queues actions.")
        st.markdown("##### 💬 Quick prompts")
        for i, qp in enumerate(QUICK_PROMPTS):
            if st.button(qp, key=f"qp{i}", width="stretch", disabled=not has_key):
                ss.pending_prompt = qp
        st.markdown("##### 🔁 Reasoning loop")
        st.markdown(
            """<div class="flow"><span class="step">1</span>Operator asks a question<br>
<span class="step">2</span>Agent calls <code>query_telemetry_db</code><br>
<span class="step">3</span>DB returns GPS + reefer temps<br>
<span class="step">4</span>Agent calls <code>search_compliance_sop</code><br>
<span class="step">5</span>Vector RAG returns SOP limits<br>
<span class="step">6</span>+ <code>get_route_weather</code> (Open-Meteo)<br>
<span class="step">7</span>Verdict + proposed dispatch actions</div>""",
            unsafe_allow_html=True,
        )
    with chat_col:
        box = st.container(height=640, border=True)
        with box:
            if not ss.messages:
                st.markdown(
                    "#### 👋 FROST is standing by\nAsk about any shipment (**A42, B17, C08, D23, E11, F05**), "
                    "the fleet, weather or SOPs — or run an autonomous risk sweep."
                )
            for m in ss.messages:
                with st.chat_message(m["role"], avatar="🧑‍✈️" if m["role"] == "user" else "❄️"):
                    if m.get("trace"):
                        n_calls = sum(1 for t in m["trace"] if t["kind"] == "call")
                        with st.expander(f"🔧 Reasoning trace · {n_calls} tool calls"):
                            for i, step in enumerate(m["trace"], 1):
                                render_step(step, i)
                    st.markdown(m["content"])
        typed = st.chat_input("Ask FROST… e.g. “Is Shipment A42 on track?”", disabled=not has_key)
        prompt = typed or ss.pop("pending_prompt", None) or (FLEET_SWEEP_PROMPT if sweep else None)
        if prompt and has_key:
            with box:
                run_agent(prompt)
            st.rerun()


# ----------------------------------------------------------------------------- fleet map
def fleet_deck(df: pd.DataFrame, focus: str | None = None, height: int = 560) -> pdk.Deck:
    tlm = db.telemetry_df()
    planned, trails, trucks, labels = [], [], [], []
    for _, r in df.iterrows():
        color = STATUS_COLORS[r["health"]]
        wps = db.get_waypoints(r["shipment_id"])
        planned.append({"path": [[w["lon"], w["lat"]] for w in wps],
                        "tip": f"<b>{r['shipment_id']}</b> planned route<br>{r['origin']} → {r['destination']}"})
        t = tlm[tlm["shipment_id"] == r["shipment_id"]]
        trails.append({"path": t[["lon", "lat"]].values.tolist(), "color": color,
                       "tip": f"<b>{r['shipment_id']}</b> GPS trail ({len(t)} pings)"})
        trucks.append({
            "lon": r["lon"], "lat": r["lat"], "color": color + [235],
            "radius": 16000 if r["shipment_id"] == focus else 10000,
            "tip": (f"<b>{r['shipment_id']} · {r['cargo']}</b><br>{r['origin']} → {r['destination']}"
                    f"<br>Cargo {r['cargo_temp_c']:.1f} °C (SOP {r['range']})<br>Ambient {r['ambient_temp_c']:.1f} °C"
                    f"<br>Reefer {r['reefer_status']} · {r['progress_pct']:.0f}% complete<br><b>{r['health']}</b>"),
        })
        labels.append({"lon": r["lon"], "lat": r["lat"], "text": r["shipment_id"]})
    with closing(db.connect(readonly=True)) as conn:
        fac = pd.read_sql_query("SELECT * FROM cold_storage_facilities", conn)
    fac["tip"] = ("🏭 <b>" + fac["name"] + "</b><br>" + fac["city"] + "<br>" + fac["supported_classes"]
                  + "<br>Pallets free: " + fac["available_pallets"].astype(str))
    layers = [
        pdk.Layer("PathLayer", planned, get_path="path", get_color=[100, 116, 139, 140], width_min_pixels=2,
                  get_width=3, pickable=True),
        pdk.Layer("PathLayer", trails, get_path="path", get_color="color", width_min_pixels=4,
                  get_width=5, pickable=True),
        pdk.Layer("ScatterplotLayer", fac, get_position=["lon", "lat"], get_fill_color=[56, 189, 248, 170],
                  get_radius=6000, radius_min_pixels=3, pickable=True),
        pdk.Layer("ScatterplotLayer", trucks, get_position=["lon", "lat"], get_fill_color="color",
                  get_line_color=[255, 255, 255], line_width_min_pixels=2, stroked=True,
                  get_radius="radius", radius_min_pixels=7, pickable=True),
        pdk.Layer("TextLayer", labels, get_position=["lon", "lat"], get_text="text", get_size=14,
                  get_color=[241, 245, 249], get_pixel_offset=[0, -20], font_weight=700),
    ]
    if focus:
        r = df[df["shipment_id"] == focus].iloc[0]
        view = pdk.ViewState(latitude=r["lat"], longitude=r["lon"], zoom=5.2)
    else:
        view = pdk.ViewState(latitude=37.8, longitude=-97.5, zoom=3.4)
    return pdk.Deck(layers=layers, initial_view_state=view, map_provider="carto", map_style=DARK_MAP,
                    tooltip={"html": "{tip}", "style": {"backgroundColor": "#0f172a", "color": "#e2e8f0",
                                                        "fontSize": "12px"}}, height=height)


with tab_map:
    @st.fragment(run_every=run_every)
    def fleet_panel():
        df = overview()
        st.pydeck_chart(fleet_deck(df), width="stretch")
        st.caption("● trucks coloured by SOP health · grey = planned route · coloured = GPS trail · "
                   "🔵 small dots = cold-storage facilities")
        show = df[["shipment_id", "cargo", "cargo_class", "range", "cargo_temp_c", "ambient_temp_c",
                   "reefer_status", "progress_pct", "origin", "destination", "health"]].copy()
        show["health"] = show["health"].map(lambda h: f"{STATUS_ICON[h]} {h}")
        st.dataframe(
            show, hide_index=True, width="stretch",
            column_config={
                "shipment_id": "Shipment", "cargo": "Cargo", "cargo_class": "Class", "range": "SOP range",
                "cargo_temp_c": st.column_config.NumberColumn("Cargo °C", format="%.1f"),
                "ambient_temp_c": st.column_config.NumberColumn("Ambient °C", format="%.1f"),
                "reefer_status": "Reefer", "origin": "Origin", "destination": "Destination",
                "progress_pct": st.column_config.ProgressColumn("Progress", format="%.0f%%", min_value=0, max_value=100),
                "health": "Health",
            },
        )

    fleet_panel()


# ----------------------------------------------------------------------------- telemetry explorer
with tab_tlm:
    @st.fragment(run_every=run_every)
    def telemetry_panel():
        df = overview()
        sid = st.selectbox(
            "Shipment", df["shipment_id"].tolist(),
            format_func=lambda s: f"{s} — {df.set_index('shipment_id').loc[s, 'cargo']}", key="tlm_sid",
        )
        r = df.set_index("shipment_id").loc[sid]
        prof = CARGO_PROFILES[r["cargo_class"]]
        t = db.telemetry_df(sid)
        trend = (t["cargo_temp_c"].iloc[-1] - t["cargo_temp_c"].iloc[-9]) / 2 if len(t) >= 9 else 0.0

        st.markdown(f'<span class="badge {STATUS_BADGE[r["health"]]}">{STATUS_ICON[r["health"]]} {r["health"]}</span>'
                    f' &nbsp; **{r["cargo"]}** · {r["customer"]} · {r["truck_id"]} / {r["driver"]}',
                    unsafe_allow_html=True)
        m = st.columns(6)
        m[0].metric("Cargo temp", f"{r['cargo_temp_c']:.1f} °C", f"{trend:+.2f} °C/h (2h)", delta_color="inverse")
        m[1].metric("SOP range", f"{prof['min_c']:g} … {prof['max_c']:g} °C")
        m[2].metric("Ambient", f"{r['ambient_temp_c']:.1f} °C")
        m[3].metric("Reefer", r["reefer_status"])
        m[4].metric("Progress", f"{r['progress_pct']:.0f}%")
        m[5].metric("Cargo value", f"${r['cargo_value_usd']:,.0f}")

        left, right = st.columns([1.7, 1])
        with left:
            fig = go.Figure()
            fig.add_hrect(y0=prof["min_c"], y1=prof["max_c"], fillcolor="rgba(34,197,94,0.12)", line_width=0,
                          annotation_text="SOP-TC-001 allowed range", annotation_position="top left")
            for y in (prof["min_c"], prof["max_c"]):
                fig.add_hline(y=y, line_dash="dot", line_color="rgba(239,68,68,.7)")
            fig.add_trace(go.Scatter(x=t["ts"], y=t["cargo_temp_c"], name="Cargo temp", mode="lines+markers",
                                     line=dict(color="#38bdf8", width=3), marker=dict(size=5)))
            fig.add_trace(go.Scatter(x=t["ts"], y=t["ambient_temp_c"], name="Ambient", yaxis="y2",
                                     line=dict(color="#f97316", dash="dash", width=1.5)))
            doors = t[t["door_open"] == 1]
            if not doors.empty:
                fig.add_trace(go.Scatter(x=doors["ts"], y=doors["cargo_temp_c"], mode="markers", name="Door open",
                                         marker=dict(symbol="x", size=13, color="#f43f5e")))
            fig.update_layout(
                template="plotly_dark", height=420, margin=dict(l=10, r=10, t=30, b=10),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(title="Cargo °C"), yaxis2=dict(title="Ambient °C", overlaying="y", side="right",
                                                         showgrid=False),
                legend=dict(orientation="h", y=1.12), title=f"{sid} reefer telemetry (15-min pings)",
            )
            st.plotly_chart(fig, width="stretch")
        with right:
            st.pydeck_chart(fleet_deck(df[df["shipment_id"] == sid], focus=sid, height=420),
                            width="stretch")
        with st.expander("Raw telemetry rows"):
            st.dataframe(t.sort_values("ts", ascending=False), hide_index=True, width="stretch")
        if st.button(f"🧠 Ask FROST to assess {sid}", disabled=not has_key):
            ss.pending_prompt = f"Is Shipment {sid} on track? Give a full assessment and act per SOP if needed."
            st.toast("Queued — open the 🧠 AI Copilot tab to watch FROST reason.")
            st.rerun()

    telemetry_panel()


# ----------------------------------------------------------------------------- dispatch queue
with tab_queue:
    acts = db.actions_df()
    q1, q2 = st.columns([3, 1])
    q1.markdown("#### Dispatch action queue")
    filt = q2.selectbox("Status", ["ALL", "PROPOSED", "APPROVED", "REJECTED"], label_visibility="collapsed")
    if filt != "ALL":
        acts = acts[acts["status"] == filt]
    if acts.empty:
        st.info("No dispatch actions yet. Ask FROST about an at-risk shipment or run a fleet sweep.")
    for _, a in acts.iterrows():
        c_card, c_btn = st.columns([5, 1])
        status_icon = {"PROPOSED": "⏳", "APPROVED": "✅", "REJECTED": "✖️"}[a["status"]]
        c_card.markdown(
            f'<div class="action-card {a["priority"]}"><b>#{a["action_id"]} · {a["priority"]} · '
            f'{a["action_type"]}</b> — shipment <b>{a["shipment_id"]}</b> &nbsp; {status_icon} {a["status"]}'
            f'<br>{a["summary"]}<div class="meta">📎 {a["sop_references"]} · created {a["created_at"]} by '
            f'{a["created_by"]}</div><div class="meta">🧠 {a["rationale"]}</div></div>',
            unsafe_allow_html=True,
        )
        if a["status"] == "PROPOSED":
            if c_btn.button("Approve", key=f"ap{a['action_id']}", type="primary", width="stretch"):
                db.set_action_status(int(a["action_id"]), "APPROVED")
                st.rerun()
            if c_btn.button("Reject", key=f"rj{a['action_id']}", width="stretch"):
                db.set_action_status(int(a["action_id"]), "REJECTED")
                st.rerun()


# ----------------------------------------------------------------------------- SOP library
with tab_sop:
    s_left, s_right = st.columns([1, 1.2], gap="large")
    with s_left:
        st.markdown("#### 🔎 Semantic SOP search (vector RAG)")
        query = st.text_input("Query", placeholder="e.g. what to do if ice cream warms during a heatwave",
                              disabled=not has_key)
        if query and has_key:
            with st.spinner("Embedding query & ranking SOP sections…"):
                try:
                    hits = rag.get_store().search(query, k=4)
                except Exception as exc:  # noqa: BLE001
                    hits = []
                    st.error(f"SOP search failed: {exc}")
            for h in hits:
                with st.container(border=True):
                    st.markdown(f"**{h['doc_id']}** · {h['section']}")
                    st.progress(min(max(h["score"], 0.0), 1.0), text=f"cosine similarity {h['score']:.3f}")
                    st.markdown(h["text"].split("\n\n", 1)[-1])
    with s_right:
        st.markdown("#### 📚 Corporate rulebook")
        for path in sorted(SOP_DIR.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            with st.expander(text.splitlines()[0].lstrip("# ")):
                st.markdown(text.split("\n", 1)[1])
