"""
guardian.py
-----------
The Execution Runtime Guardian itself: tracks an agent's live execution
as a graph of steps and flags loops, silent failures, redundant calls,
and estimated cost leaks.
"""

import networkx as nx
from collections import defaultdict
from typing import Optional

from models import ExecutionStep
from interfaces import BaseStateStore, BaseAlertSink
from state_store import StateStore
from config import FAILURE_SIGNATURES, REDUNDANCY_WINDOW_SECONDS


class ExecutionGuardian:
    def __init__(
        self,
        store: Optional[BaseStateStore] = None,
        alert_sink: Optional[BaseAlertSink] = None,
    ):
        self.store = store or StateStore()
        self.alert_sink = alert_sink
        # one directed graph per agent_id -> nodes are step_ids, edges are "next step"
        self.graphs: dict[str, nx.DiGraph] = defaultdict(nx.DiGraph)
        # keep recent steps in memory too, for fast redundancy checks
        self.recent_steps: dict[str, list[ExecutionStep]] = defaultdict(list)

    # -- ingestion -----------------------------------------------------
    def record_step(self, step: ExecutionStep, previous_step_id: Optional[str] = None):
        """
        Call this every time the agent takes a step.
        previous_step_id links this step to the one before it in the graph.
        """
        g = self.graphs[step.agent_id]
        g.add_node(step.step_id, data=step)
        if previous_step_id is not None:
            g.add_edge(previous_step_id, step.step_id)

        self.recent_steps[step.agent_id].append(step)
        self.store.save(step)

    # -- 1. loop detection ----------------------------------------------
    def detect_loops(self, agent_id: str) -> list[list[str]]:
        """
        Returns a list of cycles (each a list of step_ids) found in this
        agent's execution graph. A non-empty result means the agent is
        stuck repeating the same sequence of reasoning steps.
        """
        g = self.graphs[agent_id]
        try:
            cycles = list(nx.simple_cycles(g))
        except nx.NetworkXNoCycle:
            cycles = []
        return cycles

    # -- 2. silent failure detection -------------------------------------
    def detect_silent_failures(self, agent_id: str) -> list[ExecutionStep]:
        """
        Flags steps where status == "success" but the result payload
        actually contains a failure signature -- i.e. the agent *thinks*
        it succeeded but it didn't.
        """
        flagged = []
        for step in self.recent_steps[agent_id]:
            if step.status == "success" and step.result_payload:
                payload_lower = step.result_payload.lower()
                if any(sig in payload_lower for sig in FAILURE_SIGNATURES):
                    flagged.append(step)
        return flagged

    # -- 3. redundant call detection --------------------------------------
    def detect_redundant_calls(self, agent_id: str) -> list[tuple[ExecutionStep, ExecutionStep]]:
        """
        Flags pairs of steps with the same action + params within
        REDUNDANCY_WINDOW_SECONDS of each other -- these are wasted,
        cost-inflating repeat calls.
        """
        steps = self.recent_steps[agent_id]
        redundant_pairs = []
        # NOTE: O(n^2) brute-force comparison over recent steps. Fine for
        # hackathon-scale demos (recent_steps stays small). If you expect
        # long-running agents with thousands of steps, a cleaner version
        # would bucket steps by (action, params) into a dict and only
        # compare within each bucket -- ping me if you want that version.
        for i in range(len(steps)):
            for j in range(i + 1, len(steps)):
                a, b = steps[i], steps[j]
                same_call = (a.action == b.action and a.params == b.params)
                within_window = abs(b.timestamp - a.timestamp) <= REDUNDANCY_WINDOW_SECONDS
                if same_call and within_window:
                    redundant_pairs.append((a, b))
        return redundant_pairs

    # -- 4. cost-leak estimate ---------------------------------------------
    def estimate_cost_leak(self, agent_id: str) -> float:
        """
        Rough estimate of wasted cost = cost of every redundant call
        (the second call in each pair) + cost of every step inside a
        detected loop cycle.
        """
        leaked = 0.0

        for _, repeat in self.detect_redundant_calls(agent_id):
            leaked += repeat.cost_estimate

        g = self.graphs[agent_id]
        for cycle in self.detect_loops(agent_id):
            for step_id in cycle:
                node_data = g.nodes[step_id].get("data")
                if node_data:
                    leaked += node_data.cost_estimate

        return leaked

    # -- convenience: one call to check everything -------------------------
    def audit(self, agent_id: str) -> dict:
        """Run all checks at once and return a summary report."""
        report = {
            "loops": self.detect_loops(agent_id),
            "silent_failures": self.detect_silent_failures(agent_id),
            "redundant_calls": self.detect_redundant_calls(agent_id),
            "estimated_cost_leak": self.estimate_cost_leak(agent_id),
        }

        # Fire alerts via the sink (SNS in production, no-op locally)
        if self.alert_sink:
            if report["loops"]:
                self.alert_sink.send_alert(agent_id, "loop_detected", {
                    "cycles": report["loops"],
                })
            if report["silent_failures"]:
                self.alert_sink.send_alert(agent_id, "silent_failure", {
                    "step_ids": [s.step_id for s in report["silent_failures"]],
                })
            if report["redundant_calls"]:
                self.alert_sink.send_alert(agent_id, "redundant_calls", {
                    "pairs": [(a.step_id, b.step_id) for a, b in report["redundant_calls"]],
                })
            if report["estimated_cost_leak"] > 0:
                self.alert_sink.send_alert(agent_id, "cost_leak", {
                    "estimated_cost": report["estimated_cost_leak"],
                })

        return report
