"""Consistency of the frontend dictionaries.

A missing translation only shows up as "displayed in English", which is easy to miss, so the
key sets are compared mechanically. The frontend is too small to justify adding a test runner
for this, so it is checked here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_DICTIONARY_DIR = Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n"
_REFERENCE = "en"


def _load(locale: str) -> dict[str, str]:
    loaded: dict[str, str] = json.loads((_DICTIONARY_DIR / f"{locale}.json").read_text(encoding="utf-8"))
    return loaded


def _translated_locales() -> list[str]:
    return sorted(path.stem for path in _DICTIONARY_DIR.glob("*.json") if path.stem != _REFERENCE)


@pytest.mark.parametrize("locale", _translated_locales())
def test_translations_cover_every_english_key(locale: str) -> None:
    reference = _load(_REFERENCE)
    translated = _load(locale)

    missing = sorted(set(reference) - set(translated))
    assert not missing, f"{locale}.json  is missing translations: {missing}"

    orphaned = sorted(set(translated) - set(reference))
    assert not orphaned, f"{locale}.json  still has keys that were removed from en.json: {orphaned}"


@pytest.mark.parametrize("locale", _translated_locales())
def test_placeholders_match_the_english_message(locale: str) -> None:
    """A placeholder such as ``{keys}`` must be identical in the translation, or it cannot be filled in."""
    import re

    pattern = re.compile(r"\{(\w+)\}")
    reference = _load(_REFERENCE)
    translated = _load(locale)

    for key, message in reference.items():
        expected = set(pattern.findall(message))
        actual = set(pattern.findall(translated[key]))
        assert expected == actual, f"Placeholders of {key} in {locale}.json do not match"
