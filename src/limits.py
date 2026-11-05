"""Usage limits for the hosted app: per-visitor rate limit and a daily spend cap.

The Anthropic API is paid per token, so the app refuses questions when a visitor asks too often or
when the day's estimated spend reaches the cap. Spend is persisted in data/usage.json (git-ignored)
so a restart does not reset it. Prices are per million tokens and can be overridden with
environment variables if Anthropic changes them.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

USAGE_FILE = Path(os.environ.get("CSCLBOT_USAGE_FILE", Path(__file__).resolve().parent.parent / "data" / "usage.json"))
INPUT_USD_PER_MTOK = float(os.environ.get("CSCLBOT_INPUT_USD_PER_MTOK", "1.0"))  # Claude Haiku 4.5
OUTPUT_USD_PER_MTOK = float(os.environ.get("CSCLBOT_OUTPUT_USD_PER_MTOK", "5.0"))
DAILY_SPEND_CAP_USD = float(os.environ.get("CSCLBOT_DAILY_SPEND_CAP_USD", "5.0"))
HOURLY_LIMIT = int(os.environ.get("CSCLBOT_HOURLY_LIMIT", "8"))
DAILY_LIMIT = int(os.environ.get("CSCLBOT_DAILY_LIMIT", "30"))


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    return input_tokens * INPUT_USD_PER_MTOK / 1e6 + output_tokens * OUTPUT_USD_PER_MTOK / 1e6


class Limiter:
    def __init__(self, hourly: int = HOURLY_LIMIT, daily: int = DAILY_LIMIT, spend_cap: float = DAILY_SPEND_CAP_USD, usage_file: Path = USAGE_FILE):
        self.hourly, self.daily, self.spend_cap, self.usage_file = hourly, daily, spend_cap, usage_file
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    @staticmethod
    def today() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _load(self) -> dict:
        try:
            data = json.loads(self.usage_file.read_text())
        except (FileNotFoundError, ValueError):
            data = {}
        return data if data.get("date") == self.today() else {"date": self.today(), "usd": 0.0, "questions": 0}

    def spent_today(self) -> float:
        return float(self._load()["usd"])

    def check(self, client: str, now: float | None = None) -> str | None:
        """None if the question may proceed, otherwise a message to show the visitor."""
        now = time.time() if now is None else now
        with self.lock:
            if self._load()["usd"] >= self.spend_cap:
                return "csclbot has reached its budget for today. Please try again tomorrow."
            q = self.hits[client]
            while q and now - q[0] > 86400:
                q.popleft()
            if len(q) >= self.daily:
                return f"You have reached the limit of {self.daily} questions per day."
            if sum(1 for t in q if now - t <= 3600) >= self.hourly:
                return f"You have reached the limit of {self.hourly} questions per hour. Please wait a little."
            q.append(now)
        return None

    def record(self, input_tokens: int, output_tokens: int) -> float:
        usd = cost_usd(input_tokens, output_tokens)
        with self.lock:
            data = self._load()
            data["usd"] = round(float(data["usd"]) + usd, 6)
            data["questions"] = int(data["questions"]) + 1
            self.usage_file.parent.mkdir(parents=True, exist_ok=True)
            self.usage_file.write_text(json.dumps(data))
        return usd
