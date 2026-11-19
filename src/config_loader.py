
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = PROJECT_ROOT / "config" / "settings.json"


def load_settings() -> dict[str, Any]:
    """Load application settings from config/settings.json."""

    if not SETTINGS_FILE.exists():
        raise FileNotFoundError(
            f"Settings file not found: {SETTINGS_FILE}"
        )

    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as file:
            settings = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Invalid JSON in {SETTINGS_FILE}: {error}"
        ) from error

    if not isinstance(settings, dict):
        raise ValueError("Settings must contain a JSON object.")

    search = settings.get("search")

    if not isinstance(search, dict):
        raise ValueError("Missing or invalid 'search' section.")

    initial_days = search.get("initial_lookback_days")
    daily_hours = search.get("daily_lookback_hours")
    minimum_score = search.get("minimum_fit_score")

    if (
        type(initial_days) is not int
        or initial_days < 1
    ):
        raise ValueError(
            "'initial_lookback_days' must be a positive integer."
        )

    if (
        type(daily_hours) is not int
        or daily_hours < 1
    ):
        raise ValueError(
            "'daily_lookback_hours' must be a positive integer."
        )

    if (
        type(minimum_score) is not int
        or not 0 <= minimum_score <= 100
    ):
        raise ValueError(
            "'minimum_fit_score' must be between 0 and 100."
        )

    return settings
