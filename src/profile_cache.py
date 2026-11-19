"""Validate cached AI CV profiles against the current source documents."""

from __future__ import annotations

from typing import Any

from src.ai_profile_extractor import validate_profile
from src.cv_parser import discover_cv_files
from src.database import get_cv_profiles
from src.profile_builder import build_profile


class ProfileCacheError(RuntimeError):
    """Raised when the no-analysis command cannot safely reuse CV profiles."""


def load_current_profiles(*, strict: bool = True) -> list[dict[str, Any]]:
    """Read CV files and accept only successful profiles for unchanged text."""
    cv_files = discover_cv_files()
    if not cv_files:
        raise ProfileCacheError("No supported CV files were found in the CV folder.")

    stored_by_name = {
        profile["source_file"]: profile
        for profile in get_cv_profiles()
    }
    usable: list[dict[str, Any]] = []
    problems: list[str] = []

    for cv_path in cv_files:
        try:
            current = build_profile(cv_path)
        except (OSError, RuntimeError, ValueError) as error:
            problems.append(f"{cv_path.name}: could not read CV ({error})")
            continue

        saved = stored_by_name.get(cv_path.name)
        if saved is None:
            problems.append(f"{cv_path.name}: profile has not been saved")
            continue
        if saved.get("raw_text") != current.get("raw_text"):
            problems.append(f"{cv_path.name}: file changed after analysis")
            continue
        if saved.get("ai_status") != "success":
            problems.append(f"{cv_path.name}: latest AI analysis did not complete successfully")
            continue

        ai_profile = saved.get("ai_profile")
        if not isinstance(ai_profile, dict):
            problems.append(f"{cv_path.name}: structured profile is missing")
            continue
        try:
            validate_profile(ai_profile)
        except ValueError as error:
            problems.append(f"{cv_path.name}: profile is incomplete ({error})")
            continue

        usable.append(saved)

    if strict and problems:
        details = "\n- ".join(problems)
        raise ProfileCacheError(
            "The profile cache is incomplete or out of date. Run the full mode "
            "`python -m src.job_search`.\n- " + details
        )
    if not usable:
        details = "\n- ".join(problems)
        raise ProfileCacheError(
            "No current AI profile is available for job matching.\n- "
            + details
        )
    return usable
