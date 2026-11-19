"""The smoke test script, run against the local app (no network, no OpenAI)."""

import pytest

from scripts import smoke_test
from tests.conftest import TEST_API_KEY


def test_every_check_passes_against_the_app(client):
    results = smoke_test.run_checks(client, TEST_API_KEY)

    assert [result.name for result in results] == [
        "health",
        "sin clave → 401",
        "recomendaciones",
        "precio sugerido",
    ]
    assert all(result.ok for result in results), results
    assert not any(result.warnings for result in results)


def test_wrong_key_makes_the_checks_fail(client):
    results = smoke_test.run_checks(client, "wrong-key")

    assert [result.ok for result in results] == [True, True, False, False]
    assert "code=unauthorized" in results[2].detail


def test_main_requires_the_key(monkeypatch, capsys):
    monkeypatch.delenv("AI_SERVICE_KEY", raising=False)

    assert smoke_test.main() == 1
    assert "AI_SERVICE_KEY" in capsys.readouterr().err


@pytest.mark.parametrize("check", [smoke_test.check_recommendations, smoke_test.check_pricing])
def test_output_never_contains_the_key(client, check):
    result = check(client, TEST_API_KEY)

    assert TEST_API_KEY not in result.detail
