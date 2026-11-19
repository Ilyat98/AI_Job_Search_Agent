"""Deterministic first-pass vacancy filters and candidate fit score."""

from __future__ import annotations

import html
import re
import unicodedata
from datetime import date
from typing import Any


ROLE_TERMS = (
    "quality assurance",
    "qa engineer",
    "qa tester",
    "manual qa",
    "automation qa",
    "software tester",
    "test engineer",
    "test automation",
    "integration testing",
    "tester",
    "test specialist",
    "software testing",
    "junior qa",
    "junior tester",
    "tester manualny",
    "inżynier testów",
    "testowanie oprogramowania",
)

ROLE_ENDINGS = {
    "engineer", "designer", "technician", "developer", "tester",
    "analyst", "specialist", "manager", "architect", "administrator",
    "operator", "technologist", "programmer", "artist", "producer",
    "inżynier", "inzynier", "projektant", "projektantka", "technik",
    "techniczka", "specjalista", "specjalistka", "programista",
    "programistka", "analityk", "analityczka", "kierownik",
    "kierowniczka", "інженер", "інженерка", "дизайнер", "технік",
    "фахівець", "аналітик", "розробник", "тестувальник", "инженер",
    "дизайнер", "техник", "специалист", "аналитик", "разработчик",
    "тестировщик",
}

_REQUIREMENTS_HEADINGS = (
    "requirements", "requirements and qualifications", "required skills",
    "required qualifications", "required experience", "required technologies",
    "must have", "must haves", "must-haves",
    "what you need", "what you'll need", "what we expect",
    "what we expect from you", "what we are looking for", "your profile",
    "what we're looking for",
    "your qualifications", "your skills",
    "our ideal candidate possesses the following skills",
    "desired experience",
    "you have these superpowers", "what is important to us",
    "what matters to us", "realizacje projektu ułatwi ci",
    "наш метч, якщо ти", "наш мэтч, если ты",
    "wymagania", "nasze wymagania", "wymagania konieczne",
    "wymagane kwalifikacje", "czego oczekujemy", "czego wymagamy",
    "oczekiwania", "wymagania obowiązkowe", "wymagane technologie",
    "вимоги", "обов'язкові вимоги", "требования", "обязательные требования",
    "що для нас важливо",
)
_OPTIONAL_OR_OTHER_HEADINGS = (
    "nice to have", "good to have", "preferred", "desirable",
    "bonus points", "mile widziane", "dodatkowe atuty",
    "будет большим плюсом", "будет преимуществом", "будет плюсом",
    "бажано", "буде великим плюсом", "буде плюсом", "буде перевагою",
    "responsibilities", "what you will do", "your responsibilities",
    "what you'll do", "what you'll be doing",
    "що потрібно робити", "що будеш робити", "обов'язки",
    "чем предстоит заниматься", "что нужно делать",
    "obowiązki", "zakres obowiązków", "we offer", "what we offer",
    "benefits", "oferujemy", "co oferujemy",
)
_MANDATORY_CUES = re.compile(
    r"\b(?:must[ -]?have|required|mandatory|essential|must be proficient|"
    r"wymagany|wymagana|wymagane|obowiązkow\w*|niezbędn\w*|"
    r"обов['’]?язков\w*|необхідн\w*|обязательн\w*)\b",
    re.I,
)
_NEGATED_MANDATORY = re.compile(
    r"\b(?:not required|not mandatory|not essential|not a must[ -]?have|"
    r"not a requirement|не обязательно|"
    r"nie jest wymagane|niewymagane)\b",
    re.I,
)
_EXPERIENCE_YEARS = re.compile(
    r"(?P<years>\d+)(?:\s*(?:\+|plus|[-–—]\s*\d+))?\s*"
    r"(?:years?|yrs?|рок(?:и|ів|у)?|lat)\b",
    re.I,
)
_DATE_RANGE = re.compile(
    r"(?P<start>(?:(?:0?[1-9]|1[0-2])\s*/\s*)?\d{4})\s*"
    r"(?:-|–|—|\bto\b|\buntil\b)\s*"
    r"(?P<end>(?:(?:0?[1-9]|1[0-2])\s*/\s*)?\d{4}|present|current|now|currently)",
    re.I,
)


