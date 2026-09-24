"""Model registry: name lookup and MultiAir capability by model id."""

from __future__ import annotations

import pytest

from custom_components.open_firenet.const import (
    MULTIAIR_MODELS,
    STOVE_MODELS,
    get_model_name,
    is_multiair_supported,
)


def test_primo_multiair_is_registered():
    assert STOVE_MODELS[29] == "PRIMO MULTIAIR"
    assert get_model_name(29) == "PRIMO MULTIAIR"


@pytest.mark.parametrize("model_id", sorted(MULTIAIR_MODELS))
def test_multiair_models_are_supported_by_id_alone(model_id):
    assert is_multiair_supported({"stove": {"model": model_id}, "controls": {}})


def test_natural_convection_model_is_not_multiair():
    assert not is_multiair_supported({"stove": {"model": 11}, "controls": {}})


def test_primo_is_multiair():
    assert 29 in MULTIAIR_MODELS
