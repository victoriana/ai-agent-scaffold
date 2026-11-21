# ai-agent-scaffold
**Mission:** Implement policy search (RAG) and an AI agent workflow for an internal employee Q&A service, plus explain general concepts for building responsive APIs (FastAPI) and connecting tools through a standard protocol (MCP).  
**Core Skills Tested:** Agentic AI Architecture • RAG • FastAPI • MCP (Model Context Protocol)

---

## 1. End-to-End Architecture One-Pager

```text
================================================================================
       TSC AI/ML OPS ONE-PAGER: OFFLINE INGESTION + ONLINE RAG + AGENT LOOP
================================================================================

PART 1: OFFLINE INGESTION (Builds Searchable Table: domainname_modelid)
--------------------------------------------------------------------------------
  [PDFs / Store SOPs]
           |
           v  1. Chunk into ~500-token natural text splits (~50-token overlap)
              2. Attach metadata (doc_id, page, allowed_roles, domain)
  [Chunk + Metadata Tuples]
           |
           v  3. Batch call Vertex AI Embeddor API (pinned model_id + chunk texts)
              4. Receive 1:1 float vectors back
  [Vector + Text + Metadata] ---> INSERT into pgvector table: domainname_modelid


PART 2: ONLINE RUNTIME API (Live 24/7 FastAPI Service: POST /ask)
--------------------------------------------------------------------------------
  [Employee User: Query + Role Header]
           |
           v
   __________________________________________________________________________

  | 2A. FASTAPI WRAPPER (main.py)                                            |
  | * Pre-process:  Pydantic validates JSON payload                          |
  | * Auth/Safety:  Depends() checks RBAC role; Input Guardrails block PII/  |
  |                 prompt injections                                        |
  | * Resilience:   lifespan pools; async + httpx timeouts & exp. retries    |
  |__________________________________________________________________________|
                                       |
                                       v
   __________________________________________________________________________

  | 2B-1. ONLINE RAG RETRIEVAL (rag.py)                                      |
  | 1. Embed live query using EXACT SAME pinned model_id                     |
  | 2. Pre-filter pgvector table by role metadata (WHERE role IN allowed)    |
  | 3. Hybrid Search: Dense Vector (meaning) + BM25 (exact SKU/keywords)     |
  | 4. Rerank top candidates -> keep top 3-5 chunks                          |
  |__________________________________________________________________________|
                                       |
                                       v
                              ___________________        NO (< 0.65)

                             | Top Score >= 0.65?|-------------------> ["I don't know"]
                             |___________________|                     (Safe Fallback)
                                       | YES
                                       v
   __________________________________________________________________________

  | 2B-2. BOUNDED AGENT LOOP (agent.py + tools.py)                           |
  |                                                                          |
  |   for step in range(MAX_STEPS = 5):                                      |
  |     [System Prompt + RAG Chunks + Query + Tool Schemas] ---> [LLM]       |
  |        |-- Final Text Answer? ---> BREAK & return answer + [doc_id]      |
  |        |-- Tool Call JSON?    ---> Run user-scoped tool in tools.py,     |
  |                                    append result to messages, LOOP AGAIN |
  |   (If MAX_STEPS hit -> abort & return safe fallback)                     |
  |__________________________________________________________________________|
                                       |
                                       v
   __________________________________________________________________________

  | 2A (Post-process): Pydantic formats JSON response (or SSE stream)        |
  |__________________________________________________________________________|


PART 3: CROSS-CUTTING AI/ML OPS (Wraps Every Step Above)
--------------------------------------------------------------------------------
  * OBSERVABILITY:     Log prompts, chunks, tools, latency, & \$ cost per trace
  * POLICY VERSIONING: Pin prompt templates (v1.2) & exact model snapshots
  * EVALS:             CI/CD + online checks for retrieval recall & faithfulness
  * ACCESS CONTROL:    Pre-filter vector DB by RBAC + user-scoped tool tokens
  * GUARDRAILS:        Input (PII/injections) + Output (JSON schema/fallbacks)
================================================================================
```

