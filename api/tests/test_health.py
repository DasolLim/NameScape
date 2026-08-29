from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_health_reports_db_and_redis_reachable() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": True, "redis": True}
