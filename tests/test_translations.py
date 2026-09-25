"""Every translation file must cover exactly the keys of strings.json (English source)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

BASE = Path(__file__).parent.parent / "custom_components" / "open_firenet"


def _paths(obj, prefix=""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from _paths(value, f"{prefix}/{key}")
    else:
        yield prefix


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("lang", sorted(p.stem for p in (BASE / "translations").glob("*.json")))
def test_translation_has_same_keys_as_strings(lang):
    source = set(_paths(_load(BASE / "strings.json")))
    translated = set(_paths(_load(BASE / "translations" / f"{lang}.json")))
    assert not source - translated, f"{lang}: missing keys {sorted(source - translated)}"
    assert not translated - source, f"{lang}: unknown keys {sorted(translated - source)}"
