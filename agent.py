# agent.py — Bounded Agent Loop + Grounded Synthesis
# Runs RAG first, triggers the fallback if policy coverage is missing, and executes a bounded tool loop (MAX_STEPS = 4) before returning a cited answer.

import json
import logging
import time
from dataclasses import dataclass

from rag import PolicyHit, search_policies
from tools import MCP_TOOLS, call_mcp_tool

logger = logging.getLogger("policy-agent")

MAX_STEPS = 4
MODEL_ID = "gemini-2.5-pro-001"


@dataclass
class AgentResult:
    answer: str
    citations: list[dict]
    fallback_triggered: bool
    steps_taken: int
    latency_ms: float


def _plan_next_action(query: str, hits: list[PolicyHit], tool_results: list[str], step: int) -> dict:
    """Stubbed LLM step: calls an MCP tool when an ID is mentioned, otherwise answers from policy."""
    q_lower = query.lower()

    if step == 0 and not tool_results:
        if "emp-101" in q_lower or "emp-202" in q_lower:
            emp_id = "EMP-202" if "emp-202" in q_lower else "EMP-101"
            return {"action": "tool", "name": "get_pto_balance", "args": {"employee_id": emp_id}}
        if "exp-500" in q_lower or "exp-501" in q_lower:
            claim_id = "EXP-501" if "exp-501" in q_lower else "EXP-500"
            return {"action": "tool", "name": "check_expense_status", "args": {"claim_id": claim_id}}

    policy_summary = " ".join(f"[{h.doc_id}] {h.text}" for h in hits)
    tool_note = f" Tool result: {tool_results[-1]}" if tool_results else ""
    return {"action": "answer", "content": f"{policy_summary}{tool_note}".strip()}


def run_agent(query: str, user_role: str) -> AgentResult:
    start = time.perf_counter()
    hits, fallback = search_policies(query=query, user_role=user_role)

    if fallback:
        latency = round((time.perf_counter() - start) * 1000, 2)
        logger.info("Fallback triggered | model=%s latency=%.2fms", MODEL_ID, latency)
        return AgentResult(
            answer="I don't have enough verified company policy information to answer that question.",
            citations=[],
            fallback_triggered=True,
            steps_taken=0,
            latency_ms=latency,
        )

    tool_outputs: list[str] = []
    _available_tool_names = [t["name"] for t in MCP_TOOLS]

    for step in range(MAX_STEPS):
        decision = _plan_next_action(query, hits, tool_outputs, step)

        if decision["action"] == "tool":
            result = call_mcp_tool(decision["name"], decision["args"], user_role=user_role)
            tool_outputs.append(json.dumps(result))
            continue

        latency = round((time.perf_counter() - start) * 1000, 2)
        citations = [{"doc_id": h.doc_id, "section": h.section, "score": h.score} for h in hits]
        logger.info("Agent completed | steps=%d model=%s latency=%.2fms", step + 1, MODEL_ID, latency)
        return AgentResult(
            answer=decision["content"],
            citations=citations,
            fallback_triggered=False,
            steps_taken=step + 1,
            latency_ms=latency,
        )

    latency = round((time.perf_counter() - start) * 1000, 2)
    return AgentResult(
        answer="Unable to complete request within maximum steps.",
        citations=[],
        fallback_triggered=True,
        steps_taken=MAX_STEPS,
        latency_ms=latency,
    )
