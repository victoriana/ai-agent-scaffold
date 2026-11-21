# ai-agent-scaffold

Internal employee Q&A service implementing offline policy ingestion, RBAC-filtered policy search, a bounded AI agent loop, MCP-style tool schemas, and responsive FastAPI endpoints (JSON + SSE streaming).

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

## 4. 45-Minute Assessment Checklist

### A. End-to-End Code Walkthrough (Trace Before Test)
* [ ] **`ingest.py`:** Trace how raw policy records get split into overlapping chunks (`chunk_text`) and saved with metadata (`chunk_id`, `doc_id`, `section`, `allowed_roles`) into `policy_index.json`.
* [ ] **`rag.py`:** Trace `search_policies(query, user_role)`—loading the index (auto-seeding if missing), filtering by `user_role` *before* scoring, computing token overlap + exact `doc_id` boost, and returning `([], True)` (fallback) when `top_score < min_score`.
* [ ] **`agent.py`:** Trace `run_agent(query, user_role)`—handling a RAG fallback (`steps_taken=0`), running `for step in range(MAX_STEPS):`, calling `call_mcp_tool(...)` when `_plan_next_action` chooses a tool, appending tool output, and returning a final answer with citations and `latency_ms`.
* [ ] **`tools.py`:** Trace `MCP_TOOLS` (the JSON schemas) and `call_mcp_tool`—how `get_pto_balance` and `check_expense_status` run and enforce role checks (`user_role`).
* [ ] **`main.py`:** Trace `get_role` (`403` on invalid role), `check_guardrails` (`400` on blocked phrases), Pydantic `AskRequest`/`AskResponse`, `POST /ask`, `POST /ask/stream`, and `GET /mcp/tools`.

### B. No-Notes Coding Tips (Syntax-Check Environment)
* [ ] **Imports & types:** Double-check standard library and FastAPI imports (`dataclass`, `Field`, `Header`, `Depends`, `HTTPException`, `status`, `StreamingResponse`, `AsyncGenerator`, `Any`) so nothing is left undefined.
* [ ] **Bounded loop exits:** Ensure every `for step in range(MAX_STEPS):` loop has a clear return/break path plus a safe fallback return if `MAX_STEPS` is reached.
* [ ] **Consistent return shapes & keys:** Keep dictionary keys (`doc_id`, `section`, `score`, `employee_id`, `claim_id`) and dataclass fields aligned across callers and Pydantic response models.
* [ ] **Edge cases:** Handle empty/stopword-only queries, unauthorized roles (`403`), blocked injection phrases (`400`), and low-confidence retrieval (`fallback_triggered=True`).

### C. Test Environment & Verbal Wrap-Up Prep
* [ ] **Environment & browser:** Set aside 45 uninterrupted minutes and use a clean browser setup on your test machine as recommended.
* [ ] **Pacing:** Keep the initial code implementation clean and working first, leaving time to verify logic and explain design trade-offs clearly.
* [ ] **Verbal talking points:** Practice explaining *why* you chose async I/O and SSE streaming in FastAPI, how MCP standardizes tool discovery/invocation, how RBAC + score thresholds prevent leaks/hallucinations, and how you'd swap in embeddings, a vector DB, and a real LLM in production.

## 5. Verification & Local Test Summary

* **Offline Ingestion (`ingest.py`)**: Ran `python ingest.py` to chunk the policy documents and generate `policy_index.json` (3 chunks) prior to serving queries.
* **Server Startup (`main.py`)**: Installed `fastapi` and `uvicorn` into Python 3.11 and launched the service via `/c/Users/subspaceling/AppData/Local/Programs/Python/Python311/python.exe -m uvicorn main:app --reload` on `http://127.0.0.1:8000`.
* **Endpoint & Behavior Checks (`curl`)**: Verified `200 OK` responses across all endpoints and role/streaming behaviors in a second terminal:
  ```bash
  curl [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
  curl -H "X-User-Role: employee" [http://127.0.0.1:8000/mcp/tools](http://127.0.0.1:8000/mcp/tools)

  curl -X POST [http://127.0.0.1:8000/ask](http://127.0.0.1:8000/ask) \
    -H "Content-Type: application/json" \
    -H "X-User-Role: employee" \
    -d '{"query": "How much PTO do I accrue?"}'

  curl -X POST [http://127.0.0.1:8000/ask](http://127.0.0.1:8000/ask) \
    -H "Content-Type: application/json" \
    -H "X-User-Role: employee" \
    -d '{"query": "What is the spot bonus limit?"}'

  curl -X POST [http://127.0.0.1:8000/ask](http://127.0.0.1:8000/ask) \
    -H "Content-Type: application/json" \
    -H "X-User-Role: manager" \
    -d '{"query": "What is the spot bonus limit?"}'

  curl -N -X POST [http://127.0.0.1:8000/ask/stream](http://127.0.0.1:8000/ask/stream) \
    -H "Content-Type: application/json" \
    -H "X-User-Role: employee" \
    -d '{"query": "How much PTO do I accrue?"}'
  ```

## 6. How Your Scaffold Maps to the Assessment Criteria

* **Policy Search & RAG (`ingest.py`, `rag.py`):** Offline policy chunking with `allowed_roles` metadata and role-filtered search with a minimum score fallback directly addresses internal policy search and RAG fundamentals.
* **AI Agent Workflow (`agent.py`):** A bounded loop (`MAX_STEPS = 4`) that plans next steps, invokes tools, appends results, and returns answers with citations, step counts, and latency matches the agent workflow requirement.
* **Building Responsive APIs (`main.py`):** Using FastAPI with `async def` routes, header/role dependency validation, Pydantic schemas, input guardrails, JSON responses (`POST /ask`), and SSE streaming (`POST /ask/stream`) covers responsive API design.
* **Connecting Tools Through a Standard Protocol (`tools.py`, `GET /mcp/tools`):** Defining JSON-schema tool specifications (`MCP_TOOLS`), exposing tool discovery, and executing role-checked tool calls (`get_pto_balance`, `check_expense_status`) reflects MCP-style tool standardization.
* **45-Minute Scope & Verbal Concepts:** Keeping each module focused, clean, and self-contained makes it realistic to build or adapt under a 45-minute window while giving you concrete code examples to explain design trade-offs verbally.
