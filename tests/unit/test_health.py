async def test_health_returns_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_returns_ok_when_no_checks_registered(client):
    # Phase 0: no readiness checks exist yet, so /ready should trivially pass.
    response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"] == {}


async def test_ready_returns_503_when_a_check_fails(client):
    from luna.api.routes_health import readiness_checks

    async def failing_check() -> bool:
        return False

    readiness_checks.append(("fake_dependency", failing_check))
    try:
        response = await client.get("/ready")
        assert response.status_code == 503
        assert response.json()["status"] == "not_ready"
    finally:
        readiness_checks.pop()


async def test_health_response_has_request_id_header(client):
    response = await client.get("/health")
    assert "X-Request-ID" in response.headers
