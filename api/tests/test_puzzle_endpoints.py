"""The daily puzzle over HTTP.

Reading the puzzle is not gated and does not write anything: opening the page
must not create a session for somebody who never guesses. Guessing does, which
is the first moment there is anything to remember.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_redis
from app.db import get_session
from app.main import app
from app.models import GuestSession, Place, Puzzle, PuzzleAttempt
from app.modules.accounts import service as accounts_service
from tests.factories import build_place, build_user

TODAY = datetime.now(UTC).date()
GUEST_COOKIE = "namescape_guest"


@pytest.fixture
async def client(db: AsyncSession, fake_redis: FakeRedis) -> AsyncClient:
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_redis] = lambda: fake_redis
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://test")


async def a_puzzle(
    db: AsyncSession, *, day: date | None = None, status: str = "live", seq: int = 0
) -> tuple[Puzzle, Place]:
    place = await build_place(
        db,
        name=f"Cardiff{'' if seq == 0 else f' {seq}'}",
        geonames_id=2_653_822 + seq,
        country_code="GB",
        tier=2,
        lon=-3.1791,
        lat=51.4816,
    )
    puzzle = Puzzle(
        puzzle_date=day or TODAY,
        place_id=place.id,
        clues=["A fort on a river.", "It is a populated place, a city.", "Europe", "Wales"],
        status=status,
        generated_by="fake/model-1",
    )
    db.add(puzzle)
    await db.flush()
    return puzzle, place


async def sign_in(client: AsyncClient, db: AsyncSession, username: str = "player") -> None:
    user = await build_user(db, username=username)
    client.cookies.set("namescape_session", accounts_service._session_for(user).cookie)


async def test_the_puzzle_opens_with_one_clue_and_nothing_else(
    client: AsyncClient, db: AsyncSession
) -> None:
    puzzle, _ = await a_puzzle(db)

    body = (await client.get("/api/puzzle")).json()

    assert body["puzzle_id"] == puzzle.id
    assert body["clues"] == ["A fort on a river."]
    assert body["guesses"] == []
    assert body["remaining"] == 5
    # No answer, no pin, no grid: none of that has been earned.
    assert body["answer"] is None
    assert body["pin"] is None
    assert body["share_grid"] == ""


async def test_reading_the_puzzle_writes_nothing(client: AsyncClient, db: AsyncSession) -> None:
    """Opening the page must not mint a session for somebody who never plays."""
    await a_puzzle(db)

    response = await client.get("/api/puzzle")

    assert response.status_code == 200
    assert GUEST_COOKIE not in response.cookies
    assert (await db.execute(select(GuestSession))).scalars().all() == []
    assert (await db.execute(select(PuzzleAttempt))).scalars().all() == []


async def test_a_day_with_no_puzzle_says_so_plainly(client: AsyncClient, db: AsyncSession) -> None:
    await a_puzzle(db, status="draft")

    response = await client.get("/api/puzzle")

    assert response.status_code == 200
    assert response.json() is None


async def test_a_guess_reports_how_close_it_came(client: AsyncClient, db: AsyncSession) -> None:
    puzzle, _ = await a_puzzle(db)
    bristol = await build_place(db, name="Bristol", geonames_id=2_654_675, lon=-2.5879, lat=51.4545)

    body = (
        await client.post(f"/api/puzzle/{puzzle.id}/guess", json={"place_id": bristol.id})
    ).json()

    guess = body["guesses"][0]
    assert guess["name"] == "Bristol"
    assert 38 < guess["distance_km"] < 44
    assert guess["band"] == "near"
    assert guess["arrow"] == "⬅️"
    assert guess["proximity"] > 99
    # A wrong guess earns the next clue, and the earlier one stays.
    assert body["clues"] == ["A fort on a river.", "It is a populated place, a city."]
    assert body["remaining"] == 4


async def test_a_guessing_visitor_is_given_a_guest_session(
    client: AsyncClient, db: AsyncSession
) -> None:
    puzzle, _ = await a_puzzle(db)
    bristol = await build_place(db, name="Bristol", geonames_id=2_654_675, lon=-2.5879, lat=51.4545)

    response = await client.post(f"/api/puzzle/{puzzle.id}/guess", json={"place_id": bristol.id})

    assert response.status_code == 200
    assert GUEST_COOKIE in response.cookies
    attempt = (await db.execute(select(PuzzleAttempt))).scalars().one()
    assert attempt.guest_session_id is not None
    assert attempt.user_id is None


async def test_a_guest_keeps_their_attempt_across_requests(
    client: AsyncClient, db: AsyncSession
) -> None:
    puzzle, _ = await a_puzzle(db)
    bristol = await build_place(db, name="Bristol", geonames_id=2_654_675, lon=-2.5879, lat=51.4545)

    await client.post(f"/api/puzzle/{puzzle.id}/guess", json={"place_id": bristol.id})
    body = (await client.get("/api/puzzle")).json()

    assert len(body["guesses"]) == 1
    assert len((await db.execute(select(PuzzleAttempt))).scalars().all()) == 1


async def test_solving_reveals_the_place_and_a_grid_to_post(
    client: AsyncClient, db: AsyncSession
) -> None:
    puzzle, place = await a_puzzle(db)

    body = (await client.post(f"/api/puzzle/{puzzle.id}/guess", json={"place_id": place.id})).json()

    assert body["solved"] is True
    assert body["complete"] is True
    assert body["answer"]["name"] == "Cardiff"
    assert body["answer"]["claimed_by"] is None
    assert body["pin"] == {"lat": pytest.approx(51.4816), "lon": pytest.approx(-3.1791)}
    assert "3/5" not in body["share_grid"]
    assert "1/5" in body["share_grid"]
    assert "Cardiff" not in body["share_grid"]


async def test_guessing_again_after_finishing_is_refused(
    client: AsyncClient, db: AsyncSession
) -> None:
    puzzle, place = await a_puzzle(db)
    await client.post(f"/api/puzzle/{puzzle.id}/guess", json={"place_id": place.id})

    again = await client.post(f"/api/puzzle/{puzzle.id}/guess", json={"place_id": place.id})

    assert again.status_code == 409


async def test_guessing_a_place_that_does_not_exist_is_a_404(
    client: AsyncClient, db: AsyncSession
) -> None:
    puzzle, _ = await a_puzzle(db)

    response = await client.post(f"/api/puzzle/{puzzle.id}/guess", json={"place_id": 999_999})

    assert response.status_code == 404


async def test_guessing_at_a_puzzle_that_does_not_exist_is_a_404(
    client: AsyncClient, db: AsyncSession
) -> None:
    response = await client.post("/api/puzzle/999999/guess", json={"place_id": 1})

    assert response.status_code == 404


async def test_a_signed_in_solve_builds_a_streak(client: AsyncClient, db: AsyncSession) -> None:
    puzzle, place = await a_puzzle(db)
    await sign_in(client, db)

    body = (await client.post(f"/api/puzzle/{puzzle.id}/guess", json={"place_id": place.id})).json()

    assert body["streak"] == 1
    assert "🔥1" in body["share_grid"]


async def test_the_archive_is_account_gated_and_says_why(
    client: AsyncClient, db: AsyncSession
) -> None:
    await a_puzzle(db, day=TODAY - timedelta(days=1), status="archived")

    response = await client.get("/api/puzzle/archive")

    assert response.status_code == 401
    assert "account" in response.json()["detail"].casefold()


async def test_the_archive_lists_past_puzzles_for_an_account(
    client: AsyncClient, db: AsyncSession
) -> None:
    yesterday, place = await a_puzzle(db, day=TODAY - timedelta(days=1), status="archived")
    await a_puzzle(db, day=TODAY, status="live", seq=1)
    await sign_in(client, db)
    await client.post(f"/api/puzzle/{yesterday.id}/guess", json={"place_id": place.id})

    body = (await client.get("/api/puzzle/archive")).json()

    # Only what is past: today's puzzle is not archive material yet.
    assert [entry["puzzle_id"] for entry in body["puzzles"]] == [yesterday.id]
    assert body["puzzles"][0]["solved"] is True
    assert body["puzzles"][0]["date"] == str(TODAY - timedelta(days=1))
    # And still no answers: the archive is for replaying, not for spoilers.
    assert "answer" not in body["puzzles"][0]
