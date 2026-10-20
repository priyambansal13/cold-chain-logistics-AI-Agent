"""Legacy telemetry database (SQLite): schema, seeding, queries and live simulation."""
from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pandas as pd

from . import fleet_data
from .config import DB_PATH, TICK_MINUTES
from .geo import haversine_km, route_length_km, route_position

TS_FMT = "%Y-%m-%d %H:%M:%S"

SCHEMA = """
CREATE TABLE IF NOT EXISTS shipments (
    shipment_id      TEXT PRIMARY KEY,
    cargo            TEXT NOT NULL,
    cargo_class      TEXT NOT NULL,
    customer         TEXT NOT NULL,
    origin           TEXT NOT NULL,
    destination      TEXT NOT NULL,
    truck_id         TEXT NOT NULL,
    driver           TEXT NOT NULL,
    reefer_setpoint_c REAL NOT NULL,
    cargo_value_usd  REAL NOT NULL,
    pallets          INTEGER NOT NULL,
    departed_at      TEXT NOT NULL,
    planned_eta      TEXT NOT NULL,
    planned_hours    REAL NOT NULL,
    progress_pct     REAL NOT NULL,
    status           TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS route_waypoints (
    shipment_id TEXT NOT NULL,
    seq         INTEGER NOT NULL,
    name        TEXT NOT NULL,
    lat         REAL NOT NULL,
    lon         REAL NOT NULL,
    PRIMARY KEY (shipment_id, seq)
);
CREATE TABLE IF NOT EXISTS telemetry (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    shipment_id    TEXT NOT NULL,
    ts             TEXT NOT NULL,
    lat            REAL NOT NULL,
    lon            REAL NOT NULL,
    cargo_temp_c   REAL NOT NULL,
    ambient_temp_c REAL NOT NULL,
    humidity_pct   REAL NOT NULL,
    door_open      INTEGER NOT NULL,
    speed_kmh      REAL NOT NULL,
    reefer_status  TEXT NOT NULL,
    battery_pct    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_tlm_ship_ts ON telemetry(shipment_id, ts);
CREATE TABLE IF NOT EXISTS cold_storage_facilities (
    facility_id       TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    city              TEXT NOT NULL,
    lat               REAL NOT NULL,
    lon               REAL NOT NULL,
    supported_classes TEXT NOT NULL,
    gdp_certified     INTEGER NOT NULL,
    available_pallets INTEGER NOT NULL,
    open_24h          INTEGER NOT NULL,
    contact_phone     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dispatch_actions (
    action_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT NOT NULL,
    shipment_id    TEXT NOT NULL,
    action_type    TEXT NOT NULL,
    priority       TEXT NOT NULL,
    summary        TEXT NOT NULL,
    rationale      TEXT NOT NULL,
    sop_references TEXT NOT NULL,
    status         TEXT NOT NULL,
    created_by     TEXT NOT NULL
);
"""

# Schema description handed to the LLM for ad-hoc SQL.
SCHEMA_FOR_LLM = """
shipments(shipment_id, cargo, cargo_class, customer, origin, destination, truck_id, driver,
          reefer_setpoint_c, cargo_value_usd, pallets, departed_at, planned_eta, planned_hours,
          progress_pct, status)                      -- status: IN_TRANSIT | DELIVERED
route_waypoints(shipment_id, seq, name, lat, lon)    -- planned route, seq 0 = origin
telemetry(id, shipment_id, ts, lat, lon, cargo_temp_c, ambient_temp_c, humidity_pct,
          door_open, speed_kmh, reefer_status, battery_pct)
          -- one row per 15 min per truck; ts = 'YYYY-MM-DD HH:MM:SS' UTC;
          -- reefer_status: OK | HIGH_LOAD | DEGRADED | FAULT ; door_open: 0/1
cold_storage_facilities(facility_id, name, city, lat, lon, supported_classes, gdp_certified,
          available_pallets, open_24h, contact_phone)
dispatch_actions(action_id, created_at, shipment_id, action_type, priority, summary, rationale,
          sop_references, status, created_by)        -- status: PROPOSED | APPROVED | REJECTED
""".strip()


