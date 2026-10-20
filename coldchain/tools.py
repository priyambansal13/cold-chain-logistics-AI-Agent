"""LangChain tools exposed to the LangGraph dispatch agent."""
from __future__ import annotations

import json
from typing import Literal

import requests
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from . import db, rag, weather


def _j(obj) -> str:
    return json.dumps(obj, default=str, indent=1)


def _not_found(shipment_id: str) -> str:
    ids = db.fleet_overview_df()["shipment_id"].tolist()
    return _j({"error": f"Shipment '{shipment_id}' not found.", "known_shipments": ids})


@tool
def query_telemetry_db(shipment_id: str, hours: float = 3.0) -> str:
    """Query the fleet telemetry database for ONE shipment.

    Returns shipment manifest (cargo, cargo_class, customer, truck, setpoint), the latest GPS
    position and reefer sensor reading, route progress & projected ETA, statistics over the
    last `hours` (min/max/avg cargo temp, temperature trend per hour, door-open events,
    reefer status counts) and the most recent raw readings.
    """
    shp = db.get_shipment(shipment_id)
    if not shp:
        return _not_found(shipment_id)
    sid = shp["shipment_id"]
    df = db.telemetry_df(sid, hours=hours)
    if df.empty:
        return _j({"shipment": shp, "error": "No telemetry in window."})
    last = df.iloc[-1]
    span_h = max((df["ts"].iloc[-1] - df["ts"].iloc[0]).total_seconds() / 3600, 1e-6)
    trend = (df["cargo_temp_c"].iloc[-1] - df["cargo_temp_c"].iloc[0]) / span_h if len(df) > 1 else 0.0
    recent = df.tail(8)[["ts", "cargo_temp_c", "ambient_temp_c", "door_open", "reefer_status", "speed_kmh"]]
    return _j({
        "shipment": shp,
        "latest_reading": {
            "ts_utc": last["ts"], "lat": last["lat"], "lon": last["lon"],
            "cargo_temp_c": last["cargo_temp_c"], "ambient_temp_c": last["ambient_temp_c"],
            "humidity_pct": last["humidity_pct"], "door_open": int(last["door_open"]),
            "speed_kmh": last["speed_kmh"], "reefer_status": last["reefer_status"],
            "battery_pct": last["battery_pct"],
        },
        "route": db.route_progress(sid, last["lat"], last["lon"]),
        "window_stats": {
            "hours": hours,
            "readings": len(df),
            "cargo_temp_min_c": round(df["cargo_temp_c"].min(), 2),
            "cargo_temp_max_c": round(df["cargo_temp_c"].max(), 2),
            "cargo_temp_avg_c": round(df["cargo_temp_c"].mean(), 2),
            "trend_c_per_hour": round(float(trend), 3),
            "door_open_readings": int(df["door_open"].sum()),
            "reefer_status_counts": df["reefer_status"].value_counts().to_dict(),
        },
        "recent_readings": recent.to_dict(orient="records"),
    })


@tool
def get_fleet_overview() -> str:
    """List every shipment in the fleet with its latest position, cargo temperature, reefer status,
    door state, route and progress. Use this first for fleet-wide questions or risk sweeps."""
    df = db.fleet_overview_df()
    cols = ["shipment_id", "cargo", "cargo_class", "origin", "destination", "status", "progress_pct",
            "last_ts", "lat", "lon", "cargo_temp_c", "ambient_temp_c", "reefer_status", "door_open",
            "cargo_value_usd", "pallets"]
    return _j({"fleet_clock_utc": db.fleet_clock(), "shipments": df[cols].to_dict(orient="records")})


def _run_telemetry_sql(sql: str) -> str:
    return _j(db.run_readonly_sql(sql))


_run_telemetry_sql.__doc__ = f"""Run a read-only SQL (SQLite dialect) SELECT query against the legacy
telemetry database for ad-hoc analytics (e.g. temperature history, door events, comparisons across
trucks, dispatch history). Max 60 rows returned. Schema:
{db.SCHEMA_FOR_LLM}"""
_run_telemetry_sql.__name__ = "run_telemetry_sql"
run_telemetry_sql = tool(_run_telemetry_sql)


