import json
import logging
import sys

import pytest

from app.core.logging_config import JsonFormatter, route_of
from tests.conftest import TEST_API_KEY

SECRET_TITLE = "Bandeja secreta para Marcela Rodríguez"
PAYLOAD = {"request_id": 9, "title": SECRET_TITLE, "shape": "Bandeja", "style": "Tradicional"}


def access_lines(caplog) -> list[dict]:
    formatter = JsonFormatter()
    return [
        json.loads(formatter.format(record))
        for record in caplog.records
        if record.name == "app.access"
    ]


def all_lines(caplog) -> str:
    formatter = JsonFormatter()
    return "\n".join(formatter.format(record) for record in caplog.records)


@pytest.fixture(autouse=True)
def capture_info(caplog):
    caplog.set_level(logging.INFO)


def test_access_line_has_request_fields(client, auth_headers, caplog):
    client.post(
        "/v1/designs", json=PAYLOAD, headers={**auth_headers, "X-Request-ID": "log-test-1"}
    )

    [line] = access_lines(caplog)
    assert line["message"] == "request"
    assert line["request_id"] == "log-test-1"
    assert line["method"] == "POST"
    assert line["route"] == "/v1/designs"
    assert line["status"] == 200
    assert isinstance(line["duration_ms"], float)
    assert line["provider"] == "fake"
    assert line["model"] == "fake-pillow"
    assert line["images"] == 1
    assert "error_code" not in line


def test_access_line_has_error_code(client, caplog):
    client.post("/v1/designs", json=PAYLOAD)

    [line] = access_lines(caplog)
    assert line["status"] == 401
    assert line["error_code"] == "unauthorized"


def test_logs_never_contain_key_customer_text_or_prompt(client, auth_headers, caplog):
    client.post("/v1/designs", json=PAYLOAD, headers=auth_headers)
    client.post("/v1/designs", json={**PAYLOAD, "count": 9}, headers=auth_headers)

    text = all_lines(caplog)
    assert TEST_API_KEY not in text
    assert "Marcela" not in text
    assert "Barniz de Pasto" not in text  # part of every prompt


def test_recommendation_and_pricing_lines(client, auth_headers, caplog):
    client.post("/v1/recommendations", json={}, headers=auth_headers)
    comparable = {"shape": "bandeja", "price": 100, "currency": "USD"}
    client.post(
        "/v1/pricing/suggest",
        json={"piece": {"shape": "bandeja"}, "comparables": [comparable] * 3, "currency": "USD"},
        headers=auth_headers,
    )

    recommendations, pricing = access_lines(caplog)
    assert recommendations["route"] == "/v1/recommendations"
    assert recommendations["strategy"] == "popular"
    assert pricing["route"] == "/v1/pricing/suggest"
    assert pricing["method"] == "comparables"


def test_unmatched_route_does_not_log_raw_path(client, caplog):
    client.get("/v1/designs/Marcela?email=marcela@example.com")

    [line] = access_lines(caplog)
    assert line["route"] == "<unmatched>"
    assert "marcela" not in json.dumps(line).lower()


def test_exception_logs_type_and_stack_but_not_message():
    customer_text = "texto del cliente: Marcela"
    try:
        raise ValueError(customer_text)
    except ValueError:
        record = logging.LogRecord("x", logging.ERROR, "", 0, "falló", (), None)
        record.exc_info = sys.exc_info()

    line = json.loads(JsonFormatter().format(record))
    assert line["exc_type"] == "ValueError"
    assert "test_logging.py" in line["stack"]
    assert "Marcela" not in json.dumps(line)


def test_route_template_hides_path_parameter_values():
    scope = {
        "route": object(),
        "path": "/v1/orders/marcela-123",
        "path_params": {"id": "marcela-123"},
    }

    assert route_of(scope) == "/v1/orders/{id}"
    assert route_of({"path": "/v1/x"}) == "<unmatched>"
