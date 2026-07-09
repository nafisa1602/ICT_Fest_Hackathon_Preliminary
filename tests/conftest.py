import pytest
import app.auth

class FakeRedis:
    def __init__(self):
        self.store = {}

    def exists(self, key: str) -> int:
        return 1 if key in self.store else 0

    def setex(self, key: str, time: int, value: str) -> bool:
        self.store[key] = value
        return True

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.store[key] = value
        return True

@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(app.auth, "_redis", fake)
