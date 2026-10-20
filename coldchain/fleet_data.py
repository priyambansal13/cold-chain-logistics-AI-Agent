"""Synthetic fleet definition + sensor physics used to seed and stream telemetry.

The simulation profiles below are intentionally kept OUT of the database so the
AI copilot has to discover anomalies from raw telemetry, not read the answer.
"""
from __future__ import annotations

import math
import random

SHIPMENTS = [
    {
        "shipment_id": "A42",
        "cargo": "Frozen Atlantic Salmon Fillets",
        "cargo_class": "FROZEN",
        "customer": "Desert Fresh Markets",
        "truck_id": "TRK-1042",
        "driver": "M. Alvarez",
        "setpoint_c": -20.5,
        "cargo_value_usd": 184_000,
        "pallets": 22,
        "hours_total": 27.0,
        "progress": 0.58,
        "profile": "nominal",
        "waypoints": [
            ("Chicago, IL", 41.8781, -87.6298),
            ("St. Louis, MO", 38.6270, -90.1994),
            ("Oklahoma City, OK", 35.4676, -97.5164),
            ("Amarillo, TX", 35.2220, -101.8313),
            ("Albuquerque, NM", 35.0844, -106.6504),
            ("Flagstaff, AZ", 35.1983, -111.6513),
            ("Phoenix, AZ", 33.4484, -112.0740),
        ],
    },
    {
        "shipment_id": "B17",
        "cargo": "mRNA Influenza Vaccines",
        "cargo_class": "PHARMA",
        "customer": "Lone Star Health System",
        "truck_id": "TRK-2217",
        "driver": "K. Okafor",
        "setpoint_c": 5.0,
        "cargo_value_usd": 2_350_000,
        "pallets": 8,
        "hours_total": 8.0,
        "progress": 0.62,
        "profile": "door_event",
        "waypoints": [
            ("Memphis, TN", 35.1495, -90.0490),
            ("Little Rock, AR", 34.7465, -92.2896),
            ("Texarkana, TX", 33.4251, -94.0477),
            ("Dallas, TX", 32.7767, -96.7970),
        ],
    },
    {
        "shipment_id": "C08",
        "cargo": "Fresh Dungeness Crab & Oysters",
        "cargo_class": "CHILLED",
        "customer": "Golden Bay Seafood Co.",
        "truck_id": "TRK-3108",
        "driver": "S. Nakamura",
        "setpoint_c": 2.0,
        "cargo_value_usd": 96_000,
        "pallets": 14,
        "hours_total": 13.0,
        "progress": 0.45,
        "profile": "nominal",
        "waypoints": [
            ("Seattle, WA", 47.6062, -122.3321),
            ("Portland, OR", 45.5152, -122.6784),
            ("Medford, OR", 42.3265, -122.8756),
            ("Redding, CA", 40.5865, -122.3917),
            ("Sacramento, CA", 38.5816, -121.4944),
        ],
    },
    {
        "shipment_id": "D23",
        "cargo": "Premium Ice Cream (Gelato Line)",
        "cargo_class": "DEEP_FROZEN",
        "customer": "Coastal Grocers Inc.",
        "truck_id": "TRK-4023",
        "driver": "J. Whitfield",
        "setpoint_c": -25.5,
        "cargo_value_usd": 71_500,
        "pallets": 24,
        "hours_total": 10.5,
        "progress": 0.50,
        "profile": "drift",
        "waypoints": [
            ("Atlanta, GA", 33.7490, -84.3880),
            ("Macon, GA", 32.8407, -83.6324),
            ("Jacksonville, FL", 30.3322, -81.6557),
            ("Orlando, FL", 28.5383, -81.3792),
            ("Miami, FL", 25.7617, -80.1918),
        ],
    },
    {
        "shipment_id": "E11",
        "cargo": "Monoclonal Antibody Biologics",
        "cargo_class": "PHARMA",
        "customer": "Delaware Valley Oncology",
        "truck_id": "TRK-5011",
        "driver": "R. Chen",
        "setpoint_c": 5.0,
        "cargo_value_usd": 4_800_000,
        "pallets": 4,
        "hours_total": 6.0,
        "progress": 0.40,
        "profile": "nominal",
        "waypoints": [
            ("Boston, MA", 42.3601, -71.0589),
            ("Hartford, CT", 41.7658, -72.6734),
            ("New York, NY", 40.7128, -74.0060),
            ("Philadelphia, PA", 39.9526, -75.1652),
        ],
    },
    {
        "shipment_id": "F05",
        "cargo": "Organic Strawberries & Blueberries",
        "cargo_class": "FRESH_PRODUCE",
        "customer": "Strip Fresh Hospitality Group",
        "truck_id": "TRK-6005",
        "driver": "L. Martinez",
        "setpoint_c": 3.5,
        "cargo_value_usd": 58_000,
        "pallets": 20,
        "hours_total": 7.0,
        "progress": 0.35,
        "profile": "heat_stress",
        "waypoints": [
            ("Fresno, CA", 36.7378, -119.7871),
            ("Bakersfield, CA", 35.3733, -119.0187),
            ("Barstow, CA", 34.8958, -117.0173),
            ("Las Vegas, NV", 36.1699, -115.1398),
        ],
    },
]

