"""フロントエンド辞書の整合性。

翻訳の抜けは「英語のまま表示される」だけで気付きにくいので、キー集合の
一致を機械的に見る。フロントエンドにテストランナーを足すほどの規模ではない
ため、ここで確認する。
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
    assert not missing, f"{locale}.json に訳がありません: {missing}"

    orphaned = sorted(set(translated) - set(reference))
    assert not orphaned, f"{locale}.json に en.json 側で消えたキーが残っています: {orphaned}"


@pytest.mark.parametrize("locale", _translated_locales())
def test_placeholders_match_the_english_message(locale: str) -> None:
    """``{keys}`` のようなプレースホルダは訳文でも同じでなければ差し込めない。"""
    import re

    pattern = re.compile(r"\{(\w+)\}")
    reference = _load(_REFERENCE)
    translated = _load(locale)

    for key, message in reference.items():
        expected = set(pattern.findall(message))
        actual = set(pattern.findall(translated[key]))
        assert expected == actual, f"{locale}.json の {key} のプレースホルダが一致しません"
