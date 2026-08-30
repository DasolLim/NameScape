from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.main import app
from app.modules.gazetteer import backends
from app.modules.gazetteer.importer import import_geonames

FIXTURE = Path(__file__).parent / "fixtures" / "geonames_sample.txt"


@pytest.fixture
async def client(db: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> AsyncClient:
    async def index_unavailable(*_a: object, **_k: object) -> None:
        return None

    monkeypatch.setattr(backends, "typesense_ids", index_unavailable)
    await import_geonames(db, FIXTURE)

    app.dependency_overrides[get_session] = lambda: db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_search_returns_matching_places(client: AsyncClient) -> None:
    response = await client.get("/api/search", params={"q": "Dildo"})

    assert response.status_code == 200
    results = response.json()["results"]
    assert results[0]["name"] == "Dildo"
    assert results[0]["country_code"] == "CA"
    assert results[0]["claimed_by"] is None


async def test_search_filters_by_country(client: AsyncClient) -> None:
    response = await client.get("/api/search", params={"q": "Hell", "country": "NO"})

    assert [r["country_code"] for r in response.json()["results"]] == ["NO"]


async def test_a_blank_query_returns_an_empty_list_not_an_error(client: AsyncClient) -> None:
    response = await client.get("/api/search", params={"q": "  "})

    assert response.status_code == 200
    assert response.json()["results"] == []


async def test_a_null_byte_in_a_query_does_not_crash(client: AsyncClient) -> None:
    """Postgres text cannot hold 0x00; found by contract fuzzing in CI.

    The byte is stripped rather than rejected, so the query still means what
    the user typed.
    """
    response = await client.get("/api/search", params={"q": "Dild\x00o"})

    assert response.status_code == 200
    assert [r["name"] for r in response.json()["results"]] == ["Dildo"]
