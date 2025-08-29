import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from podx.services.rss import _parse_duration, RssService


def test_parse_duration():
    assert _parse_duration("01:02:03") == 3723
    assert _parse_duration("05:06") == 306
    assert _parse_duration("45") == 45
    assert _parse_duration("bad") is None


def test_fetch_episodes(tmp_path):
    rss = (
        '<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel>'
        '<item><title>Ep1</title><description>Desc1</description>'
        '<pubDate>Tue, 04 Jul 2023 17:00:00 +0000</pubDate>'
        '<itunes:duration>00:01:30</itunes:duration>'
        '<itunes:image href="art1.jpg"/></item>'
        '<item><title>Ep2</title><description>Desc2</description>'
        '<pubDate>Wed, 05 Jul 2023 17:00:00 +0000</pubDate>'
        '<itunes:duration>45</itunes:duration></item>'
        '</channel></rss>'
    )
    path = tmp_path / "feed.xml"
    path.write_text(rss)
    service = RssService()
    episodes = service.fetch_episodes(path.as_uri())
    assert len(episodes) == 2
    e0 = episodes[0]
    assert e0.title == "Ep1"
    assert e0.duration == 90
    assert e0.artwork_url == "art1.jpg"
    assert e0.transcribed is False
