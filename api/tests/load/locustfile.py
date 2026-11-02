"""Load profile for the two endpoints that decide whether this feels fast.

PRD step 22 targets: search p95 under 200ms, viewport p95 under 400ms.
Search is the leading indicator - every product in this category that failed,
failed at search first.
"""

import random

from locust import HttpUser, between, task

QUERIES = ["Dildo", "Batman", "Boring", "Dull", "Hell", "Dildoo", "Cocker", "Truth"]

# Roughly Newfoundland, where the seeded discoveries are.
BOUNDS = {"west": -55.0, "south": 46.5, "east": -52.5, "north": 48.5}


class Explorer(HttpUser):
    """Someone spinning the globe and searching, which is most of the traffic."""

    wait_time = between(0.1, 0.5)

    @task(3)
    def search(self) -> None:
        self.client.get("/api/search", params={"q": random.choice(QUERIES)}, name="/api/search")

    @task(5)
    def viewport(self) -> None:
        jitter = random.uniform(-0.2, 0.2)
        self.client.get(
            "/api/viewport",
            params={
                "west": BOUNDS["west"] + jitter,
                "south": BOUNDS["south"],
                "east": BOUNDS["east"] + jitter,
                "north": BOUNDS["north"],
                "zoom": random.choice([2, 6, 12]),
            },
            name="/api/viewport",
        )

    @task(1)
    def health(self) -> None:
        self.client.get("/api/health", name="/api/health")
