async def test_health_returns_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_returns_ok_when_checks_pass(client, app):
    # The app's own lifespan (main.py) registers a real "database" check
    # into app.state.readiness_checks — see
    # test_ready_reports_database_check_from_lifespan below for that.
    # This test controls the list explicitly to verify the MECHANISM
    # (empty/passing checks -> 200) independent of what's really wired up,
    # which is what keeps it a true unit test.
    app.state.readiness_checks = []
    response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"] == {}


async def test_ready_returns_503_when_a_check_fails(client, app):
    async def failing_check() -> bool:
        return False

    app.state.readiness_checks = [("fake_dependency", failing_check)]
    response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


async def test_ready_reports_database_check_from_lifespan(client):
    # No setup here — the app's own lifespan wired this up. The test
    # fixture's database_url (see conftest.py) points nowhere reachable,
    # so this documents the actual, expected unit-test behavior: /ready
    # is 503 by default because there's no real Postgres, and that's
    # correct, not a bug in the test environment.
    response = await client.get("/ready")
    body = response.json()
    assert "database" in body["checks"]
    assert body["checks"]["database"] is False
    assert response.status_code == 503


async def test_health_response_has_request_id_header(client):
    response = await client.get("/health")
    assert "X-Request-ID" in response.headers
