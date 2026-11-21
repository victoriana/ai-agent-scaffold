# agent.py: Bounded MAX_STEPS Agent Workflow + Observability Tracing
import json
import logging
import time
from dataclasses import dataclass

from rag import SearchHit, search_policies
from tools import MCP_TOOLS_LIST, mcp_call_tool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("employee-agent")

MAX_STEPS = 5
MODEL_ID = "gemini-2.5-pro-001"
PROMPT_VERSION = "v1.0"


@dataclass
class AgentResponse:
    answer: str
    citations: list[dict]
    fallback_triggered: bool
    steps_taken: int
    latency_ms: float


def simulate_llm(messages: list[dict], step: int) -> dict:
    """
    Simulates an LLM deciding whether to invoke an MCP tool (Step 0)
    or synthesize the final policy-grounded answer (Step 1).
    """
    user_q = next((m["content"] for m in messages if m["role"] == "user"), "").lower()

    if step == 0 and "emp-101" in user_q:
        return {
            "type": "tool_call",
            "name": "get_pto_balance",
            "arguments": {"employee_id": "EMP-101"},
        }
    if step == 0 and "exp-500" in user_q:
        return {
            "type": "tool_call",
            "name": "check_expense_status",
            "arguments": {"claim_id": "EXP-500"},
        }

    tool_outputs = [m["content"] for m in messages if m["role"] == "tool"]
    tool_summary = f" Live record lookup: {tool_outputs[-1]}." if tool_outputs else ""
    return {
        "type": "final_answer",
        "content": f"According to company policy, your request follows standard guidelines.{tool_summary}",
    }


def run_employee_agent(query: str, user_role: str) -> AgentResponse:
    start = time.perf_counter()

    # 1. Policy Search (RAG with RBAC filter + score threshold)
    hits: list[SearchHit]
    hits, fallback = search_policies(query=query, user_role=user_role)
    if fallback:
        latency = round((time.perf_counter() - start) * 1000, 2)
        logger.info(f"[TRACE] Fallback | model={MODEL_ID} prompt={PROMPT_VERSION} latency={latency}ms")
        return AgentResponse(
            answer="I don't have enough verified company policy information to answer that question.",
            citations=[],
            fallback_triggered=True,
            steps_taken=0,
            latency_ms=latency,
        )

    # 2. Construct grounded prompt + MCP tool definitions
    context = "\n".join(f"[{h.doc_id}, p.{h.page}]: {h.text}" for h in hits)
    messages = [
        {
            "role": "system",
            "content": (
                f"Answer ONLY from the policy context below and cite [doc_id]. "
                f"Available MCP tools: {[t['name'] for t in MCP_TOOLS_LIST]}\n{context}"
            ),
        },
        {"role": "user", "content": query},
    ]

    # 3. Bounded Agent Execution Loop (MAX_STEPS guard)
    for step in range(MAX_STEPS):
        decision = simulate_llm(messages, step)

        if decision["type"] == "final_answer":
            latency = round((time.perf_counter() - start) * 1000, 2)
            citations = [{"doc_id": h.doc_id, "page": h.page, "score": h.score} for h in hits]
            logger.info(
                f"[TRACE] Success | steps={step + 1} model={MODEL_ID} "
                f"prompt={PROMPT_VERSION} latency={latency}ms"
            )
            return AgentResponse(
                answer=decision["content"],
                citations=citations,
                fallback_triggered=False,
                steps_taken=step + 1,
                latency_ms=latency,
            )

        if decision["type"] == "tool_call":
            result = mcp_call_tool(
                tool_name=decision["name"],
                arguments=decision["arguments"],
                user_role=user_role,
            )
            messages.append({"role": "tool", "name": decision["name"], "content": json.dumps(result)})

    # 4. Safe fallback if MAX_STEPS exceeded
    latency = round((time.perf_counter() - start) * 1000, 2)
    logger.warning(f"[TRACE] MAX_STEPS ({MAX_STEPS}) reached | latency={latency}ms")
    return AgentResponse(
        answer="Unable to complete request within maximum reasoning steps.",
        citations=[],
        fallback_triggered=True,
        steps_taken=MAX_STEPS,
        latency_ms=latency,
    )
