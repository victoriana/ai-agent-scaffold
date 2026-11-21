# ai-agent-scaffold

Internal employee Q&A service implementing offline policy ingestion, RBAC-filtered policy search, a bounded AI agent loop, MCP-style tool schemas, and responsive FastAPI endpoints (JSON + SSE streaming)[cite: 2, 3, 5, 6, 7, 8].

## 1. End-to-End Architecture

```text
================================================================================
              OFFLINE INGESTION + ONLINE POLICY AGENT ARCHITECTURE
================================================================================

PART 1: OFFLINE INGESTION (ingest.py -> policy_index.json)
--------------------------------------------------------------------------------
  [Raw Policy Docs / SOPs]
         |
         v  1. Chunk text into overlapping windows (chunk_text)
            2. Attach metadata (chunk_id, doc_id, section, allowed_roles)
            3. (Production swap: batch embed + upsert into vector DB)
  [policy_index.json]


PART 2: ONLINE RUNTIME (main.py -> rag.py -> agent.py + tools.py)
--------------------------------------------------------------------------------
  [Employee Request: JSON body + X-User-Role header]
         |
         v
  +--------------------------------------------------------------------------+
  | 1. FASTAPI LAYER (main.py)                                               |
  |    * Validates role via Depends(get_role) -> 403 if unauthorized         |
  |    * Validates query payload via Pydantic AskRequest                     |
  |    * Runs input guardrail check -> 400 on blocked phrases                |
  |    * Routes to GET /health, GET /mcp/tools, POST /ask, or POST /ask/stream|
  +--------------------------------------------------------------------------+
         |
         v
  +--------------------------------------------------------------------------+
  | 2. POLICY SEARCH / RAG (rag.py)                                          |
  |    * Loads policy_index.json (auto-seeds via ingest.py if missing)       |
  |    * Pre-filters chunks by user_role BEFORE scoring (RBAC)               |
  |    * Scores token overlap + exact doc_id boost                           |
  |    * Top score < min_score (0.25)? -> return safe fallback immediately   |
  +--------------------------------------------------------------------------+
         | (hits found)
         v
  +--------------------------------------------------------------------------+
  | 3. BOUNDED AGENT LOOP (agent.py) + MCP TOOLS (tools.py)                  |
  |                                                                          |
  |    for step in range(MAX_STEPS = 4):                                     |
  |      * _plan_next_action() decides: call MCP tool OR return final answer |
  |      * If tool call -> call_mcp_tool() enforces role check in tools.py   |
  |        (get_pto_balance / check_expense_status) & appends tool result    |
  |      * If final answer -> return answer, citations, steps_taken, latency |
  |    * If MAX_STEPS reached -> return safe fallback                        |
  +--------------------------------------------------------------------------+
         |
         v
  +--------------------------------------------------------------------------+
  | 4. RESPONSE DELIVERY (main.py)                                           |
  |    * POST /ask        -> Structured JSON (AskResponse)                   |
  |    * POST /ask/stream -> Server-Sent Events (text/event-stream)          |
  +--------------------------------------------------------------------------+
```
---
## 2. Repository Structure & Implementation

* `ingest.py`: Offline ingestion pipeline that splits policy text into overlapping chunks, attaches `chunk_id`, `doc_id`, `section`, and `allowed_roles` metadata, and writes `policy_index.json` (designed to swap in batch embeddings and vector store upserts in production).
* `rag.py`: Loads `policy_index.json` via `load_policy_chunks()`, filters chunks by `user_role` prior to scoring, computes token-overlap scores with a `doc_id` match boost, and triggers a safe fallback when the top score is below `min_score`.
* `tools.py`: Declares MCP-style tool schemas (`MCP_TOOLS`) and dispatches calls (`call_mcp_tool`) for `get_pto_balance` and `check_expense_status`, enforcing user-role authorization inside the tool handlers.
* `agent.py`: Coordinates `search_policies` and a bounded `MAX_STEPS = 4` execution loop (`run_agent`), returning `answer`, `citations`, `fallback_triggered`, `steps_taken`, and `latency_ms`.
* `main.py`: Exposes `GET /health`, `GET /mcp/tools`, `POST /ask` (JSON), and `POST /ask/stream` (SSE), wired with `Depends(get_role)`, Pydantic models, and input guardrails.

## 3. Core Concepts Summary

### Building Responsive APIs (FastAPI)
* **Async I/O & Non-Blocking Routes**: Use `async def` and async clients (`httpx.AsyncClient`) for network, LLM, and vector DB I/O so worker threads are not blocked while waiting on external calls.
* **Streaming for Perceived Latency**: `POST /ask/stream` uses `StreamingResponse` with `text/event-stream` (SSE) so clients receive incremental tokens rather than waiting for full completion.
* **Fail Fast & Guardrails**: Validate headers/roles (`Depends`) and payloads (`Pydantic`), and block unsafe inputs early before running retrieval or tool logic.

### Connecting Tools via MCP (Model Context Protocol)
* **Standardized Tool Interface**: MCP standardizes how clients discover tools (`GET /mcp/tools` / `MCP_TOOLS` JSON Schemas) and invoke them (`call_mcp_tool`) without hardcoding custom glue for every model or client.
* **Core Primitives**: **Tools** (executable actions with JSON input schemas), **Resources** (read-only context), and **Prompts** (reusable prompt templates).
* **Defense-in-Depth Security**: Combine RAG document-level RBAC filtering with tool-level role checks so agents only access authorized policies and records.

### Production AI/ML Ops Practices
* **Decoupled Offline vs. Online Pipelines**: Separate document chunking/indexing (`ingest.py`) from low-latency query serving (`rag.py` + `main.py`) so updates do not block live traffic.
* **Bounded Execution & Fallbacks**: Cap agent steps (`MAX_STEPS`) and trigger explicit `"I don't know"` fallbacks when policy confidence is below threshold.
* **Observability & Versioning**: Log latency, step counts, tool calls, and pin model/prompt versions to keep behavior traceable and reproducible.