def profile_role_terms(profile: dict[str, Any]) -> list[str]:
    """Infer searchable role phrases from this profile's experience entries."""
    found: set[str] = set()
    for item in profile.get("experience", []) or []:
        if not isinstance(item, str):
            continue
        text = re.sub(r"\b\d{1,2}/\d{4}\b|\b\d{4}\b|present\b", " ", item, flags=re.I)
        chunks = re.split(r"\s+(?:at|@|—|–|-)\s+|,", text, maxsplit=3, flags=re.I)
        for chunk in chunks:
            words = re.findall(r"[\w+#/.]+", chunk, flags=re.UNICODE)
            role_positions = [
                index for index, word in enumerate(words)
                if word.casefold() in ROLE_ENDINGS
            ]
            for index in role_positions:
                for start in range(max(0, index - 2), index + 1):
                    for end in range(start + 2, min(len(words), start + 4) + 1):
                        if index >= end:
                            continue
                        phrase_words = words[start:end]
                        if not any(word.casefold() in ROLE_ENDINGS for word in phrase_words):
                            continue
                        phrase = " ".join(phrase_words).strip(" -,:()")
                        if phrase and not any(char.isdigit() for char in phrase):
                            found.add(phrase)
    return sorted(found, key=lambda phrase: (-len(phrase.split()), phrase.casefold()))


def _plain_text(value: str | None) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def _normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold().replace("’", "'"))
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _contains_skill(text: str, term: str) -> bool:
    """Match a configured skill as a phrase, avoiding Java/JavaScript overlap."""
    normalized_text = _normalized(text)
    normalized_term = _normalized(term).strip()
    if not normalized_term:
        return False
    if normalized_term == "c":
        return re.search(r"(?<![\w+#])c(?![\w+#])", normalized_text) is not None
    pattern = rf"(?<![\w]){re.escape(normalized_term)}(?![\w])"
    return re.search(pattern, normalized_text) is not None


def _requirement_lines(description: str) -> list[str]:
    """Collect explicit required sections and sentences from a job description."""
    text = html.unescape(description or "")
    text = re.sub(
        r"<\s*br\s*/?\s*>|</\s*(?:p|li|div|h[1-6]|ul|ol)\s*>",
        "\n", text, flags=re.I,
    )
    text = re.sub(r"<\s*(?:li|div)\b[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[•▪◦]", "\n", text)
    text = text.replace("’", "'").replace("‘", "'")
    headings = sorted(
        (*_REQUIREMENTS_HEADINGS, *_OPTIONAL_OR_OTHER_HEADINGS),
        key=len,
        reverse=True,
    )
    heading_pattern = re.compile(
        r"(?i)(?<![\w])(" + "|".join(re.escape(item) for item in headings) + r")(?P<delimiter>\s*[:?])?"
    )

    def split_heading(match: re.Match[str]) -> str:
        remainder = text[match.end():].lstrip()
        starts_section = bool(
            match.group("delimiter")
            or (remainder and (remainder[0].isupper() or remainder[0].isdigit()))
        )
        if not starts_section:
            return match.group(0)
        return f"\n{match.group(1)}:\n"

    text = heading_pattern.sub(split_heading, text)
    lines = [" ".join(line.split()).strip(" •▪◦\t") for line in text.splitlines()]

    collected: list[str] = []
    in_required_section = False
    for line in lines:
        if not line:
            continue
        heading = _normalized(line).strip(" :.-")
        if any(
            heading == _normalized(item)
            or heading.startswith(_normalized(item) + ":")
            for item in _OPTIONAL_OR_OTHER_HEADINGS
        ):
            in_required_section = False
            continue
        requirement_heading = next((
            _normalized(item) for item in _REQUIREMENTS_HEADINGS
            if heading == _normalized(item) or heading.startswith(_normalized(item) + ":")
        ), None)
        if requirement_heading is not None:
            in_required_section = True
            if ":" in line:
                inline_text = line.split(":", 1)[1].strip()
                if inline_text:
                    collected.append(inline_text)
            continue
        if in_required_section:
            collected.append(line)
        elif _MANDATORY_CUES.search(line) and not _NEGATED_MANDATORY.search(line):
            collected.append(line)
    return collected


