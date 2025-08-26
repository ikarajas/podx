import sys
from pathlib import Path
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from podx.cli import main


def test_cli_ui(monkeypatch):
    called = {"called": False}

    def fake_main():
        called["called"] = True
        return 0

    dummy_module = types.SimpleNamespace(main=fake_main)
    monkeypatch.setitem(sys.modules, "podx.ui.main", dummy_module)

    exit_code = main(["ui"])

    assert exit_code == 0
    assert called["called"]