def connect(readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=10)
    else:
        conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _fmt(dt: datetime) -> str:
    return dt.strftime(TS_FMT)


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, TS_FMT).replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------- seeding
def seed(force: bool = False) -> None:
    """Create and populate the database with a synthetic fleet and 12h of history."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        if not force:
            return
        DB_PATH.unlink()

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    now = now - timedelta(minutes=now.minute % TICK_MINUTES)

    with closing(connect()) as conn, conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO cold_storage_facilities VALUES (?,?,?,?,?,?,?,?,?,?)", fleet_data.FACILITIES
        )
        for spec in fleet_data.SHIPMENTS:
            wps = spec["waypoints"]
            hours_done = spec["progress"] * spec["hours_total"]
            departed = now - timedelta(hours=hours_done)
            eta = departed + timedelta(hours=spec["hours_total"])
            conn.execute(
                "INSERT INTO shipments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    spec["shipment_id"], spec["cargo"], spec["cargo_class"], spec["customer"],
                    wps[0][0], wps[-1][0], spec["truck_id"], spec["driver"], spec["setpoint_c"],
                    spec["cargo_value_usd"], spec["pallets"], _fmt(departed), _fmt(eta),
                    spec["hours_total"], round(spec["progress"] * 100, 1), "IN_TRANSIT",
                ),
            )
            conn.executemany(
                "INSERT INTO route_waypoints VALUES (?,?,?,?,?)",
                [(spec["shipment_id"], i, n, la, lo) for i, (n, la, lo) in enumerate(wps)],
            )
            n_readings = min(48, int(hours_done * 60 / TICK_MINUTES) + 1)
            rows = []
            for k in range(n_readings - 1, -1, -1):
                h = hours_done - k * TICK_MINUTES / 60
                ts = now - timedelta(minutes=k * TICK_MINUTES)
                rows.append(_reading_row(spec, h, ts))
            conn.executemany(_INSERT_TLM, rows)


_INSERT_TLM = (
    "INSERT INTO telemetry (shipment_id, ts, lat, lon, cargo_temp_c, ambient_temp_c, humidity_pct,"
    " door_open, speed_kmh, reefer_status, battery_pct) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
)


def _reading_row(spec: dict, hours_since_departure: float, ts: datetime) -> tuple:
    pts = [(la, lo) for _, la, lo in spec["waypoints"]]
    lat, lon, _ = route_position(pts, hours_since_departure / spec["hours_total"])
    r = fleet_data.sensor_reading(spec, hours_since_departure, lat, ts.hour + ts.minute / 60)
    return (
        spec["shipment_id"], _fmt(ts), round(lat, 5), round(lon, 5), r["cargo_temp_c"],
        r["ambient_temp_c"], r["humidity_pct"], r["door_open"], r["speed_kmh"],
        r["reefer_status"], r["battery_pct"],
    )


def simulate_tick() -> str:
    """Advance the fleet clock one tick and stream a new reading for every truck in transit."""
    with closing(connect()) as conn, conn:
        clock = _parse(conn.execute("SELECT MAX(ts) FROM telemetry").fetchone()[0])
        new_clock = clock + timedelta(minutes=TICK_MINUTES)
        for row in conn.execute("SELECT * FROM shipments WHERE status='IN_TRANSIT'").fetchall():
            spec = fleet_data.shipment_by_id(row["shipment_id"])
            if spec is None:
                continue
            hours_done = (new_clock - _parse(row["departed_at"])).total_seconds() / 3600
            progress = min(hours_done / spec["hours_total"], 1.0)
            conn.execute(_INSERT_TLM, _reading_row(spec, min(hours_done, spec["hours_total"]), new_clock))
            conn.execute(
                "UPDATE shipments SET progress_pct=?, status=? WHERE shipment_id=?",
                (round(progress * 100, 1), "DELIVERED" if progress >= 1 else "IN_TRANSIT", row["shipment_id"]),
            )
    return _fmt(new_clock)


# --------------------------------------------------------------------------- queries
def fleet_clock() -> str:
    with closing(connect(readonly=True)) as conn:
        return conn.execute("SELECT MAX(ts) FROM telemetry").fetchone()[0]


def get_shipment(shipment_id: str) -> dict | None:
    with closing(connect(readonly=True)) as conn:
        row = conn.execute(
            "SELECT * FROM shipments WHERE UPPER(shipment_id)=UPPER(?)", (shipment_id.strip(),)
        ).fetchone()
        return dict(row) if row else None


def get_waypoints(shipment_id: str) -> list[dict]:
    with closing(connect(readonly=True)) as conn:
        rows = conn.execute(
            "SELECT seq, name, lat, lon FROM route_waypoints WHERE shipment_id=? ORDER BY seq",
            (shipment_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def telemetry_df(shipment_id: str | None = None, hours: float | None = None) -> pd.DataFrame:
    sql, params = "SELECT * FROM telemetry", []
    clauses = []
    if shipment_id:
        clauses.append("shipment_id=?")
        params.append(shipment_id)
    if hours:
        cutoff = _parse(fleet_clock()) - timedelta(hours=hours)
        clauses.append("ts>=?")
        params.append(_fmt(cutoff))
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY shipment_id, ts"
    with closing(connect(readonly=True)) as conn:
        df = pd.read_sql_query(sql, conn, params=params)
    df["ts"] = pd.to_datetime(df["ts"])
    return df


def fleet_overview_df() -> pd.DataFrame:
    sql = """
    SELECT s.*, t.ts AS last_ts, t.lat, t.lon, t.cargo_temp_c, t.ambient_temp_c, t.door_open,
           t.speed_kmh, t.reefer_status, t.battery_pct
    FROM shipments s
    JOIN telemetry t ON t.id = (SELECT id FROM telemetry WHERE shipment_id=s.shipment_id
                                ORDER BY ts DESC LIMIT 1)
    ORDER BY s.shipment_id
    """
    with closing(connect(readonly=True)) as conn:
        return pd.read_sql_query(sql, conn)


def route_progress(shipment_id: str, lat: float, lon: float) -> dict:
    """Where the truck sits on its planned route + remaining distance."""
    shp = get_shipment(shipment_id)
    wps = get_waypoints(shipment_id)
    pts = [(w["lat"], w["lon"]) for w in wps]
    total = route_length_km(pts)
    frac = (shp["progress_pct"] or 0) / 100
    _, _, nxt = route_position(pts, frac)
    remaining_km = total * (1 - frac)
    hours_left = shp["planned_hours"] * (1 - frac)
    projected_eta = _parse(fleet_clock()) + timedelta(hours=hours_left)
    return {
        "route_total_km": round(total, 1),
        "remaining_km": round(remaining_km, 1),
        "next_waypoint": wps[nxt]["name"],
        "km_to_next_waypoint": round(haversine_km(lat, lon, wps[nxt]["lat"], wps[nxt]["lon"]), 1),
        "remaining_waypoints": [w["name"] for w in wps[nxt:]],
        "hours_remaining": round(hours_left, 2),
        "projected_eta_utc": _fmt(projected_eta),
        "planned_eta_utc": shp["planned_eta"],
    }


def remaining_route_points(shipment_id: str) -> list[dict]:
    """Waypoints not yet passed, each with hours-until-arrival."""
    shp = get_shipment(shipment_id)
    wps = get_waypoints(shipment_id)
    pts = [(w["lat"], w["lon"]) for w in wps]
    frac = (shp["progress_pct"] or 0) / 100
    seg = [0.0] + [haversine_km(*pts[i], *pts[i + 1]) for i in range(len(pts) - 1)]
    cum = [sum(seg[: i + 1]) for i in range(len(seg))]
    total = cum[-1] or 1
    out = []
    for w, c in zip(wps, cum):
        wfrac = c / total
        if wfrac > frac:
            out.append({**w, "hours_until_arrival": round((wfrac - frac) * shp["planned_hours"], 2)})
    return out


def nearest_facilities(lat: float, lon: float, cargo_class: str, k: int = 3) -> list[dict]:
    with closing(connect(readonly=True)) as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM cold_storage_facilities").fetchall()]
    hits = []
    for r in rows:
        if cargo_class not in r["supported_classes"].split(","):
            continue
        d = haversine_km(lat, lon, r["lat"], r["lon"])
        hits.append({**r, "distance_km": round(d, 1), "est_drive_hours": round(d / 80, 2)})
    return sorted(hits, key=lambda x: x["distance_km"])[:k]


_FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum)\b", re.I)


def run_readonly_sql(sql: str, max_rows: int = 60) -> dict:
    stmt = sql.strip().rstrip(";")
    if ";" in stmt:
        return {"error": "Only a single statement is allowed."}
    if not re.match(r"^(select|with)\b", stmt, re.I) or _FORBIDDEN.search(stmt):
        return {"error": "Only read-only SELECT/WITH queries are permitted."}
    try:
        with closing(connect(readonly=True)) as conn:
            cur = conn.execute(stmt)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchmany(max_rows + 1)
    except sqlite3.Error as exc:
        return {"error": f"SQL error: {exc}"}
    return {
        "columns": cols,
        "rows": [list(r) for r in rows[:max_rows]],
        "truncated": len(rows) > max_rows,
    }


# --------------------------------------------------------------------------- dispatch actions
def log_action(shipment_id: str, action_type: str, priority: str, summary: str,
               rationale: str, sop_references: str, created_by: str = "FROST-AI") -> int:
    with closing(connect()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO dispatch_actions (created_at, shipment_id, action_type, priority, summary,"
            " rationale, sop_references, status, created_by) VALUES (?,?,?,?,?,?,?,?,?)",
            (fleet_clock(), shipment_id, action_type, priority, summary, rationale,
             sop_references, "PROPOSED", created_by),
        )
        return int(cur.lastrowid)


def actions_df(shipment_id: str | None = None) -> pd.DataFrame:
    sql, params = "SELECT * FROM dispatch_actions", []
    if shipment_id:
        sql += " WHERE shipment_id=?"
        params.append(shipment_id)
    sql += " ORDER BY action_id DESC"
    with closing(connect(readonly=True)) as conn:
        return pd.read_sql_query(sql, conn, params=params)


def set_action_status(action_id: int, status: str) -> None:
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE dispatch_actions SET status=? WHERE action_id=?", (status, action_id))
