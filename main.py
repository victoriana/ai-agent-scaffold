from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agent import AgentWorkflow

app = FastAPI(title="Employee Policy Assistant", version="1.0")
agent = AgentWorkflow()

class QueryRequest(BaseModel):
    question: str
    user_id: str  # For RAG context/personalization

class QueryResponse(BaseModel):
    answer: str
    sources: list[str]
    confidence: float

@app.post("/ask", response_model=QueryResponse)
async def ask_question(request: QueryRequest):
    try:
        # Call your agent workflow
        result = await agent.run(request.question, request.user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "healthy"}
