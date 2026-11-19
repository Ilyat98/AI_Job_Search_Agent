
"""Compare profiles extracted by a rule-based parser and an AI model.

The module does not decide which source is correct. It preserves matches,
differences, and possible conflicts for later review.
"""

import json
import re
from typing import Any


# These keys help identify an item without assuming a particular profession.
IDENTITY_KEYS = (
    "name",
    "skill",
    "title",
    "role",
    "language",
    "company",
)


def normalize_value(value: Any) -> str:
    """Convert a value to a normalized string for comparison."""
    if value is None:
        return ""

    text = str(value).casefold().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s+#./-]", "", text)
    return text


def _item_identity(item: Any) -> str:
    """Build a comparison key for a string or structured item."""
    if isinstance(item, dict):
        normalized_item = {
            str(key).casefold(): value
            for key, value in item.items()
        }

        parts = []
        for key in IDENTITY_KEYS:
            value = normalized_item.get(key)
            if value is not None and normalize_value(value):
                parts.append(f"{key}:{normalize_value(value)}")

        if parts:
            return "|".join(parts)

    # For items without a recognizable identity, compare the full value.
    return normalize_value(
        json.dumps(item, ensure_ascii=False, sort_keys=True)
        if isinstance(item, (dict, list))
        else item
    )


def reconcile_list(
    parser_items: list[Any],
    ai_items: list[Any],
) -> dict[str, list[Any]]:
    """Compare lists while preserving duplicate items."""
    parser_items = parser_items or []
    ai_items = ai_items or []

    def group_by_identity(items: list[Any]) -> dict[str, list[Any]]:
        """Group items without overwriting duplicates."""
        grouped: dict[str, list[Any]] = {}

        for item in items:
            identity = _item_identity(item)
            grouped.setdefault(identity, []).append(item)

        return grouped

    parser_groups = group_by_identity(parser_items)
    ai_groups = group_by_identity(ai_items)

    common = []
    parser_only = []
    ai_only = []
    conflicts = []

    all_identities = dict.fromkeys(
        [*parser_groups, *ai_groups]
    )

    for identity in all_identities:
        parser_group = list(parser_groups.get(identity, []))
        ai_group = list(ai_groups.get(identity, []))

        # First match completely identical items, including duplicates.
        remaining_ai = list(ai_group)

        unmatched_parser = []

        for parser_item in parser_group:
            try:
                index = remaining_ai.index(parser_item)
            except ValueError:
                unmatched_parser.append(parser_item)
            else:
                ai_item = remaining_ai.pop(index)
                common.append({
                    "parser": parser_item,
                    "ai": ai_item,
                })

        # Items with the same identity but different details are conflicts.
        while unmatched_parser and remaining_ai:
            parser_item = unmatched_parser.pop(0)
            ai_item = remaining_ai.pop(0)

            conflicts.append({
                "parser": parser_item,
                "ai": ai_item,
            })

        # Preserve any items without a counterpart.
        parser_only.extend(unmatched_parser)
        ai_only.extend(remaining_ai)

    return {
        "common": common,
        "parser_only": parser_only,
        "ai_only": ai_only,
        "conflicts": conflicts,
    }


def reconcile_profiles(
    parser_profile: dict[str, Any],
    ai_profile: dict[str, Any],
) -> dict[str, Any]:
    """Compare list-valued fields shared by two extracted profiles."""
    if not isinstance(parser_profile, dict):
        raise TypeError("parser_profile must be a dictionary")

    if not isinstance(ai_profile, dict):
        raise TypeError("ai_profile must be a dictionary")

    ignored_fields = {
        "raw_text",
        "source_file",
        "sections",
    }

    fields = (
        set(parser_profile)
        | set(ai_profile)
    ) - ignored_fields

    result = {
        "fields": {},
        "missing_from_parser": [],
        "missing_from_ai": [],
        "not_comparable": [],
    }

    for field in sorted(fields):
        parser_has_field = field in parser_profile
        ai_has_field = field in ai_profile

        if not parser_has_field:
            result["missing_from_parser"].append(field)
            continue

        if not ai_has_field:
            result["missing_from_ai"].append(field)
            continue

        parser_value = parser_profile[field]
        ai_value = ai_profile[field]

        if isinstance(parser_value, list) and isinstance(ai_value, list):
            result["fields"][field] = reconcile_list(
                parser_value,
                ai_value,
            )
        else:
            result["not_comparable"].append({
                "field": field,
                "parser": parser_value,
                "ai": ai_value,
                "reason": "Values are not both lists",
            })

    return result


if __name__ == "__main__":
    # Synthetic example only — no real CV data is used here.
    parser_example = {
        "skills": ["Python", "SQL", "Git"],
        "languages": [{"name": "English", "level": "B2"}],
    }

    ai_example = {
        "skills": ["Python", "Docker"],
        "languages": [{"name": "English", "level": "C1"}],
    }

    comparison = reconcile_profiles(parser_example, ai_example)
    print(json.dumps(comparison, ensure_ascii=False, indent=2))
