"""One-shot pipeline: CV profiles, configured sources, ranking, and Excel."""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src import database
from src.cv_service import process_all_cvs
from src.config_loader import load_settings
from src.excel_exporter import OUTPUT_PATH, export_jobs
from src.job_matcher import is_target_role, profile_role_terms, score_job
from src.job_evaluator import (
    combine_job_assessments,
    evaluate_job_with_ollama,
    evaluation_fingerprint,
)
from src.job_sources.registry import fetch_enabled_sources
from src.profile_cache import ProfileCacheError, load_current_profiles
from src.calibration import calibrate_threshold, load_feedback
from src.search_planner import build_search_plan

logger = logging.getLogger(__name__)


class VacancyFilterError(RuntimeError):
    """Raised for an invalid or unsupported vacancy search configuration."""


def _as_datetime(value: str, timezone_name: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed.astimezone(timezone.utc)


def _lookback_cutoff(settings: dict[str, Any]) -> datetime:
    timezone_name = settings["app"]["timezone"]
    now = datetime.now(ZoneInfo(timezone_name)).astimezone(timezone.utc)
    if database.is_initial_search():
        return now - timedelta(days=settings["search"]["initial_lookback_days"])
    return now - timedelta(hours=settings["search"]["daily_lookback_hours"])


def _within_lookback(
    job: dict[str, Any], cutoff: datetime, timezone_name: str
) -> bool:
    published_at = job.get("published_at")
    if not published_at:
        # Unknown publication dates are retained, but Excel shows a dash.
        return True
    parsed = _as_datetime(published_at, timezone_name)
    return parsed is None or parsed >= cutoff


def filter_relevant_listings(
    items: list[dict[str, Any]],
    target_keywords: list[str],
    cutoff: datetime,
    timezone_name: str,
) -> tuple[list[dict[str, Any]], int]:
    """Filter titles using established target roles, not planner query phrases."""
    role_matches = [
        job for job in items
        if job.get("status") != "closed"
        and is_target_role(job, target_keywords)
    ]
    relevant = [
        job for job in role_matches
        if _within_lookback(job, cutoff, timezone_name)
    ]
    return relevant, len(role_matches)


def _rule_fallback(
    job: dict[str, Any],
    profiles: list[dict[str, Any]],
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Keep the search useful when local Ollama cannot evaluate vacancies."""
    matching = settings.get("job_matching", {})
    result = score_job(
        job,
        profiles,
        skill_aliases=matching.get("required_skill_aliases", {}),
        missing_skill_penalty=int(matching.get("missing_required_skill_penalty", 15)),
        max_required_skill_penalty=int(matching.get("max_required_skill_penalty", 45)),
        seniority_mismatch_penalty=int(
            settings.get("agent", {}).get("seniority_mismatch_penalty", 10)
        ),
    )
    score = int(result.get("fit_score") or 0)
    possible = int(settings.get("agent", {}).get("possible_match_min_score", 55))
    if score >= possible:
        decision = "Possible match (rules fallback)"
    else:
        decision = "Weak match (rules fallback)"
    result.update({
        "ai_decision": decision,
        "ai_summary": result.get("match_explanation") or "Ollama evaluation unavailable.",
        "evaluation_source": "Rules (fallback)",
        "evaluation_confidence": "low",
        "evaluation_requirements": [],
        "preferred_gaps": [],
    })
    return result


def _evaluate_listings(
    jobs: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
    settings: dict[str, Any],
) -> tuple[list[dict[str, Any]], bool, int, int]:
    """Use cached/local AI assessments, falling back to deterministic scores on failure."""
    ai_config = settings.get("ai", {})
    model = str(ai_config.get("model") or "")
    ai_enabled = ai_config.get("enabled") is True
    ollama_failed = not ai_enabled
    ai_count = 0
    cache_count = 0
    results = []

    for index, job in enumerate(jobs, start=1):
        fingerprint = evaluation_fingerprint(
            job,
            profiles,
            model=model,
            user_preferences=settings.get("user_preferences", {}),
            job_matching=settings.get("job_matching", {}),
            endpoint=str(ai_config.get("base_url") or ""),
            max_description_chars=int(
                settings.get("agent", {}).get("max_description_chars", 9000)
            ),
        )
        cached = database.get_cached_job_evaluation(
            str(job.get("normalized_url") or ""), fingerprint
        )
        assessments = cached.get("assessments") if cached else None
        if isinstance(assessments, list):
            cache_count += 1
        elif ai_enabled and not ollama_failed:
            try:
                if ai_count % 5 == 0:
                    print(f"Ollama is evaluating vacancies: {index}/{len(jobs)}…")
                assessments = evaluate_job_with_ollama(
                    job, profiles, settings=settings
                )
                if all(
                    item.get("evaluation_source") != "Rules"
                    for item in assessments
                ):
                    database.save_cached_job_evaluation(
                        str(job.get("normalized_url") or ""),
                        fingerprint,
                        {"assessments": assessments},
                    )
                ai_count += 1
            except (OSError, RuntimeError) as error:
                ollama_failed = True
                logger.warning("Ollama job evaluation failed; using rule fallback: %s", error)
                print("Warning: Ollama is unavailable; using rule-based fallback for this and remaining new vacancies.")
            except (ValueError, TypeError) as error:
                # A malformed model response is local to this vacancy. Continue
                # asking Ollama about subsequent listings instead of disabling
                # AI evaluation for the entire batch.
                logger.warning(
                    "Invalid Ollama response for one vacancy; using rule fallback "
                    "for this vacancy only: %s",
                    error,
                )
                print("Warning: Ollama returned an invalid assessment for this vacancy; continuing with the next one.")

        if isinstance(assessments, list):
            try:
                result = combine_job_assessments(
                    job, profiles, assessments, settings=settings
                )
            except (ValueError, TypeError, KeyError) as error:
                logger.warning("Invalid cached/local job assessment; using rule fallback: %s", error)
                result = _rule_fallback(job, profiles, settings)
                result["evaluation_source"] = "Rules (fallback: invalid Ollama response)"
        else:
            result = _rule_fallback(job, profiles, settings)
        results.append(result)
    return results, ollama_failed, ai_count, cache_count


def run_pipeline(
    *,
    analyze_profiles: bool = True,
    clear_profile_cache: bool = False,
    output_path: str | Path = OUTPUT_PATH,
) -> Path:
    """Run CV validation, source searches, ranking, database upserts, and export."""
    settings = load_settings()
    database.init_db()
    agent_settings = settings.setdefault("agent", {})
    default_possible_threshold = int(agent_settings.get("possible_match_min_score", 55))
    feedback_rows = load_feedback(
        agent_settings.get("feedback_file", "data/job_feedback.csv")
    )
    possible_threshold, calibration = calibrate_threshold(
        feedback_rows,
        default_threshold=default_possible_threshold,
        minimum_per_class=int(agent_settings.get("feedback_min_examples_per_class", 3)),
    )
    agent_settings["possible_match_min_score"] = possible_threshold

    if analyze_profiles:
        if clear_profile_cache:
            print("Clearing saved CV profiles; keeping vacancy history…")
            database.clear_cv_profiles()
        print("Analyzing current CVs with local Ollama…")
        process_all_cvs()
        profiles = load_current_profiles(strict=clear_profile_cache)
    else:
        print("Checking cached AI profiles against the current CVs…")
        profiles = load_current_profiles(strict=True)
    print(f"Ready CV profiles: {len(profiles)}")
    if calibration["active"]:
        print(
            "Score threshold calibrated from feedback: "
            f"{possible_threshold} (apply: {calibration['positive']}, "
            f"reject: {calibration['negative']}; balanced accuracy: "
            f"{calibration['balanced_accuracy']:.0%})."
        )
    else:
        print(
            "Score calibration is inactive: "
            f"{calibration['positive']} apply labels and "
            f"{calibration['negative']} reject labels; "
            f"using default threshold {possible_threshold}."
        )

    cutoff = _lookback_cutoff(settings)
    timezone_name = settings["app"]["timezone"]
    search_plan = build_search_plan(profiles, settings)
    search_terms = list(search_plan["initial_terms"])
    profile_roles = [
        role
        for profile in profiles
        for role in profile_role_terms(profile.get("ai_profile") or {})
    ]
    preferences = settings.get("user_preferences", {})
    preferred_roles = preferences.get("preferred_roles", []) if isinstance(preferences, dict) else []
    if search_plan["tracks"]:
        print("CV-supported search tracks: " + ", ".join(
            f"{track} ({', '.join(terms)})"
            for track, terms in search_plan["tracks"].items()
        ))
    listings, source_errors, succeeded = fetch_enabled_sources(
        settings, search_terms=search_terms, since=cutoff
    )
    agent_warnings: list[str] = []
    target_keywords = list(dict.fromkeys([
        *(settings.get("job_keywords") or settings.get("job_categories", [])),
        *profile_roles,
        *preferred_roles,
        *search_plan["target_titles"],
    ]))
    relevant, role_match_count = filter_relevant_listings(
        listings, target_keywords, cutoff, timezone_name
    )
    print(f"Listings received: {len(listings)}; matching target roles: {role_match_count}; within date range: {len(relevant)}")
    scored_jobs, ollama_failed, _, _ = _evaluate_listings(relevant, profiles, settings)

    max_replans = max(0, int(agent_settings.get("max_replans", 1)))
    replan_threshold = max(1, int(agent_settings.get("replan_if_fewer_acceptable", 8)))
    possible_threshold = int(agent_settings.get("possible_match_min_score", 55))
    for replan_number in range(max_replans):
        acceptable = sum(
            job.get("evaluation_source") == "Ollama"
            and int(job.get("fit_score") or 0) >= possible_threshold
            and job.get("ai_decision") != "Not a match"
            for job in scored_jobs
        )
        if acceptable >= replan_threshold or ollama_failed:
            break
        searched = {" ".join(term.casefold().split()) for term in search_terms}
        extra_terms = [
            term for term in search_plan["expansion_terms"]
            if " ".join(term.casefold().split()) not in searched
        ][:int(agent_settings.get("max_replan_terms", 12))]
        if not extra_terms:
            break
        print(
            f"Only plausible vacancies so far: {acceptable}; expanding search "
            f"with CV-supported role synonyms ({replan_number + 1}/{max_replans}): "
            f"{', '.join(extra_terms)}"
        )
        search_terms.extend(extra_terms)
        try:
            extra_listings, extra_errors, extra_succeeded = fetch_enabled_sources(
                settings, search_terms=extra_terms, since=cutoff
            )
        except (OSError, RuntimeError, ValueError) as error:
            source_errors.append(f"Expanded search: {error}")
            break
        source_errors.extend(extra_errors)
        succeeded = list(dict.fromkeys([*succeeded, *extra_succeeded]))
        listings_by_url = {
            str(job.get("normalized_url") or job.get("url")): job
            for job in listings
        }
        for job in extra_listings:
            key = str(job.get("normalized_url") or job.get("url"))
            listings_by_url.setdefault(key, job)
        listings = list(listings_by_url.values())
        relevant, role_match_count = filter_relevant_listings(
            listings, target_keywords, cutoff, timezone_name
        )
        print(
            f"After expanded search: listings {len(listings)}, "
            f"relevant by role/date {len(relevant)}"
        )
        scored_jobs, ollama_failed, _, _ = _evaluate_listings(
            relevant, profiles, settings
        )

    per_source: dict[str, int] = {}
    for listing in listings:
        source = str(listing.get("source") or "unknown")
        per_source[source] = per_source.get(source, 0) + 1
    print("Listings by source: " + ", ".join(
        f"{source}: {count}" for source, count in sorted(per_source.items())
    ))
    evaluation_sources: dict[str, int] = {}
    for job in scored_jobs:
        source = str(job.get("evaluation_source") or "unknown")
        evaluation_sources[source] = evaluation_sources.get(source, 0) + 1
    if evaluation_sources:
        print("Evaluated: " + ", ".join(
            f"{source}: {count}" for source, count in sorted(evaluation_sources.items())
        ))

    with_missing_required_skills = sum(
        bool(job.get("missing_requirements")) for job in scored_jobs
    )
    if with_missing_required_skills:
        print(
            "Vacancies with score reduced for mandatory requirements: "
            f"{with_missing_required_skills}"
        )
    minimum_score = settings["search"].get("minimum_fit_score", 0)
    include_no_match = bool(agent_settings.get("include_no_match_in_excel", False))
    report_jobs = [
        job for job in scored_jobs
        if int(job.get("fit_score") or 0) >= minimum_score
        and job.get("ai_decision") not in {"Not a match", "Manual review"}
        and (
            include_no_match
            or "weak match" not in str(job.get("ai_decision") or "").casefold()
        )
    ]
    review_min_score = max(0, possible_threshold - 15)
    review_limit = max(0, int(agent_settings.get("near_miss_report_limit", 10)))
    review_jobs = sorted(
        (
            job for job in scored_jobs
            if job.get("ai_decision") == "Manual review"
            or (
                job.get("evaluation_source") == "Ollama"
                and job.get("ai_decision") == "Not a match"
                and int(job.get("fit_score") or 0) >= review_min_score
            )
        ),
        key=lambda item: (int(item.get("fit_score") or 0), item.get("published_at") or ""),
        reverse=True,
    )[:review_limit]
    review_urls = {
        str(job.get("normalized_url") or job.get("url") or "")
        for job in review_jobs
    }
    excluded_no_match = sum(
        job.get("evaluation_source") == "Ollama"
        and job.get("ai_decision") == "Not a match"
        and str(job.get("normalized_url") or job.get("url") or "") not in review_urls
        for job in scored_jobs
    )
    previously_seen = database.get_existing_job_urls(
        [
            job.get("normalized_url", "")
            for job in [*report_jobs, *review_jobs]
        ]
    )
    report_jobs = [
        {**job, "previously_seen": job.get("normalized_url") in previously_seen}
        for job in report_jobs
    ]
    review_jobs = [
        {
            **job,
            "previously_seen": job.get("normalized_url") in previously_seen,
            "report_decision_label": (
                job.get("ai_decision") if job.get("ai_decision") == "Manual review"
                else "Manual review (low confidence)"
            ),
        }
        for job in review_jobs
    ]
    for job in scored_jobs:
        database.save_job(job)

    export_rows = [*report_jobs, *review_jobs]
    # Keep the first worksheet useful even when the model recommends no direct
    # matches: include manual-review candidates there with an explicit status,
    # and add the focused review worksheet as a convenience view.
    workbook_path = export_jobs(
        export_rows,
        output_path=output_path,
        review_jobs=review_jobs,
    )
    if not source_errors:
        if database.is_initial_search():
            database.mark_initial_search_completed()
        else:
            database.set_state("last_successful_search_at", database.current_timestamp())

    print(f"Sources responding: {', '.join(succeeded)}")
    if source_errors:
        print("Some sources were unavailable; the search is not marked complete:")
        for error in source_errors:
            print(f"- {error}")
    if agent_warnings:
        print("Agent warnings:")
        for warning in agent_warnings:
            print(f"- {warning}")
    if review_jobs:
        print(
            f"Candidates for manual review in Excel: {len(review_jobs)}"
        )
    print(
        f"Rows in Excel: {len(export_rows)} "
        f"(agent recommendations: {len(report_jobs)}; "
        f"manual review: {len(review_jobs)}; evaluated: {len(scored_jobs)})"
    )
    if excluded_no_match and not include_no_match:
        print(
            "Rejected by Ollama and excluded from Excel "
            f"(excluding manual-review candidates): {excluded_no_match}"
        )
    print(f"Excel file: {workbook_path}")
    return workbook_path


def _confirm_profile_rebuild() -> bool:
    """Ask before deleting incomplete/stale cached CV profiles."""
    yes_answers = {"yes", "y"}
    no_answers = {"no", "n"}
    while True:
        try:
            answer = input(
                "Rebuild all CV profiles? The local profile cache will be deleted; "
                "CV files and vacancy history will be kept [yes/no]: "
            ).strip().casefold()
        except EOFError:
            return False
        if answer in yes_answers:
            return True
        if answer in no_answers:
            return False
        print("Enter yes or no.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search jobs against current CV profiles and export Excel"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--reuse-profiles",
        action="store_true",
        help="Use saved profiles; ask whether to rebuild them if missing or stale",
    )
    mode.add_argument(
        "--reanalyze",
        action="store_true",
        help="Delete cached CV profiles and analyze every current CV again",
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_PATH),
        help="Excel output path (default: data/vacancies.xlsx)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    try:
        if args.reuse_profiles:
            try:
                run_pipeline(analyze_profiles=False, output_path=args.output)
            except ProfileCacheError as error:
                print(f"\nWARNING: saved CV profiles are incomplete or out of date.\n{error}")
                if not _confirm_profile_rebuild():
                    print("Search cancelled. No data was changed.")
                    return
                run_pipeline(
                    analyze_profiles=True,
                    clear_profile_cache=True,
                    output_path=args.output,
                )
        else:
            run_pipeline(
                analyze_profiles=True,
                clear_profile_cache=args.reanalyze,
                output_path=args.output,
            )
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"Job search failed: {error}\n")


if __name__ == "__main__":
    main()
