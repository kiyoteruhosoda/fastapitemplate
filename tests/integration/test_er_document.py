"""ER 図と実際の表の突き合わせ（ADR-0089）。

図はコードから生成せず手で書く（ADR-0072 §2）ので、表や列を足して図を直し忘れても何も起きない。
"""

from __future__ import annotations

import re
from pathlib import Path

from shared.kernel.database.db import Base

_ER = Path(__file__).resolve().parents[2] / "docs" / "ER.md"
_BLOCK = re.compile(r"^    (\w+) \{\n(.*?)^    \}", re.DOTALL | re.MULTILINE)


def _documented() -> dict[str, set[str]]:
    blocks = _BLOCK.findall(_ER.read_text(encoding="utf-8"))
    return {name: {line.split()[1] for line in body.splitlines() if line.strip()} for name, body in blocks}


def _actual() -> dict[str, set[str]]:
    return {table.name: {column.name for column in table.columns} for table in Base.metadata.tables.values()}


def test_every_table_is_in_the_er_diagram() -> None:
    assert set(_documented()) == set(_actual())


def test_every_column_is_in_the_er_diagram() -> None:
    documented = _documented()
    different = {
        name: columns ^ documented[name] for name, columns in _actual().items() if columns != documented.get(name)
    }
    assert not different, f"docs/ER.md と実際の列が違います: {different}"