---

## 2. Implementation Summary (Coding Part)

* **Part 1 — Offline Ingestion (`ingest.py`):** Split domain PDFs/SOPs into ~500-token natural text/metadata tuples (~50-token overlap), batch-call Vertex AI's pinned embedding model to get 1:1 float vectors, and insert `[vector, text, metadata]` rows into `pgvector` table `domainname_modelid`.
* **Part 2A — FastAPI Wrapper (`main.py`):** Live 24/7 API traffic cop where Pydantic handles JSON pre/post-processing (or SSE streaming), while `Depends()`, input guardrails, `lifespan`, and `async`/`httpx` enforce RBAC access control, block prompt injections/PII, and manage connection pools, timeouts, and exponential retries.
* **Part 2B — Online RAG & Bounded Agent (`rag.py`, `agent.py`, `tools.py`):** Embed the live query with the same pinned `model_id`, pre-filter `domainname_modelid` by user role, run Hybrid Search (Vector + BM25) + Reranking, and trigger an `"I don't know"` fallback if `top_score < threshold`; otherwise run a bounded `MAX_STEPS` loop where the LLM calls user-scoped tools until returning a cited `[doc_id]` answer.

---

## 3. Written Concept Notes (Explanation Part)

### A. Building Responsive APIs (FastAPI)
* **Non-Blocking Async I/O (`async def` + `httpx.AsyncClient`):** Keeps the event loop free while waiting on slow external LLM or vector DB calls; never use blocking `time.sleep()` or `requests` inside `async` routes.
* **Streaming Responses (`StreamingResponse` + SSE):** Streams tokens (`text/event-stream`) incrementally as the LLM generates them, lowering perceived latency (Time-To-First-Token) instead of making users wait for the full completion.
* **Resilience & Lifecycle (`lifespan`, Timeouts, Retries):** Reuse persistent HTTP/DB connection pools via `lifespan`, enforce strict connect/read timeouts, and use exponential backoff retries for transient `429`/`5xx` upstream errors.
* **Fast Fail & Validation (`Pydantic` + `Depends()`):** Reject malformed payloads (`422`) and unauthorized roles (`403`) immediately before spending tokens or running vector queries.

### B. Connecting Tools Through a Standard Protocol (MCP — Model Context Protocol)
* **What It Is:** An open standard protocol (JSON-RPC based) that standardizes how AI applications (**MCP Hosts/Clients**) discover and invoke external tools, data, and prompts exposed by **MCP Servers**.
* **Why Use MCP ("USB-C for AI"):** Solves the `N × M` custom-integration problem—instead of writing custom tool wrappers per agent framework, you expose an API/DB once as an MCP server and any MCP-compliant agent can dynamically discover and call its capabilities.
* **3 Core MCP Primitives:**
  1. **Tools:** Executable actions with strict JSON Schemas (e.g., `check_store_inventory(sku, store_id)`).
  2. **Resources:** Read-only contextual data addressed by URI (e.g., `policy://returns/sop-04`).
  3. **Prompts:** Reusable, parameterized prompt templates hosted centrally by the server.
* **Security & Governance:** Enforces least privilege at the protocol boundary—the agent only sees declared tool schemas and executes with scoped user permissions rather than direct database credentials.

### C. 5 Core AI/ML Ops Production Rules
1. **Observability:** Log every prompt, retrieved chunk, tool call, latency, and token cost per trace to debug failures.
2. **Evaluation (Evals):** Run automated CI/CD and online checks (including LLM-as-a-Judge) over golden datasets for retrieval recall and answer faithfulness.
3. **Guardrails:** Validate inputs (block prompt injections/PII) before inference, and validate outputs (JSON schema, score thresholds, safe fallbacks) before delivery.
4. **Access Control:** Pre-filter vector search results by user RBAC metadata *before* ranking, and execute tools with user-scoped tokens.
5. **Policy Versioning:** Pin prompt templates, thresholds, and exact model IDs (`gemini-2.5-pro-001`) so every output is reproducible and safe to roll back.