@tool
def get_route_weather(shipment_id: str, config: RunnableConfig) -> str:
    """Fetch LIVE weather (Open-Meteo API) for a shipment's current GPS position and every remaining
    waypoint on its route, including 3-day forecast max/min temperatures, precipitation, wind, and
    pre-computed threat flags (EXTREME_HEAT, SEVERE_HEAT, ELEVATED_HEAT, THUNDERSTORM, ...).
    Includes hours until the truck reaches each waypoint."""
    shp = db.get_shipment(shipment_id)
    if not shp:
        return _not_found(shipment_id)
    sid = shp["shipment_id"]
    if shp["status"] != "IN_TRANSIT":
        return _j({"shipment_id": sid, "note": "Shipment delivered; no remaining route."})
    last = db.telemetry_df(sid).iloc[-1]
    points = [{"name": "Current truck position", "lat": float(last["lat"]), "lon": float(last["lon"]),
               "hours_until_arrival": 0.0}]
    points += [{"name": w["name"], "lat": w["lat"], "lon": w["lon"],
                "hours_until_arrival": w["hours_until_arrival"]} for w in db.remaining_route_points(sid)]
    scenario = (config or {}).get("configurable", {}).get("weather_scenario")
    try:
        forecast = weather.fetch_forecast(points, days=3, scenario=scenario)
    except requests.RequestException as exc:
        return _j({"error": f"Weather API unavailable: {exc}"})

    worst_max, all_flags = -99.0, set()
    for f in forecast:
        # Only the forecast days that overlap the truck's passage matter (today + next day).
        relevant = f["daily"][: 2 if f["hours_until_arrival"] < 24 else 3]
        f["route_relevant_max_c"] = max((d["max_c"] for d in relevant), default=None)
        f["route_relevant_flags"] = sorted({fl for d in relevant for fl in d["threat_flags"]})
        worst_max = max(worst_max, f["route_relevant_max_c"] or -99)
        all_flags.update(f["route_relevant_flags"])
    return _j({
        "shipment_id": sid,
        "source": "Open-Meteo live forecast API" + (" + simulated scenario overlay" if any(
            "scenario_overlay" in f for f in forecast) else ""),
        "route_worst_forecast_max_c": worst_max,
        "route_threat_flags": sorted(all_flags),
        "points": forecast,
    })


@tool
def search_compliance_sop(query: str, k: int = 4) -> str:
    """Semantic (vector RAG) search over the corporate SOP rulebook: temperature ranges per cargo
    class, excursion response, extreme weather / heatwave rules, pharma GDP rules, reefer failure
    procedures and the dispatch action catalogue. Always use this to obtain limits and procedures;
    never rely on memory. Returns the best matching SOP sections with their document IDs."""
    try:
        hits = rag.get_store().search(query, k=k)
    except Exception as exc:  # noqa: BLE001 - surface any embedding failure to the agent
        return _j({"error": f"SOP search failed: {exc}"})
    return _j([{"doc_id": h["doc_id"], "section": h["section"], "score": h["score"], "text": h["text"]}
               for h in hits])


@tool
def find_nearest_cold_storage(shipment_id: str, k: int = 3) -> str:
    """Find the nearest cold-storage / cross-dock facilities to a shipment's CURRENT position that
    support its cargo class. Returns distance, estimated drive hours, available pallets,
    GDP certification and 24h availability."""
    shp = db.get_shipment(shipment_id)
    if not shp:
        return _not_found(shipment_id)
    last = db.telemetry_df(shp["shipment_id"]).iloc[-1]
    return _j({
        "shipment_id": shp["shipment_id"],
        "cargo_class": shp["cargo_class"],
        "pallets_needed": shp["pallets"],
        "facilities": db.nearest_facilities(float(last["lat"]), float(last["lon"]), shp["cargo_class"], k),
    })


ActionType = Literal["MONITOR", "PRE_COOL", "REROUTE", "DIVERT_COLD_STORAGE", "MAINTENANCE_DISPATCH",
                     "CUSTOMER_NOTIFY", "ESCALATE_QA", "QUARANTINE"]


@tool
def create_dispatch_action(shipment_id: str, action_type: ActionType, priority: Literal["P1", "P2", "P3"],
                           summary: str, rationale: str, sop_references: str) -> str:
    """Propose a dispatch action into the control-tower queue (status PROPOSED; a human dispatcher
    approves). Use only when telemetry/weather evidence and an SOP justify it. `summary` is a
    one-line instruction, `rationale` cites the evidence, `sop_references` lists SOP IDs/sections."""
    shp = db.get_shipment(shipment_id)
    if not shp:
        return _not_found(shipment_id)
    existing = db.actions_df(shp["shipment_id"])
    dup = existing[(existing["action_type"] == action_type) & existing["status"].isin(["PROPOSED", "APPROVED"])]
    if not dup.empty:
        return _j({"skipped": True, "reason": "Duplicate open action exists",
                   "existing_action_id": int(dup.iloc[0]["action_id"])})
    action_id = db.log_action(shp["shipment_id"], action_type, priority, summary, rationale, sop_references)
    return _j({"created": True, "action_id": action_id, "status": "PROPOSED"})


@tool
def get_dispatch_actions(shipment_id: str = "") -> str:
    """List existing dispatch actions (optionally for one shipment) to avoid duplicates and report
    what is already in progress."""
    df = db.actions_df(shipment_id or None)
    return _j(df.to_dict(orient="records"))


TOOLS = [
    query_telemetry_db,
    get_fleet_overview,
    run_telemetry_sql,
    get_route_weather,
    search_compliance_sop,
    find_nearest_cold_storage,
    get_dispatch_actions,
    create_dispatch_action,
]
