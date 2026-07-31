"""
test_execution_guardian.py
----------------------------
Basic tests for the Execution Runtime Guardian. Run with: pytest tests/
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from models import ExecutionStep
from guardian import ExecutionGuardian
from state_store import StateStore


def make_guardian():
    return ExecutionGuardian(StateStore(":memory:"))


def test_no_issues_on_clean_run():
    guardian = make_guardian()
    agent = "agent-clean"
    s1 = ExecutionStep(agent_id=agent, step_id="s1", action="fetch_data",
                        status="success", result_payload="ok", cost_estimate=0.001)
    guardian.record_step(s1)
    report = guardian.audit(agent)
    assert report["loops"] == []
    assert report["silent_failures"] == []
    assert report["redundant_calls"] == []
    assert report["estimated_cost_leak"] == 0.0


def test_detects_loop():
    guardian = make_guardian()
    agent = "agent-loop"
    s1 = ExecutionStep(agent_id=agent, step_id="s1", action="reason", cost_estimate=0.001)
    s2 = ExecutionStep(agent_id=agent, step_id="s2", action="reason", cost_estimate=0.001)
    guardian.record_step(s1)
    guardian.record_step(s2, previous_step_id="s1")
    guardian.graphs[agent].add_edge("s2", "s1")  # close the loop
    loops = guardian.detect_loops(agent)
    assert len(loops) == 1


def test_detects_silent_failure():
    guardian = make_guardian()
    agent = "agent-silent"
    s1 = ExecutionStep(agent_id=agent, step_id="s1", action="update_memory",
                        status="success", result_payload="Traceback: error",
                        cost_estimate=0.001)
    guardian.record_step(s1)
    failures = guardian.detect_silent_failures(agent)
    assert len(failures) == 1
    assert failures[0].step_id == "s1"


def test_detects_redundant_calls():
    guardian = make_guardian()
    agent = "agent-redundant"
    s1 = ExecutionStep(agent_id=agent, step_id="s1", action="fetch_weather",
                        params={"city": "Chennai"}, cost_estimate=0.002)
    s2 = ExecutionStep(agent_id=agent, step_id="s2", action="fetch_weather",
                        params={"city": "Chennai"}, cost_estimate=0.002)
    guardian.record_step(s1)
    guardian.record_step(s2, previous_step_id="s1")
    redundant = guardian.detect_redundant_calls(agent)
    assert len(redundant) == 1


if __name__ == "__main__":
    test_no_issues_on_clean_run()
    test_detects_loop()
    test_detects_silent_failure()
    test_detects_redundant_calls()
    print("All tests passed.")
