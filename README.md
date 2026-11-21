# ai-agent-scaffold
Architect RAG Pipeline, Implement Agent Workflow, Build FastAPI Endpoint, Implement MCP (Model Context Protocol)

## Architecture One-Pager

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
  [Sales Floor User: Query + Role Header]
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

## Abbreviated Written Summary

* **Part 1 — Offline Ingestion:** Split domain PDFs/SOPs into ~500-token natural text/metadata tuples (~50-token overlap), batch-call Vertex AI's pinned embedding model to get 1:1 float vectors, and insert `[vector, text, metadata]` rows into `pgvector` table `domainname_modelid`.
* **Part 2A — FastAPI Wrapper (`main.py`):** Live 24/7 API traffic cop where Pydantic handles JSON pre/post-processing (or SSE streaming), while `Depends()`, input guardrails, `lifespan`, and `async`/`httpx` enforce user access (RBAC), block bad prompts/PII, and manage connection pools, timeouts, and exponential retries.
* **Part 2B — Online RAG & Bounded Agent (`rag.py`, `agent.py`, `tools.py`):** Embed the live query with the same pinned `model_id`, pre-filter `domainname_modelid` by user role, run Hybrid Search (Vector + BM25) + Reranking, and trigger an `"I don't know"` fallback if `top_score < threshold`; otherwise run a bounded `MAX_STEPS` loop where the LLM calls user-scoped tools until returning a cited `[doc_id]` answer.

## 5 Core AI/ML Ops Rules (TSC Production Reliability)

1. **Observability:** Log every prompt, retrieved chunk, tool call, latency, and token cost per request trace so you can debug failures.
2. **Evaluation (Evals):** Run automated CI/CD and online checks (including LLM-as-a-Judge) over golden datasets to verify retrieval recall and answer faithfulness without hallucination.
3. **Guardrails:** Validate user inputs (block prompt injections/PII) before LLM inference, and validate outputs (enforce JSON schema, safe fallbacks, and approval gates) before returning them.
4. **Access Control:** Filter vector search results by the user's permissions (`tenant_id`/`role`) *before* retrieving chunks, and run tools with user-scoped credentials so private data never leaks.
5. **Policy Versioning:** Never hardcode floating prompts or model aliases—version prompt templates, guardrail thresholds, and exact model IDs (`gemini-2.5-pro-001`) so every response is reproducible and safe to roll back.

```
