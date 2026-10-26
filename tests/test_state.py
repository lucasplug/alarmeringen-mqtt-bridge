"""Tests voor AlertState: begrenzing, atomaire opslag en herladen."""

import json

from state import AlertState


def test_remember_and_is_seen():
    state = AlertState(max_seen_ids=10, history_size=5)
    assert not state.is_seen("a")
    state.remember("a")
    assert state.is_seen("a")
    state.remember("a")  # dubbel onthouden is een no-op
    assert len(state.seen_order) == 1


def test_seen_ids_bounded_by_max():
    state = AlertState(max_seen_ids=3, history_size=5)
    for alert_id in "abcde":
        state.remember(alert_id)
    assert len(state.seen_ids) == 3
    assert not state.is_seen("a")  # oudste eruit
    assert state.is_seen("e")


def test_history_bounded_by_size():
    state = AlertState(max_seen_ids=10, history_size=2)
    for n in range(4):
        state.add_history({"n": n})
    assert [h["n"] for h in state.history] == [3, 2]


def test_save_and_load_roundtrip(tmp_path):
    path = str(tmp_path / "state.json")
    state = AlertState(max_seen_ids=10, history_size=5)
    state.remember("a")
    state.remember("b")
    state.add_history({"titel": "test"})
    state.save(path)

    # Atomair: geen achtergebleven .tmp-bestand.
    assert not (tmp_path / "state.json.tmp").exists()

    reloaded = AlertState(max_seen_ids=10, history_size=5)
    reloaded.load(path)
    assert reloaded.is_seen("a") and reloaded.is_seen("b")
    assert reloaded.history == [{"titel": "test"}]


def test_load_corrupt_state_starts_empty(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{kapot")
    state = AlertState(max_seen_ids=10, history_size=5)
    state.load(str(path))
    assert not state.seen_ids
    assert state.history == []


def test_load_trims_history_to_current_size(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"seen_ids": [], "history": [{"n": n} for n in range(10)]}))
    state = AlertState(max_seen_ids=10, history_size=3)
    state.load(str(path))
    assert len(state.history) == 3


def test_is_repeat_within_window_only():
    state = AlertState(max_seen_ids=10, history_size=5, repeat_window=600)
    state.remember_title("A1  Hoorneslaan KATWZH : 16189", now=1000.0)
    # Normalisatie van hoofdletters en witruimte.
    assert state.is_repeat("a1 hoorneslaan katwzh : 16189", now=1500.0)
    assert not state.is_repeat("a1 hoorneslaan katwzh : 16189", now=1700.0)
    assert not state.is_repeat("a2 hoorneslaan katwzh : 16189", now=1100.0)


def test_recent_titles_pruned_and_persisted(tmp_path):
    path = str(tmp_path / "state.json")
    state = AlertState(max_seen_ids=10, history_size=5, repeat_window=600)
    state.remember_title("oud", now=0.0)
    state.remember_title("nieuw", now=1000.0)
    assert list(state.recent_titles) == ["nieuw"]
    state.save(path)

    reloaded = AlertState(max_seen_ids=10, history_size=5, repeat_window=600)
    assert reloaded.load(path) is True
    assert reloaded.is_repeat("nieuw", now=1100.0)


def test_load_reports_missing_state(tmp_path):
    state = AlertState(max_seen_ids=10, history_size=5)
    assert state.load(str(tmp_path / "bestaat-niet.json")) is False
