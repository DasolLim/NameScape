"""Give the dev globe something to draw: a demo finder and some discoveries.

Development only. Launch seeding is 500 hand-reviewed finds across 60
countries, which is a curation job, not a script.
"""

import asyncio

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
        user = (
            (await session.execute(select(User).where(User.username == "demo"))).scalars().first()
        )
        if user is None:
            user = User(username="demo", email="demo@example.com")
            session.add(user)
            await session.flush()

        created = 0
        for name, caption in CAPTIONS.items():
            place = (
                (await session.execute(select(Place).where(Place.name == name))).scalars().first()
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
        await session.commit()

    print(f"seeded {created} demo discoveries as @demo")


if __name__ == "__main__":
    asyncio.run(main())
