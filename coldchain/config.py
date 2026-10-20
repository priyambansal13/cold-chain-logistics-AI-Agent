"""Central configuration for the Cold-Chain Dispatch Console."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "telemetry.db"
SOP_DIR = DATA_DIR / "sops"
VECTOR_INDEX_PATH = DATA_DIR / "sop_vector_index.json"

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
AVAILABLE_MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-5", "gpt-5-mini"]

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
HTTP_TIMEOUT_S = 12

# Simulated minutes of fleet time per telemetry tick.
TICK_MINUTES = 15

# Mirror of SOP-TC-001 used ONLY for UI colouring/charts. The agent never reads
# this table: it must retrieve limits from the SOP rulebook via vector RAG.
CARGO_PROFILES = {
    "FROZEN": {"label": "Frozen Foods", "min_c": -22.0, "max_c": -18.0},
    "DEEP_FROZEN": {"label": "Deep Frozen / Ice Cream", "min_c": -28.0, "max_c": -23.0},
    "CHILLED": {"label": "Chilled Seafood & Dairy", "min_c": 0.0, "max_c": 4.0},
    "PHARMA": {"label": "Pharmaceuticals 2–8 °C", "min_c": 2.0, "max_c": 8.0},
    "FRESH_PRODUCE": {"label": "Fresh Produce", "min_c": 1.0, "max_c": 7.0},
}
ALERT_MARGIN_C = 0.5

# Demo scenario: overlay a synthetic heatwave on live weather data.
HEATWAVE_REGIONS = {
    "US Southwest (AZ / NM / NV / S. CA)": {"lat": (31.0, 37.6), "lon": (-120.5, -104.0)},
    "US Southeast (GA / FL)": {"lat": (24.5, 34.5), "lon": (-87.5, -79.5)},
    "US South-Central (TX / OK / AR)": {"lat": (29.0, 37.0), "lon": (-103.0, -89.5)},
    "US Pacific Northwest / N. CA": {"lat": (38.0, 48.5), "lon": (-124.5, -120.0)},
}
