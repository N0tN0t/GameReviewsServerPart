from locust import HttpUser, between, task


class GameReviewsUser(HttpUser):
    wait_time = between(0.2, 1.0)

    @task(9)
    def read_games_catalog(self):
        self.client.get("/api/v1/games")
