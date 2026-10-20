# ❄️ Autonomous Cold-Chain Logistics Dispatch Console

An AI dispatch copilot (**FROST**) that turns a legacy telemetry database into a proactive
reasoning engine. Built with **LangGraph + OpenAI**, a **vector-RAG SOP rulebook**, **live
Open-Meteo weather**, and a **Streamlit** control-tower UI.

```
Operator ──"Is A42 on track?"──▶ LangGraph Agent ──▶ query_telemetry_db  ──▶ SQLite telemetry (GPS, reefer temps)
                                       │          ──▶ search_compliance_sop ──▶ Vector RAG (OpenAI embeddings over SOPs)
                                       │          ──▶ get_route_weather   ──▶ Open-Meteo live forecast API
                                       │          ──▶ find_nearest_cold_storage / run_telemetry_sql
                                       ◀──────────── create_dispatch_action (PROPOSED → human approves)
Operator ◀── "A42 is within range (-20.5 °C, SOP-TC-001 §2: -22…-18 °C). No route threats."
```

## Quick start
```bash
cd cold-chain-dispatch
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env          # add your OPENAI_API_KEY (or paste it into the sidebar)
.venv/bin/streamlit run app.py
```
The telemetry DB is seeded automatically on first run (`data/telemetry.db`); the SOP vector index
is built on the first SOP search and cached in `data/sop_vector_index.json`.

## Features
| Tab | What it does |
|---|---|
| 🧠 AI Copilot | Chat with FROST; every tool call/result is streamed live as a numbered reasoning trace. One-click **autonomous fleet risk sweep**. |
| 🗺️ Live Fleet Map | pydeck map: planned routes, GPS trails, trucks coloured by SOP health, cold-storage facilities. |
| 📈 Telemetry Explorer | Cargo vs ambient temperature with the SOP band, door-open markers, 2-h trend. |
| 🚨 Dispatch Queue | AI-proposed actions (with SOP citations + rationale) for dispatcher approve / reject. |
| 📚 SOP Rulebook | Semantic search over the SOPs with cosine scores; full rulebook viewer. |

Sidebar: model picker, **heatwave drill** (overlays +°C on live weather in a region), **live telemetry
stream** (each tick = 15 fleet-minutes), DB reset, index rebuild.

## Built-in scenarios
| Shipment | Cargo | Situation the copilot should discover |
|---|---|---|
| A42 | Frozen salmon, Chicago → Phoenix | Nominal at ≈ -20.5 °C; heads into the Southwest (try the heatwave drill) |
| B17 | mRNA vaccines, Memphis → Dallas | Door-open event with a 30-min excursion > 8 °C (GDP deviation → QA) |
| C08 | Live seafood, Seattle → Sacramento | Nominal |
| D23 | Ice cream, Atlanta → Miami | Reefer DEGRADED, temperature drifting toward -23 °C → imminent breach |
| E11 | Biologics, Boston → Philadelphia | Nominal, high value |
| F05 | Berries, Fresno → Las Vegas | Reefer HIGH_LOAD in desert heat, rising trend |

## Project layout
```
app.py                    Streamlit console
coldchain/agent.py        LangGraph StateGraph (agent ⇄ ToolNode) + system prompt
coldchain/tools.py        8 tools exposed to the agent
coldchain/db.py           SQLite schema, seeding, queries, live simulation, read-only SQL guard
coldchain/rag.py          SOP chunking, OpenAI embeddings, cosine search, disk cache
coldchain/weather.py      Open-Meteo client + threat flags + drill overlay
coldchain/fleet_data.py   Synthetic fleet + sensor physics (kept out of the DB on purpose)
data/sops/*.md            Corporate rulebooks (edit them; the index auto-rebuilds)
```

Notes: the agent's SQL tool opens the DB read-only and rejects non-SELECT statements. Temperature
limits shown in the UI mirror SOP-TC-001 for colouring only — the agent must retrieve them via RAG.
