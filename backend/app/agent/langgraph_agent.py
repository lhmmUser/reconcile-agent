# app/agent/langgraph_agent.py
from langchain_openai import ChatOpenAI   # or Gemini wrapper if you prefer
from langgraph.graph import StateGraph, END
from pydantic import BaseModel
from typing import Dict, Any
from tools.reconcile_tool import reconcile_orders_payments

# Define state
class AgentState(BaseModel):
    query: str
    result: Dict[str, Any] | None = None

# LLM
llm = ChatOpenAI(model="gpt-4o", temperature=0.1)

# Graph
workflow = StateGraph(AgentState)

# Step 1: Interpret + decide
def decide(state: AgentState):
    return "reconcile"

workflow.add_node("reconcile", reconcile_orders_payments)
workflow.set_entry_point("reconcile")
workflow.add_edge("reconcile", END)

graph = workflow.compile()
