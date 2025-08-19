import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from podx.directory import search_podcasts
from podx.cli import main

sample_response = {
    "resultCount": 1,
    "results": [
        {
            "collectionName": "The Rest Is History",
            "feedUrl": "https://feeds.megaphone.fm/GLT4787413333",
            "genres": ["History", "Podcasts"],
        }
    ],
}


class DummyResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass

    def read(self):
        return json.dumps(sample_response).encode()


def fake_urlopen(_url):
    return DummyResponse()


def test_search_podcasts(monkeypatch):
    monkeypatch.setattr("podx.directory.request.urlopen", fake_urlopen)
    podcasts = search_podcasts("rest is history")
    assert len(podcasts) == 1
    p = podcasts[0]
    assert p.name == "The Rest Is History"
    assert p.feed_url == "https://feeds.megaphone.fm/GLT4787413333"
    assert p.genres == ["History", "Podcasts"]


def test_cli_search(monkeypatch, capsys):
    monkeypatch.setattr("podx.directory.request.urlopen", fake_urlopen)
    exit_code = main(["search", "rest is history"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Podcast Name: The Rest Is History" in captured.out
    assert "Feed URL: https://feeds.megaphone.fm/GLT4787413333" in captured.out
    assert "Genres: History, Podcasts" in captured.out
