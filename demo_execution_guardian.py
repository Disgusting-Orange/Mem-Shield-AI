"""
demo_execution_guardian.py
---------------------------
Standalone runnable demo for the Execution Runtime Guardian.
Run from the repo root: python demo/demo_execution_guardian.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from execution_guardian import ExecutionStep, ExecutionGuardian, StateStore

if __name__ == "__main__":
    guardian = ExecutionGuardian(StateStore(":memory:"))
    agent = "agent-1"

    # Simulate a normal step
    s1 = ExecutionStep(agent_id=agent, step_id="s1", action="fetch_weather",
                        params={"city": "Chennai"}, status="success",
                        result_payload="25C sunny", cost_estimate=0.002)
    guardian.record_step(s1)

    # Simulate a redundant repeat of the same call
    s2 = ExecutionStep(agent_id=agent, step_id="s2", action="fetch_weather",
                        params={"city": "Chennai"}, status="success",
                        result_payload="25C sunny", cost_estimate=0.002)
    guardian.record_step(s2, previous_step_id="s1")

    # Simulate a silent failure: reports success but payload has an error
    s3 = ExecutionStep(agent_id=agent, step_id="s3", action="update_memory",
                        params={"key": "profile"}, status="success",
                        result_payload="Traceback: NullPointerException",
                        cost_estimate=0.001)
    guardian.record_step(s3, previous_step_id="s2")

    # Simulate a loop: s4 -> s5 -> s4
    s4 = ExecutionStep(agent_id=agent, step_id="s4", action="reason_step",
                        status="success", cost_estimate=0.0005)
    s5 = ExecutionStep(agent_id=agent, step_id="s5", action="reason_step",
                        status="success", cost_estimate=0.0005)
    guardian.record_step(s4, previous_step_id="s3")
    guardian.record_step(s5, previous_step_id="s4")
    guardian.graphs[agent].add_edge("s5", "s4")  # closes the loop

    report = guardian.audit(agent)
    print("=== AUDIT REPORT ===")
    print("Loops found:", report["loops"])
    print("Silent failures:", [s.step_id for s in report["silent_failures"]])
    print("Redundant call pairs:", [(a.step_id, b.step_id) for a, b in report["redundant_calls"]])
    print("Estimated cost leak:", report["estimated_cost_leak"])
