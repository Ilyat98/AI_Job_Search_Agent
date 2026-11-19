"""Build bounded, role-specific search phrases from the available CVs."""

from __future__ import annotations

from typing import Any

from src.job_matcher import profile_role_terms


def build_search_plan(
    profiles: list[dict[str, Any]], settings: dict[str, Any]
) -> dict[str, Any]:
    """Return initial terms, safe title synonyms, and CV tracks represented."""
    source_config = settings.get("job_sources", {})
    configured_terms = source_config.get("search_terms", [])
    role_terms = list(dict.fromkeys(
        role
        for profile in profiles
        for role in profile_role_terms(profile.get("ai_profile") or {})
    ))
    preferences = settings.get("user_preferences", {})
    preferred_roles = preferences.get("preferred_roles", []) if isinstance(preferences, dict) else []
    initial_terms = list(dict.fromkeys([
        *configured_terms, *role_terms, *preferred_roles,
    ]))

    role_tracks = source_config.get("role_search_tracks", {})
    experience_text = " ".join(role_terms).casefold()
    represented_tracks: dict[str, list[str]] = {}
    allowed_titles: list[str] = []
    expansion_terms: list[str] = []
    for track_name, track in role_tracks.items():
        if not isinstance(track, dict):
            continue
        cues = track.get("cues", [])
        if not any(str(cue).casefold() in experience_text for cue in cues):
            continue
        terms = [str(term).strip() for term in track.get("search_terms", []) if str(term).strip()]
        represented_tracks[track_name] = terms
        allowed_titles.extend(terms)
        expansion_terms.extend(terms)

    seen = {" ".join(str(term).casefold().split()) for term in initial_terms}
    expansion_terms = list(dict.fromkeys(
        term for term in expansion_terms
        if " ".join(term.casefold().split()) not in seen
    ))
    target_titles = list(dict.fromkeys([
        *(settings.get("job_keywords") or settings.get("job_categories", [])),
        *role_terms,
        *preferred_roles,
        *allowed_titles,
    ]))
    return {
        "initial_terms": initial_terms,
        "expansion_terms": expansion_terms,
        "target_titles": target_titles,
        "tracks": represented_tracks,
    }
