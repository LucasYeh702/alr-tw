from __future__ import annotations

from tw_legal_rag_mcp.ingestion import staging


def test_synthetic_staging_adapter_exposes_public_ingestion_shape():
    assert hasattr(staging, "SyntheticStagingAdapter")
    result = staging.SyntheticStagingAdapter().load()

    assert result.schema == "alr-tw.adapter-result/v1"
    assert result.adapter_name == "synthetic_staging_adapter"
    assert result.status == "staged"
    assert result.manifest.source_tier == "staging"
    assert result.records
    assert result.records[0]["source_tier"] == "staging"
    assert "chunk_size" not in repr(result.to_dict()).lower()
    assert "hnsw" not in repr(result.to_dict()).lower()


def test_stage_records_preserves_source_ids_without_production_parameters():
    assert hasattr(staging, "stage_records")
    result = staging.stage_records(
        [
            {
                "source_id": "synthetic-staging-001",
                "title": "Synthetic staging record",
                "text": "Synthetic public-safe staging text.",
            }
        ]
    )

    assert result.status == "staged"
    assert result.records[0]["source_id"] == "synthetic-staging-001"
    assert result.records[0]["source_tier"] == "staging"
