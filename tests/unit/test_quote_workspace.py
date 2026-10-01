from datetime import UTC, datetime, timedelta

import pytest

from alr_tw.research.quote_workspace import map_source_quote
from test_v080_finalization_integration import _prepared_service


def test_mapping_is_read_only_and_purge_removes_authority(tmp_path):
    service, run_id, _ = _prepared_service(tmp_path)
    before = service.store.list_evidence(run_id)
    result = map_source_quote(service.store, run_id, "source-1", "行為人應負合成責任")
    assert result["status"] == "unique"
    assert result["quote"]["exact_text"] == "行為人應負合成責任"
    assert not result["evidence_minting_authorized"]
    assert before == service.store.list_evidence(run_id)
    service.store.purge_run(run_id)
    with pytest.raises(ValueError, match="RESEARCH_RUN_EXPIRED"):
        map_source_quote(service.store, run_id, "source-1", "行為人")


def test_expired_or_foreign_source_is_not_mappable(tmp_path, monkeypatch):
    import test_v080_finalization_integration as fixtures
    monkeypatch.setattr(fixtures, "NOW", datetime.now(UTC) - timedelta(minutes=1))
    service, run_id, _ = _prepared_service(
        tmp_path, source_expires_at=datetime.now(UTC) - timedelta(seconds=1)
    )
    for source in ["source-1", "foreign-source"]:
        with pytest.raises(ValueError, match="QUOTE_SOURCE_NOT_ELIGIBLE"):
            map_source_quote(service.store, run_id, source, "行為人")
