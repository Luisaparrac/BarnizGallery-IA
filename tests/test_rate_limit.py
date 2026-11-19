from app.core.rate_limiter import SlidingWindowRateLimiter, client_identity


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_allows_up_to_the_limit_then_blocks():
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(clock)

    assert [limiter.hit("a", 3) for _ in range(3)] == [None, None, None]
    assert limiter.hit("a", 3) == 60


def test_window_slides():
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(clock)
    limiter.hit("a", 1)

    clock.now += 45
    assert limiter.hit("a", 1) == 15

    clock.now += 15
    assert limiter.hit("a", 1) is None


def test_buckets_are_independent():
    limiter = SlidingWindowRateLimiter(FakeClock())
    limiter.hit("a", 1)

    assert limiter.hit("b", 1) is None


def test_identity_never_contains_the_key():
    identity = client_identity("super-secret-key", "10.0.0.1")

    assert "super-secret-key" not in identity
    assert identity.endswith(":10.0.0.1")
    assert identity != client_identity("other-key", "10.0.0.1")


def test_endpoint_returns_429_with_retry_after(make_client, auth_headers):
    client = make_client(rate_limit_per_minute=2)

    statuses = [
        client.post("/v1/recommendations", json={}, headers=auth_headers).status_code
        for _ in range(2)
    ]
    blocked = client.post("/v1/recommendations", json={}, headers=auth_headers)

    assert statuses == [200, 200]
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "rate_limited"
    assert int(blocked.headers["Retry-After"]) > 0


def test_limit_is_per_ip(make_client, auth_headers):
    client = make_client(rate_limit_per_minute=1)
    first = {**auth_headers, "X-Forwarded-For": "1.1.1.1"}
    second = {**auth_headers, "X-Forwarded-For": "2.2.2.2"}

    assert client.post("/v1/recommendations", json={}, headers=first).status_code == 200
    assert client.post("/v1/recommendations", json={}, headers=second).status_code == 200
    assert client.post("/v1/recommendations", json={}, headers=first).status_code == 429


def test_wrong_keys_are_limited_too(make_client):
    client = make_client(rate_limit_per_minute=1)
    headers = {"X-API-Key": "guess"}

    assert client.post("/v1/recommendations", json={}, headers=headers).status_code == 401
    assert client.post("/v1/recommendations", json={}, headers=headers).status_code == 429


def test_health_is_not_limited(make_client):
    client = make_client(rate_limit_per_minute=1)

    assert all(client.get("/health").status_code == 200 for _ in range(5))
