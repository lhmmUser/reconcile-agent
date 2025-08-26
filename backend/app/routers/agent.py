# app/routers/agent.py
from fastapi import APIRouter
from pydantic import BaseModel
from app.agent.langgraph_agent import graph, AgentState

router = APIRouter(prefix="/agent", tags=["agent"])

class AgentRequest(BaseModel):
    message: str

@router.post("/run")
async def run_agent(req: AgentRequest):
    # Give the agent the natural language message
    final_state = await graph.ainvoke({"query": req.message})
    return {"summary": final_state["result"]}
