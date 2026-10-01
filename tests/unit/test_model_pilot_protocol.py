from pathlib import Path
import runpy

import pytest

CHECK = runpy.run_path(str(
    Path(__file__).resolve().parents[2] / "scripts/run_bounded_model_pilot.py"
))["unexpected_actions"]


def test_cli_description_warning_is_not_a_model_tool_call():
    event = {"item": {"type": "error", "message":
                      "Skill descriptions were shortened to fit the 2% skills context budget."}}
    assert CHECK([event]) == []


@pytest.mark.parametrize("kind", ["command_execution", "mcp_tool_call", "file_change", "web_search"])
def test_out_of_protocol_tools_are_rejected(kind):
    event = {"item": {"type": kind}}
    assert CHECK([event]) == [event]


def test_unknown_error_is_not_silently_ignored():
    event = {"item": {"type": "error", "message": "unknown tool failure"}}
    assert CHECK([event]) == [event]
