"""Give the dev globe something to draw: a demo finder and some discoveries.

Development only. Launch seeding is 500 hand-reviewed finds across 60
countries, which is a curation job, not a script.
"""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text

from app.db import SessionLocal
from app.models import Place, User

CAPTIONS = {
    "Dildo": "Newfoundland's finest, and entirely sincere about it.",
    "Boring": "Twinned with Dull. Genuinely.",
    "Dull": "Twinned with Boring. Genuinely.",
    "Batman": "No cave, no bats, just a city on the Tigris.",
    "Truth or Consequences": "Renamed for a radio quiz show in 1950.",
    "Fugging": "Renamed in 2021 after one sign theft too many.",
    "Hell": "Freezes over most winters.",
    "Cockermouth": "Where the river Cocker meets the Derwent.",
    "Toad Suck": "Named for boatmen who drank until they swelled up.",
    "Knockemstiff": "The name predates the fistfights, apparently.",
}


async def main() -> None:
    async with SessionLocal() as session:
        # Backdated: voting needs an account at least 48 hours old.
        settled = datetime.now(UTC) - timedelta(days=5)
        users: dict[str, User] = {}
        for name in ("demo", "voter"):
            found = (
                (await session.execute(select(User).where(User.username == name))).scalars().first()
            )
            if found is None:
                found = User(username=name, email=f"{name}@example.com")
                session.add(found)
                await session.flush()
            found.created_at = settled
            users[name] = found
        user = users["demo"]

        created = 0
        for name, caption in CAPTIONS.items():
            place = (
                (
                    await session.execute(
                        select(Place)
                        .where(Place.name == name, Place.feature_class == "P")
                        .order_by(Place.population.desc())
                    )
                )
                .scalars()
                .first()
            )
            if place is None:
                continue
            await session.execute(
                text(
                    "INSERT INTO discoveries (place_id, user_id, caption) "
                    "VALUES (:place_id, :user_id, :caption) ON CONFLICT (place_id) DO NOTHING"
                ),
                {"place_id": place.id, "user_id": user.id, "caption": caption},
            )
            created += 1
        # @voter needs one discovery of their own before they may vote.
        voter_place = (
            (await session.execute(select(Place).where(Place.name == "Bastardo"))).scalars().first()
        )
        if voter_place is not None:
            await session.execute(
                text(
                    "INSERT INTO discoveries (place_id, user_id, caption) "
                    "VALUES (:place_id, :user_id, :caption) ON CONFLICT (place_id) DO NOTHING"
                ),
                {
                    "place_id": voter_place.id,
                    "user_id": users["voter"].id,
                    "caption": "Umbria's finest.",
                },
            )

        # A resolved nickname, so the globe has a second label to render.
        dildo = (
            (
                await session.execute(
                    select(Place).where(Place.name == "Dildo", Place.feature_class == "P")
                )
            )
            .scalars()
            .first()
        )
        if dildo is not None:
            await session.execute(
                text(
                    "INSERT INTO proposals "
                    "(contest_id, place_id, user_id, text, normalized_text, agree, disagree, "
                    " is_incumbent) "
                    "VALUES (NULL, :place_id, :user_id, :text, :normalized, 42, 0, true) "
                    "ON CONFLICT DO NOTHING"
                ),
                {
                    "place_id": dildo.id,
                    "user_id": users["demo"].id,
                    "text": "The Cove of Few Regrets",
                    "normalized": "the cove of few regrets",
                },
            )
            proposal_id = await session.scalar(
                text(
                    "SELECT id FROM proposals WHERE place_id = :place_id ORDER BY id DESC LIMIT 1"
                ),
                {"place_id": dildo.id},
            )
            await session.execute(
                text(
                    "INSERT INTO nicknames "
                    "(place_id, text, proposal_id, score, term_ends_at) "
                    "VALUES (:place_id, :text, :proposal_id, 42, now() + interval '30 days') "
                    "ON CONFLICT (place_id) DO NOTHING"
                ),
                {
                    "place_id": dildo.id,
                    "text": "The Cove of Few Regrets",
                    "proposal_id": proposal_id,
                },
            )

        await session.commit()

    print(f"seeded {created} demo discoveries as @demo, plus @voter")


if __name__ == "__main__":
    asyncio.run(main())
