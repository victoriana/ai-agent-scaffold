import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent import run_employee_agent
from tools import MCP_TOOLS_LIST

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("employee-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Startup: initializing shared async HTTP client pool")
    app.state.http_client = httpx.AsyncClient(timeout=httpx.Timeout(connect=3.0, read=15.0, write=5.0, pool=5.0))
    yield
    logger.info("Shutdown: closing shared async HTTP client pool")
    await app.state.http_client.aclose()


app = FastAPI(title="Internal Employee Policy & Agent API", lifespan=lifespan)


class AskRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=1000)
    stream: bool = False


class CitationOut(BaseModel):
    doc_id: str
    page: int
    score: float


class AskResponse(BaseModel):
    answer: str
    citations: list[CitationOut] = []
    fallback_triggered: bool
    steps_taken: int
    latency_ms: float


def get_current_role(x_user_role: str = Header(default="employee")) -> str:
    if x_user_role not in {"employee", "manager", "hr_admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized role")
    return x_user_role


def enforce_input_guardrails(query: str) -> None:
    blocked = ["ignore previous instructions", "reveal system prompt", "bypass rbac"]
    if any(phrase in query.lower() for phrase in blocked):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query blocked by input guardrail")


async def sse_token_stream(answer: str) -> AsyncGenerator[str, None]:
    for token in answer.split():
        yield f"data: {token}\n\n"
        await asyncio.sleep(0.03)
    yield "data: [DONE]\n\n"


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/mcp/tools")
def list_mcp_tools(role: str = Depends(get_current_role)):
    """Exposes available MCP tool schemas for standardized tool discovery."""
    return {"tools": MCP_TOOLS_LIST}


@app.post("/ask", response_model=AskResponse)
async def ask_policy_agent(payload: AskRequest, role: str = Depends(get_current_role)):
    enforce_input_guardrails(payload.query)
    result = run_employee_agent(query=payload.query, user_role=role)

    if payload.stream:
        return StreamingResponse(
            sse_token_stream(result.answer),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    return AskResponse(
        answer=result.answer,
        citations=[CitationOut(**c) for c in result.citations],
        fallback_triggered=result.fallback_triggered,
        steps_taken=result.steps_taken,
        latency_ms=result.latency_ms,
    )
