# main.py : Clean FastAPI Service (/health, /mcp/tools, /ask, /ask/stream)
# Separates JSON (POST /ask) from SSE streaming (POST /ask/stream), validates role headers via Depends, and keeps guardrails concise.

import asyncio
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent import run_agent
from tools import MCP_TOOLS

app = FastAPI(title="Employee Policy & Agent Service")

VALID_ROLES = {"employee", "manager", "hr_admin"}
BLOCKED_PHRASES = ("ignore previous instructions", "reveal system prompt", "bypass rbac")


class AskRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=1000)


class Citation(BaseModel):
    doc_id: str
    section: str
    score: float


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]
    fallback_triggered: bool
    steps_taken: int
    latency_ms: float


def get_role(x_user_role: str = Header(default="employee")) -> str:
    if x_user_role not in VALID_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid role")
    return x_user_role


def check_guardrails(query: str) -> None:
    q = query.lower()
    if any(phrase in q for phrase in BLOCKED_PHRASES):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Blocked by input guardrail")


async def _stream_words(text: str) -> AsyncGenerator[str, None]:
    for word in text.split():
        yield f"data: {word}\n\n"
        await asyncio.sleep(0.02)
    yield "data: [DONE]\n\n"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/mcp/tools")
def list_tools(role: str = Depends(get_role)) -> dict:
    return {"role": role, "tools": MCP_TOOLS}


@app.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest, role: str = Depends(get_role)) -> AskResponse:
    check_guardrails(payload.query)
    res = run_agent(query=payload.query, user_role=role)
    return AskResponse(
        answer=res.answer,
        citations=[Citation(**c) for c in res.citations],
        fallback_triggered=res.fallback_triggered,
        steps_taken=res.steps_taken,
        latency_ms=res.latency_ms,
    )


@app.post("/ask/stream")
async def ask_stream(payload: AskRequest, role: str = Depends(get_role)) -> StreamingResponse:
    check_guardrails(payload.query)
    res = run_agent(query=payload.query, user_role=role)
    return StreamingResponse(_stream_words(res.answer), media_type="text/event-stream")