def find_required_skills(
    job: dict[str, Any], skill_aliases: dict[str, list[str]]
) -> list[str]:
    """Find catalogued skills stated in an explicitly mandatory context."""
    required_text = "\n".join(_requirement_lines(str(job.get("description") or "")))
    matched: list[tuple[str, str]] = []
    for canonical, aliases in skill_aliases.items():
        variants = [canonical, *(aliases if isinstance(aliases, list) else [])]
        matched_variant = next((
            str(alias) for alias in variants
            if _contains_skill(required_text, str(alias))
        ), None)
        if matched_variant:
            matched.append((canonical, matched_variant))

    # Avoid charging twice for a specific term and its broader catalog entry,
    # such as "React.js" and "React" or "GitLab CI" and "GitLab".
    required: list[str] = []
    for canonical, variant in matched:
        covered_by_specific_term = any(
            canonical != other_canonical
            and len(other_variant) > len(variant)
            and _contains_skill(other_variant, variant)
            for other_canonical, other_variant in matched
        )
        if not covered_by_specific_term:
            required.append(canonical)
    return required


def _experience_scope(job: dict[str, Any], requirement_line: str) -> str:
    text = _normalized(
        f"{job.get('title') or ''} {requirement_line}"
    )
    if re.search(r"\b(?:qa|aqa|quality assurance|test(?:er|ing)?|validation)\b|тест", text):
        return "qa"
    if re.search(r"\b(?:game|gameplay|game design)\b|геймдизайн|игр", text):
        return "game"
    if re.search(r"\b(?:technical support|it support|support engineer|customer support)\b|підтрим|поддерж", text):
        return "support"
    if re.search(r"\b(?:developer|development|programmer|software engineering)\b|розроб", text):
        return "development"
    return "general"


def _experience_text_matches_scope(value: str, scope: str) -> bool:
    text = _normalized(value)
    patterns = {
        "qa": r"\b(?:qa|aqa|quality assurance|test(?:er|ing)?|validation)\b|тест|тестув|випробув",
        "game": r"\b(?:game|gameplay|game design|level design)\b|геймдизайн|ігров|игров",
        "support": r"\b(?:technical support|it support|support engineer|customer support)\b|технічн.{0,12}підтрим|техническ.{0,12}поддерж",
        "development": r"\b(?:developer|development|programmer|software engineer)\b|розробник|програміст",
        "general": r".+",
    }
    return re.search(patterns.get(scope, patterns["general"]), text) is not None


def _date_month(value: str, *, is_end: bool = False) -> int:
    value = value.strip().casefold()
    if value in {"present", "current", "currently", "now"}:
        today = date.today()
        return today.year * 12 + today.month
    match = re.fullmatch(r"(?:(\d{1,2})\s*/\s*)?(\d{4})", value)
    if not match:
        raise ValueError(f"Unsupported experience date: {value}")
    month = int(match.group(1) or (12 if is_end else 1))
    year = int(match.group(2))
    # Convert the inclusive end month to an exclusive boundary.
    return year * 12 + month + (1 if is_end else 0)


def _experience_months(profile: dict[str, Any], scope: str) -> int | None:
    intervals: list[tuple[int, int]] = []
    saw_matching_role = False
    for item in profile.get("experience", []) or []:
        if not isinstance(item, str) or not _experience_text_matches_scope(item, scope):
            continue
        saw_matching_role = True
        for match in _DATE_RANGE.finditer(item):
            try:
                start = _date_month(match.group("start"))
                end = _date_month(match.group("end"), is_end=True)
            except ValueError:
                continue
            if end > start:
                intervals.append((start, end))
    if not intervals:
        return 0 if saw_matching_role else None

    intervals.sort()
    total = 0
    start, end = intervals[0]
    for next_start, next_end in intervals[1:]:
        if next_start <= end:
            end = max(end, next_end)
        else:
            total += end - start
            start, end = next_start, next_end
    return total + end - start


