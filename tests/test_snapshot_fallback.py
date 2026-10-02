import json

from app import snapshot
from app.config import settings


def write(dirpath, mid, source, client, fetched):
    p = dirpath / str(mid) / "snapshot.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"source": source, "fetched_at": fetched,
                             "matter": {"id": mid, "client": client, "description": "Auto accident"}}))


def test_find_saved_picks_newest_live_clio_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "snapshot_dir", tmp_path)
    write(tmp_path, 1, "clio", "Gina Sapini", "2026-10-02T17:00:00+00:00")
    write(tmp_path, 2, "clio", "Gina Sapini", "2026-10-02T18:00:00+00:00")
    write(tmp_path, 3, "sample", "Gina Sapini", "2026-10-02T19:00:00+00:00")   # sample is never used
    write(tmp_path, 4, "clio", "Someone Else", "2026-10-02T20:00:00+00:00")
    assert snapshot.find_saved("sapini")["matter"]["id"] == 2


def test_find_saved_none_when_nothing_matches(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "snapshot_dir", tmp_path)
    (tmp_path / "9").mkdir()
    (tmp_path / "9" / "snapshot.json").write_text("{broken")
    assert snapshot.find_saved("sapini") is None
    assert snapshot.find_saved("") is None