FACILITIES = [
    ("CS-OKC", "PolarLink Cold Storage", "Oklahoma City, OK", 35.4200, -97.5500, "FROZEN,DEEP_FROZEN,CHILLED,FRESH_PRODUCE", 0, 140, 1, "+1-405-555-0142"),
    ("CS-AMA", "FrostPoint Logistics", "Amarillo, TX", 35.1900, -101.8500, "FROZEN,DEEP_FROZEN,CHILLED", 0, 60, 1, "+1-806-555-0177"),
    ("CS-ABQ", "Mesa Cold Hub", "Albuquerque, NM", 35.0600, -106.6200, "FROZEN,DEEP_FROZEN,CHILLED,FRESH_PRODUCE,PHARMA", 1, 85, 1, "+1-505-555-0119"),
    ("CS-FLG", "Canyon Reefer Depot", "Flagstaff, AZ", 35.1900, -111.6200, "FROZEN,CHILLED", 0, 30, 0, "+1-928-555-0163"),
    ("CS-PHX", "Sonoran Cold Chain Center", "Phoenix, AZ", 33.4300, -112.0000, "FROZEN,DEEP_FROZEN,CHILLED,FRESH_PRODUCE,PHARMA", 1, 210, 1, "+1-602-555-0101"),
    ("CS-LIT", "Delta BioCold", "Little Rock, AR", 34.7400, -92.2900, "PHARMA,CHILLED", 1, 25, 1, "+1-501-555-0188"),
    ("CS-TXK", "Lone Star Cold", "Texarkana, TX", 33.4300, -94.0500, "FROZEN,CHILLED,FRESH_PRODUCE,PHARMA", 1, 40, 1, "+1-903-555-0124"),
    ("CS-JAX", "Gulf Freeze Terminal", "Jacksonville, FL", 30.3300, -81.6600, "FROZEN,DEEP_FROZEN", 0, 95, 1, "+1-904-555-0156"),
    ("CS-ORL", "Sunshine Deep Freeze", "Orlando, FL", 28.5400, -81.3800, "FROZEN,DEEP_FROZEN,CHILLED", 0, 70, 1, "+1-407-555-0133"),
    ("CS-MFR", "Cascade Cold Dock", "Medford, OR", 42.3300, -122.8700, "CHILLED,FRESH_PRODUCE", 0, 35, 0, "+1-541-555-0170"),
    ("CS-BSW", "Mojave Fresh Cross-Dock", "Barstow, CA", 34.9000, -117.0200, "FRESH_PRODUCE,CHILLED", 0, 50, 1, "+1-760-555-0109"),
    ("CS-EWR", "Keystone GDP Pharma Hub", "Newark, NJ", 40.7300, -74.1700, "PHARMA", 1, 30, 1, "+1-973-555-0191"),
]

# Door-open spike shape: hours relative to the seed point -> (temp delta, door open)
_DOOR_SPIKE = {-1.75: (3.2, 1), -1.5: (4.6, 1), -1.25: (2.1, 0), -1.0: (0.9, 0)}


def shipment_by_id(shipment_id: str) -> dict | None:
    return next((s for s in SHIPMENTS if s["shipment_id"] == shipment_id), None)


def sensor_reading(spec: dict, hours_since_departure: float, lat: float, utc_hour: float) -> dict:
    """Generate one physically plausible reefer sensor reading."""
    seed_h = spec["progress"] * spec["hours_total"]
    rel_h = round((hours_since_departure - seed_h) * 4) / 4  # hours relative to seed time
    rng = random.Random(f"{spec['shipment_id']}-{round(hours_since_departure * 4)}")
    setpoint = spec["setpoint_c"]
    profile = spec["profile"]

    temp = setpoint + rng.gauss(0, 0.3)
    door = 0
    reefer = "OK"
    # Synthetic trailer-exterior ambient: latitude gradient + diurnal swing (local ≈ UTC-6).
    local_h = (utc_hour - 6) % 24
    ambient = 31 - 0.65 * (lat - 30) + 6.5 * math.sin(2 * math.pi * (local_h - 9) / 24) + rng.gauss(0, 0.8)

    if profile == "door_event" and rel_h in _DOOR_SPIKE:
        delta, door = _DOOR_SPIKE[rel_h]
        temp = setpoint + delta + rng.gauss(0, 0.15)
    elif profile == "drift":
        drift_h = hours_since_departure - (seed_h - 4.0)
        if drift_h > 0:
            temp = setpoint + min(0.55 * drift_h, 12.0) + rng.gauss(0, 0.12)
            reefer = "DEGRADED" if drift_h < 6 else "FAULT"
    elif profile == "heat_stress":
        ambient += 7.0
        stress_h = hours_since_departure - (seed_h - 3.0)
        if stress_h > 0:
            temp = setpoint + 0.6 * stress_h + rng.gauss(0, 0.15)
            reefer = "HIGH_LOAD"

    return {
        "cargo_temp_c": round(temp, 2),
        "ambient_temp_c": round(ambient, 1),
        "humidity_pct": round(min(98, max(40, 82 + rng.gauss(0, 5))), 1),
        "door_open": door,
        "speed_kmh": 0.0 if door else round(max(0, 88 + rng.gauss(0, 6)), 1),
        "reefer_status": reefer,
        "battery_pct": round(max(20, 100 - hours_since_departure * 1.4), 1),
    }
