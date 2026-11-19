
import pytest

from src.profile_reconciler import reconcile_list, reconcile_profiles


def test_empty_lists():
    result = reconcile_list([], [])

    assert result == {
        "common": [],
        "parser_only": [],
        "ai_only": [],
        "conflicts": [],
    }


def test_preserves_duplicate_items():
    result = reconcile_list(
        ["Python", "Python"],
        ["Python"],
    )

    assert len(result["common"]) == 1
    assert result["parser_only"] == ["Python"]
    assert result["ai_only"] == []
    assert result["conflicts"] == []


def test_detects_conflicting_language_levels():
    result = reconcile_list(
        [{"name": "English", "level": "B2"}],
        [{"name": "English", "level": "C1"}],
    )

    assert result["common"] == []
    assert result["parser_only"] == []
    assert result["ai_only"] == []
    assert result["conflicts"] == [
        {
            "parser": {"name": "English", "level": "B2"},
            "ai": {"name": "English", "level": "C1"},
        }
    ]


def test_keeps_unmatched_items_from_both_sources():
    result = reconcile_list(
        ["Python", "SQL"],
        ["Python", "Docker"],
    )

    assert len(result["common"]) == 1
    assert result["parser_only"] == ["SQL"]
    assert result["ai_only"] == ["Docker"]


def test_empty_profile_fields_are_comparable():
    result = reconcile_profiles(
        {"skills": []},
        {"skills": []},
    )

    assert result["fields"]["skills"] == {
        "common": [],
        "parser_only": [],
        "ai_only": [],
        "conflicts": [],
    }


def test_different_field_types_are_not_comparable():
    result = reconcile_profiles(
        {"skills": ["Python"]},
        {"skills": "Python"},
    )

    assert result["not_comparable"] == [
        {
            "field": "skills",
            "parser": ["Python"],
            "ai": "Python",
            "reason": "Values are not both lists",
        }
    ]


def test_missing_field_is_reported():
    result = reconcile_profiles(
        {"skills": ["Python"]},
        {"languages": []},
    )

    assert result["missing_from_parser"] == ["languages"]
    assert result["missing_from_ai"] == ["skills"]


def test_invalid_profile_raises_type_error():
    with pytest.raises(TypeError):
        reconcile_profiles([], {})
