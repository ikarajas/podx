from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from podx.models import Subscription
from podx.services.config import Config, WhisperSettings, LoggingSettings
from podx.services.subscriptions import SubscriptionService


def make_config(tmp_path: Path) -> Config:
    return Config(
        root_dir=tmp_path,
        whisper=WhisperSettings(runner="", model="", extra_args=[]),
        logging=LoggingSettings(),
    )


def test_subscription_persistence(tmp_path):
    cfg = make_config(tmp_path)
    service = SubscriptionService(cfg)
    service.add_subscription(Subscription(name="Test", feed_url="url", icon_url="icon.png"))
    again = SubscriptionService(cfg)
    subs = again.list_subscriptions()
    assert len(subs) == 1
    sub = subs[0]
    assert sub.name == "Test"
    assert sub.feed_url == "url"
    assert sub.icon_url == "icon.png"
