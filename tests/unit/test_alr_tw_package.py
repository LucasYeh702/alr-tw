def test_alr_tw_package_exposes_public_version_and_harness():
    import alr_tw
    from alr_tw.harness.orchestrator import run_agentic_demo

    trace = run_agentic_demo("民法第184條 押金", scenario="pass_official_source")

    assert alr_tw.__version__ == "0.4.0"
    assert trace.schema_version == "alr-tw.agentic_trace/v1"
    assert trace.final_action == "answer"
