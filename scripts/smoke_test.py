"""Smoke test of a deployed AI service (Render by default). Never generates images.

Usage::

    AI_SERVICE_KEY=... python scripts/smoke_test.py
    AI_SERVICE_URL=https://otra-url.onrender.com AI_SERVICE_KEY=... python scripts/smoke_test.py

Checks ``/health``, that ``/v1`` rejects requests without key, recommendations and the
suggested price. The key is read from the environment and never printed. Exit code 0 if
every check passes, 1 otherwise.

Fields added in 1.1.0 (``explanation``, ``confidence``) are reported as warnings when
missing, so the script also works against a service that still runs 1.0.0.
"""

import os
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

DEFAULT_URL = "https://barnizgallery-ia.onrender.com"
#: Render's free plan can take about a minute to wake up.
TIMEOUT_SECONDS = 120.0

RECOMMENDATIONS = {
    "profile": {
        "colors": ["rojo"],
        "shapes": ["bandeja"],
        "styles": ["tradicional"],
        "motifs": ["colibri"],
        "budget": {"min": 20, "max": 120, "currency": "USD"},
    },
    "interactions": [{"artwork_id": 5, "action": "VIEW", "duration_seconds": 40}],
    "candidates": [
        {
            "artwork_id": 5,
            "store_id": 2,
            "colors": ["rojo", "amarillo"],
            "shape": "bandeja",
            "style": "tradicional",
            "motifs": ["colibri"],
            "price": 80,
            "currency": "USD",
            "popularity": 12,
        },
        {
            "artwork_id": 6,
            "store_id": 3,
            "colors": ["azul"],
            "shape": "caja",
            "style": "moderno",
            "motifs": ["geometrico"],
            "price": 300,
            "currency": "USD",
            "popularity": 50,
        },
    ],
    "limit": 5,
}

PRICING = {
    "piece": {"shape": "bandeja", "motifs": ["colibri"], "width_cm": 30, "height_cm": 30},
    "comparables": [
        {
            "shape": "bandeja",
            "motifs": ["colibri"],
            "width_cm": 30,
            "height_cm": 30,
            "price": price,
            "currency": "USD",
            "sold": sold,
        }
        for price, sold in ((80, True), (95, True), (100, False), (115, False))
    ],
    "currency": "USD",
}


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    warnings: list[str] = field(default_factory=list)


def _request_id() -> str:
    return f"smoke-{uuid.uuid4().hex[:12]}"


def check_health(client: httpx.Client) -> CheckResult:
    response = client.get("/health")
    body = response.json() if response.status_code == 200 else {}
    ok = response.status_code == 200 and body.get("status") == "ok"
    detail = (
        f"HTTP {response.status_code} versión={body.get('version')} "
        f"imágenes={body.get('image_provider')} texto={body.get('text_provider')} "
        f"commit={(body.get('commit') or '-')[:7]}"
    )
    return CheckResult("health", ok, detail)


def check_auth_required(client: httpx.Client) -> CheckResult:
    response = client.post(
        "/v1/recommendations",
        json={},
        headers={"X-API-Key": "", "X-Request-ID": _request_id()},
    )
    code = response.json().get("code") if response.status_code == 401 else None
    ok = response.status_code == 401 and code == "unauthorized"
    return CheckResult("sin clave → 401", ok, f"HTTP {response.status_code} code={code}")


def check_recommendations(client: httpx.Client, key: str) -> CheckResult:
    request_id = _request_id()
    response = client.post(
        "/v1/recommendations",
        json=RECOMMENDATIONS,
        headers={"X-API-Key": key, "X-Request-ID": request_id},
    )
    if response.status_code != 200:
        return CheckResult("recomendaciones", False, _error(response, request_id))
    body = response.json()
    items = body.get("items", [])
    ok = body.get("strategy") == "hybrid" and bool(items) and items[0].get("artwork_id") == 5
    warnings = [] if items and "explanation" in items[0] else ["falta 'explanation' (< 1.1.0)"]
    detail = f"strategy={body.get('strategy')} primero={items[0]['artwork_id'] if items else '-'}"
    return CheckResult("recomendaciones", ok, f"{detail} id={request_id}", warnings)


def check_pricing(client: httpx.Client, key: str) -> CheckResult:
    request_id = _request_id()
    response = client.post(
        "/v1/pricing/suggest",
        json=PRICING,
        headers={"X-API-Key": key, "X-Request-ID": request_id},
    )
    if response.status_code != 200:
        return CheckResult("precio sugerido", False, _error(response, request_id))
    body = response.json()
    low, price, high = body.get("min_price"), body.get("suggested_price"), body.get("max_price")
    ok = None not in (low, price, high) and low <= price <= high and body.get("currency") == "USD"
    warnings = [] if "confidence" in body else ["falta 'confidence' (< 1.1.0)"]
    detail = f"{price} {body.get('currency')} [{low} a {high}] método={body.get('method')}"
    return CheckResult("precio sugerido", ok, f"{detail} id={request_id}", warnings)


def _error(response: httpx.Response, request_id: str) -> str:
    try:
        code = response.json().get("code")
    except ValueError:
        code = None
    return f"HTTP {response.status_code} code={code} id={request_id}"


def run_checks(client: httpx.Client, key: str) -> list[CheckResult]:
    checks: list[Callable[[], CheckResult]] = [
        lambda: check_health(client),
        lambda: check_auth_required(client),
        lambda: check_recommendations(client, key),
        lambda: check_pricing(client, key),
    ]
    results = []
    for check in checks:
        try:
            results.append(check())
        except httpx.HTTPError as exc:
            results.append(CheckResult("conexión", False, type(exc).__name__))
            break
    return results


def main() -> int:
    url = os.getenv("AI_SERVICE_URL", DEFAULT_URL).rstrip("/")
    key = os.getenv("AI_SERVICE_KEY", "")
    if not key:
        print("Falta la variable de entorno AI_SERVICE_KEY.", file=sys.stderr)
        return 1

    print(f"Smoke test de {url}")
    with httpx.Client(base_url=url, timeout=TIMEOUT_SECONDS) as client:
        results = run_checks(client, key)

    for result in results:
        print(f"  {'OK   ' if result.ok else 'FALLA'} {result.name}: {result.detail}")
        for warning in result.warnings:
            print(f"        aviso: {warning}")
    passed = all(result.ok for result in results) and len(results) == 4
    print("Todo bien." if passed else "Hay fallas.")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
