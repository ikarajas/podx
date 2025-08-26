from __future__ import annotations

from dataclasses import asdict
import json
from typing import List

from podx.services.config import Config
from ..models import Subscription


class SubscriptionService:
    """Persist and retrieve podcast subscriptions."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.path = cfg.root_dir / "subscriptions.json"
        self._subscriptions: list[Subscription] = []
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text())
            self._subscriptions = [Subscription(**item) for item in data]
        else:
            self._subscriptions = []

    def list_subscriptions(self) -> List[Subscription]:
        return list(self._subscriptions)

    def add_subscription(self, sub: Subscription) -> None:
        if not any(s.feed_url == sub.feed_url for s in self._subscriptions):
            self._subscriptions.append(sub)
            self._save()

    def remove_subscription(self, feed_url: str) -> None:
        self._subscriptions = [s for s in self._subscriptions if s.feed_url != feed_url]
        self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(s) for s in self._subscriptions]
        self.path.write_text(json.dumps(data, indent=2))


__all__ = ["SubscriptionService", "Subscription"]