def missing_required_experience(
    job: dict[str, Any], profile: dict[str, Any]
) -> list[str]:
    """Report explicit minimum years that the dated CV experience cannot support."""
    required_text = _requirement_lines(str(job.get("description") or ""))
    requirements: list[tuple[int, str]] = []
    for line in required_text:
        match = _EXPERIENCE_YEARS.search(line)
        if not match:
            continue
        years = int(match.group("years"))
        if years:
            requirements.append((years, _experience_scope(job, line)))

    missing = []
    for years, scope in requirements:
        months = _experience_months(profile, scope)
        label = {"qa": "QA/AQA", "game": "game design", "support": "technical support", "development": "software development"}.get(scope, "related work")
        if months is None:
            missing.append(
                f"Experience in {label}: requires {years}+ years; relevant experience is not confirmed in the CV"
            )
        elif months < years * 12:
            actual = f"{months // 12} y {months % 12} mo." if months >= 12 else f"{months} mo."
            missing.append(
                f"Experience in {label}: requires {years}+ years; the CV shows about {actual}"
            )
    return list(dict.fromkeys(missing))


def seniority_mismatch_warning(
    job: dict[str, Any], profile: dict[str, Any]
) -> str | None:
    """Return a soft warning when dated relevant experience is below the title level."""
    title = _normalized(str(job.get("title") or ""))
    if re.search(r"\b(?:lead|principal|staff|head|director|chief)\b", title):
        level, expected_months = "Lead/Senior", 48
    elif re.search(r"\b(?:senior|sr\.?|seniorka|starszy|starsza|старш\w*)\b", title):
        level, expected_months = "Senior", 36
    elif re.search(r"\b(?:mid|middle|medior)\b", title):
        level, expected_months = "Middle", 12
    else:
        return None

    scope = _experience_scope(job, "")
    months = _experience_months(profile, scope)
    if months is None:
        return f"Level {level}: relevant experience duration is not confirmed by dates in the CV"
    if months >= expected_months:
        return None
    actual = f"{months // 12} y {months % 12} mo." if months >= 12 else f"{months} mo."
    return f"Level {level}: in the CV about {actual} of relevant experience"


def missing_required_skills(
    required: list[str],
    profile: dict[str, Any],
    skill_aliases: dict[str, list[str]],
    *,
    job: dict[str, Any] | None = None,
) -> list[str]:
    candidate_facts = "\n".join(
        item
        for field in ("skills", "experience")
        for item in (profile.get(field) or [])
        if isinstance(item, str)
    )
    missing = []
    description = _normalized(str((job or {}).get("description") or ""))
    for canonical in required:
        aliases = skill_aliases.get(canonical, [])
        variants = [canonical, *(aliases if isinstance(aliases, list) else [])]
        if any(_contains_skill(candidate_facts, str(alias)) for alias in variants):
            continue

        # Treat alternatives stated explicitly by the employer as equivalent.
        if canonical == "JavaScript" and re.search(
            r"javascript.{0,80}or (?:another|other) scripting language",
            description,
        ):
            scripting_languages = ("Python", "Bash", "PowerShell", "Lua", "Ruby", "PHP")
            if any(_contains_skill(candidate_facts, language) for language in scripting_languages):
                continue
        if canonical == "PostgreSQL" and re.search(
            r"postgres(?:ql)?\s*\(\s*or another relational db\s*\)",
            description,
        ):
            relational_databases = ("SQL", "MySQL", "SQLite", "MariaDB", "Oracle")
            if any(_contains_skill(candidate_facts, database) for database in relational_databases):
                continue
        missing.append(canonical)
    return missing


def is_target_role(job: dict[str, Any], keywords: list[str] | None = None) -> bool:
    title = _normalized(_plain_text(job.get("title")))
    terms = list(ROLE_TERMS)
    if keywords:
        terms.extend(_normalized(item) for item in keywords)
    return any(_has_phrase(title, term) for term in terms)


def _has_phrase(text: str, phrase: str) -> bool:
    normalized_text = _normalized(text)
    normalized_phrase = _normalized(phrase).strip()
    if not normalized_phrase:
        return False
    pattern = rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)"
    return re.search(pattern, normalized_text) is not None


