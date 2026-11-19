
import logging
from typing import Any

from src.cv_parser import discover_cv_files
from src.profile_builder import build_profile
from src.ai_profile_extractor import extract_ai_profile
from src.database import (
    init_db,
    save_cv_profile,
    save_ai_profile,
    get_cv_profiles,
    count_cv_profiles, update_ai_status,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

logger = logging.getLogger(__name__)



def process_all_cvs() -> int:
    """
    Extract text from CVs, create AI profiles with Ollama,
    and save the results to SQLite.

    Returns the number of CVs whose text was successfully processed
    and whose basic record was saved.
    """
    cv_files = discover_cv_files()
    saved_count = 0

    for cv_path in cv_files:
        logger.info("Processing CV: %s", cv_path.name)

        # Step 1: Extract raw text from the PDF.
        try:
            profile = build_profile(cv_path)

        except (OSError, ValueError):
            logger.exception(
                "Could not extract text from CV '%s'.",
                cv_path.name,
            )
            continue

        # Step 2: Save the source record in SQLite.
        try:
            save_cv_profile(profile)
            saved_count += 1

        except (OSError, RuntimeError, ValueError):
            logger.exception(
                "Could not save the source record for '%s'.",
                cv_path.name,
            )
            continue

        print(f"\nCV text saved: {cv_path.name}")

        # Step 3: Extract structured facts using local Ollama.
        try:
            ai_profile = extract_ai_profile(profile["raw_text"])

            # Step 4: Save the AI profile and mark it as successful.
            save_ai_profile(
                profile["source_file"],
                ai_profile,
            )

            print(f"AI profile saved: {cv_path.name}")

        except (OSError, RuntimeError, ValueError) as exc:
            # Determine which status should be saved.
            error_message = str(exc).lower()

            if (
                "timed out" in error_message
                or "timeout" in error_message
            ):
                status = "timeout"
            else:
                status = "error"

            # Save the failed attempt without deleting the old AI profile.
            try:
                update_ai_status(
                    profile["source_file"],
                    status,
                )

            except (OSError, RuntimeError, ValueError):
                logger.exception(
                    "Could not update AI status for '%s'.",
                    cv_path.name,
                )

            logger.exception(
                "Could not create or save AI profile for '%s'.",
                cv_path.name,
            )

            print(
                f"AI profile processing failed ({status}): "
                f"{cv_path.name}"
            )

    return saved_count




def print_ai_profile(
    source_file: str,
    ai_profile: dict[str, Any] | None,
    ai_status: str = "not_processed",
) -> None:
    """Display the AI profile and the status of its latest processing attempt."""
    print(f"\nCV: {source_file}")

    if ai_status == "success" and ai_profile is not None:
        print("AI profile: available (latest processing successful)")

    elif ai_status == "timeout":
        print("AI profile: latest processing timed out")
        if ai_profile is not None:
            print("A previous AI profile is stored, but may be outdated.")
        return

    elif ai_status == "error":
        print("AI profile: latest processing failed")
        if ai_profile is not None:
            print("A previous AI profile is stored, but may be outdated.")
        return

    elif ai_profile is None:
        print("AI profile: unavailable")
        return

    else:
        print("AI profile: not confirmed as successfully processed")
        return

    for field in (
        "skills",
        "interests",
        "languages",
        "experience",
        "education",
        "certificates",
        "projects",
        "unknowns",
    ):
        if field in ai_profile:
            print(f"{field.capitalize()}: {ai_profile[field]}")



def main() -> None:
    """Initialize SQLite, process CVs, and display AI profiles."""
    init_db()

    saved_count = process_all_cvs()
    profiles = get_cv_profiles()

    print("\n" + "=" * 60)
    print(f"CV source records saved this run: {saved_count}")
    print(f"Total CV records in database: {count_cv_profiles()}")

    print("\nAI profile results:")

    for profile in profiles:
        print_ai_profile(
            source_file=profile["source_file"],
            ai_profile=profile.get("ai_profile"),
            ai_status=profile.get("ai_status", "not_processed"),
        )


if __name__ == "__main__":
    main()
