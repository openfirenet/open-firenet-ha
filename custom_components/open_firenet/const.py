from __future__ import annotations

DOMAIN = "open_firenet"

DEFAULT_SCAN_INTERVAL = 30  # seconds

API_STATE = "/api/state"
API_CONTROLS = "/api/controls"
API_SCHEDULE = "/api/schedule"

OPERATING_MODES = {
    0: "manual",
    1: "auto",
    2: "comfort",
}
OPERATING_MODES_REVERSE = {v: k for k, v in OPERATING_MODES.items()}

TEMP_MIN = 14.0
TEMP_MAX = 28.0
TEMP_STEP = 1.0

SETBACK_TEMP_MIN = 10.0
SETBACK_TEMP_MAX = 25.0
SETBACK_TEMP_STEP = 0.5

FROST_TEMP_MIN = 4.0
FROST_TEMP_MAX = 10.0
FROST_TEMP_STEP = 1.0

DOMO_BACK_MODEL_ID = 23
BAKE_TEMP_MIN = 130
BAKE_TEMP_MAX = 340
BAKE_TEMP_STEP = 5

ROOM_OFFSET_MIN = -4.0
ROOM_OFFSET_MAX = 4.0
ROOM_OFFSET_STEP = 0.1

HEATING_POWER_MIN = 30
HEATING_POWER_MAX = 100
HEATING_POWER_STEP = 5

MULTIAIR_TRIM_MIN = -30
MULTIAIR_TRIM_MAX = 30
MULTIAIR_TRIM_STEP = 5

MULTIAIR_LEVELS = ["auto", "1", "2", "3", "4", "5"]

STOVE_MODELS: dict[int, str] = {
    1: "INDUO",
    2: "TOPO",
    3: "ROCO",
    4: "ROCO MULTIAIR",
    5: "ROCO RAO",
    6: "KAPO",
    7: "MIRO",
    8: "COMO",
    9: "REVO",
    10: "INTERNO",
    11: "FILO",
    12: "SUMO",
    13: "DOMO",
    14: "CORSO",
    15: "INDUO II",
    16: "REVIVO",
    17: "PARO",
    18: "LIVO",
    19: "COMO II",
    20: "REVO II",
    21: "COSMO",
    22: "SONO",
    23: "DOMO BACK",
    24: "PK E",
    25: "SUMO MULTIAIR",
    26: "CONNECT",
    29: "PRIMO",
}

MULTIAIR_MODELS: set[int] = {4, 13, 17, 23, 25, 29}


def get_model_name(model_id: int | None, fallback: str | None = None) -> str:
    """Return the commercial name of the stove model."""
    if fallback:
        return fallback
    if model_id is not None and model_id in STOVE_MODELS:
        return STOVE_MODELS[model_id]
    return f"Model {model_id}" if model_id is not None else "Unknown"


def is_multiair_supported(data: dict) -> bool:
    """Check if the stove hardware supports MultiAir forced convection fans."""
    if not isinstance(data, dict):
        return False
    stove = data.get("stove", {})
    controls = data.get("controls", {})
    model_id = stove.get("model")
    return (
        model_id in MULTIAIR_MODELS
        or "convection_fan1_active" in controls
        or "convectionFan1Active" in controls
    )


def is_bake_supported(data: dict) -> bool:
    """Check if the stove hardware supports a baking oven (DOMO BACK)."""
    if not isinstance(data, dict):
        return False
    stove = data.get("stove", {})
    model_id = stove.get("model")
    model_name = stove.get("model_name")
    return model_id == DOMO_BACK_MODEL_ID or model_name == "DOMO BACK"