def score_job_for_profile(
    job: dict[str, Any], profile: dict[str, Any]
) -> tuple[int, list[str]]:
    """Return a transparent 0–100 fit index, not an employment probability."""
    title = _plain_text(job.get("title"))
    body = _plain_text(job.get("description"))
    job_text = f"{title} {body}"
    reasons: list[str] = []

    profile_roles = profile_role_terms(profile)
    if is_target_role(job):
        role_points = 30
        reasons.append("Title matches QA / testing")
    elif profile_roles and is_target_role(job, profile_roles):
        role_points = 30
        reasons.append("Title matches a role in the CV experience")
    elif any(_has_phrase(job_text, term) for term in ROLE_TERMS):
        role_points = 10
        reasons.append("QA / testing is mentioned in the description")
    else:
        role_points = 0

    skills = profile.get("skills", [])
    matched_skills = [
        skill for skill in skills
        if isinstance(skill, str) and _has_phrase(job_text, skill)
    ]
    skill_points = round(50 * min(len(set(matched_skills)) / 6, 1))
    if matched_skills:
        reasons.append("Skills: " + ", ".join(dict.fromkeys(matched_skills[:6])))

    experience_items = profile.get("experience", [])
    experience_text = " ".join(item for item in experience_items if isinstance(item, str))
    has_related_experience = any(
        _has_phrase(experience_text, role) for role in profile_roles
    ) or any(term in _normalized(experience_text) for term in (
        "qa", "quality assurance", "tester", "test engineer",
        "software testing", "validation engineer",
    ))
    experience_points = 15 if has_related_experience else 0
    if has_related_experience:
        reasons.append("The CV includes experience in a related role")

    required_languages = []
    normalized_body = _normalized(body)
    for language in (profile.get("languages") or []):
        if not isinstance(language, dict):
            continue
        name = language.get("name")
        if isinstance(name, str) and _has_phrase(normalized_body, name):
            required_languages.append(name)
    if required_languages:
        language_points = 5
        reasons.append("Languages listed in the CV appear in the vacancy: " + ", ".join(required_languages))
    else:
        language_points = 0

    return min(100, role_points + skill_points + experience_points + language_points), reasons


def score_job(
    job: dict[str, Any],
    profiles: list[dict[str, Any]],
    *,
    skill_aliases: dict[str, list[str]] | None = None,
    missing_skill_penalty: int = 15,
    max_required_skill_penalty: int = 45,
    seniority_mismatch_penalty: int = 10,
) -> dict[str, Any]:
    """Choose the best CV and reduce its score for unmet explicit requirements."""
    skill_aliases = skill_aliases or {}
    required = find_required_skills(job, skill_aliases)
    candidates = []
    for profile in profiles:
        ai_profile = profile.get("ai_profile")
        if not isinstance(ai_profile, dict):
            continue
        score, reasons = score_job_for_profile(job, ai_profile)
        missing = missing_required_skills(
            required, ai_profile, skill_aliases, job=job
        )
        experience_missing = missing_required_experience(job, ai_profile)
        missing.extend(experience_missing)
        missing = list(dict.fromkeys(missing))
        penalty = min(len(missing) * missing_skill_penalty, max_required_skill_penalty)
        level_warning = seniority_mismatch_warning(job, ai_profile)
        # Explicit year requirements already incur a hard requirement penalty;
        # avoid charging a second soft seniority penalty for the same gap.
        level_penalty = (
            max(0, seniority_mismatch_penalty)
            if level_warning and not experience_missing else 0
        )
        adjusted_score = max(0, score - penalty - level_penalty)
        if missing:
            reasons.append(
                "Unconfirmed mandatory requirements: " + ", ".join(missing)
                + f" (−{penalty} points)"
            )
        if level_warning:
            reasons.append("Seniority warning: " + level_warning)
        candidates.append((
            len(missing), adjusted_score, profile.get("source_file", ""),
            reasons, missing, [level_warning] if level_warning else [], level_penalty,
        ))

    if not candidates:
        return {
            **job,
            "fit_score": 0,
            "recommended_cv": None,
            "match_explanation": "[]",
            "missing_requirements": required,
            "fit_warnings": [],
            "seniority_penalty": 0,
            "rejection_reason": None,
        }

    _, score, recommended_cv, reasons, missing, fit_warnings, level_penalty = min(
        candidates, key=lambda item: (item[0], -item[1])
    )
    return {
        **job,
        "fit_score": score,
        "recommended_cv": recommended_cv,
        "match_explanation": "; ".join(reasons),
        "missing_requirements": missing,
        "fit_warnings": fit_warnings,
        "seniority_penalty": level_penalty,
        "rejection_reason": None,
    }
