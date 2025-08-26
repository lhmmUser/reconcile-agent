# app/main.py
from __future__ import annotations

import os
import json
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Your feature routers
from app.routers.reconcile import router as reconcile_router
from app.routers.razorpay_export import router as razorpay_router

# LangGraph / LangChain
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain.tools import tool
import httpx


# --------------------------------------------------------------------------------------
# FastAPI app
# --------------------------------------------------------------------------------------
app = FastAPI(title="Diffrun Admin Backend", version="1.0.0")

# CORS (tighten origins in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include your routers
app.include_router(reconcile_router)
app.include_router(razorpay_router)


# --------------------------------------------------------------------------------------
# Tool: call your existing reconcile endpoint and return JSON (as a string)
#   NOTE: Make it SYNC + return a STRING. LangGraph/LC tools work very reliably this way.
# --------------------------------------------------------------------------------------
API_BASE = (os.getenv("INTERNAL_API_BASE") or "http://127.0.0.1:8000").rstrip("/")

@tool("tool_reconcile", return_direct=False)
def tool_reconcile(
    from_date: str | None = None,
    to_date: str | None = None,
    na_status: str = "captured",
    case_insensitive_ids: bool = False,
    max_fetch: int = 200000,
) -> str:
    """
    Reconcile Razorpay payments vs Mongo orders using the backend endpoint.
    Returns a JSON STRING with keys: summary, na_payment_ids, na_by_status.
    """
    params = {
        "na_status": na_status,
        "case_insensitive_ids": str(bool(case_insensitive_ids)).lower(),
        "max_fetch": str(int(max_fetch)),
    }
    if from_date:
        params["from_date"] = from_date
    if to_date:
        params["to_date"] = to_date

    url = f"{API_BASE}/reconcile/vlookup-payment-to-orders/auto"
    try:
        # sync request (works fine inside LangChain tool)
        resp = httpx.get(url, params=params, timeout=120.0)
        resp.raise_for_status()
        # Ensure we return a JSON STRING
        return json.dumps(resp.json(), separators=(",", ":"))
    except httpx.HTTPError as e:
        # Return JSON string describing the error (agent will still surface it)
        return json.dumps({"error": f"tool_reconcile failed: {str(e)}"}, separators=(",", ":"))


# --------------------------------------------------------------------------------------
# LLM + Agent (LangGraph prebuilt ReAct agent)
#   IMPORTANT: We instruct the agent to output ONLY the tool's JSON verbatim.
# --------------------------------------------------------------------------------------
def _get_llm():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    # Keep deterministic for ops (temperature 0)
    return ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), temperature=0)

AGENT_SYSTEM_PROMPT = (
    "You are an operations agent for payments reconciliation. "
    "When the user asks in natural language, call the tool 'tool_reconcile' with the appropriate "
    "arguments (from_date, to_date, na_status default 'captured'). "
    "AFTER the tool returns, OUTPUT EXACTLY the JSON string returned by the tool. "
    "Do not add any extra words before or after. Do not summarize. "
    "Your final answer must be valid minified JSON."
)

agent = create_react_agent(
    model=_get_llm(),
    tools=[tool_reconcile],
    prompt=AGENT_SYSTEM_PROMPT,
)


# --------------------------------------------------------------------------------------
# Agent endpoint: returns a clean JSON object to the UI
# --------------------------------------------------------------------------------------
from pydantic import BaseModel
from typing import Any, Dict, List, Union

# LangChain message types
try:
    from langchain_core.messages import BaseMessage  # newer
except Exception:
    from langchain.schema import BaseMessage  # fallback for older versions

class AgentRequest(BaseModel):
    message: str

class AgentResponse(BaseModel):
    result: Dict[str, Any]  # parsed JSON from tool_reconcile

def _extract_text(content: Any) -> Union[str, None]:
    """Return the first textual payload from a message.content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # OpenAI-style multi-part content
        for part in content:
            # part can be dict-like ({"type":"text","text":"..."}) or object with .text
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                return part["text"]
            txt = getattr(part, "text", None)
            if isinstance(txt, str):
                return txt
    return None

def _find_last_json_text(messages: List[BaseMessage]) -> Union[str, None]:
    """Scan messages from the end and return the last JSON-looking text."""
    for msg in reversed(messages):
        text = _extract_text(getattr(msg, "content", None))
        if not isinstance(text, str):
            continue
        t = text.strip()
        if t.startswith("{") and t.endswith("}"):
            return t
    # fallback: return last non-empty text even if not JSON
    for msg in reversed(messages):
        text = _extract_text(getattr(msg, "content", None))
        if isinstance(text, str) and text.strip():
            return text
    return None

@app.post("/agent/run", response_model=AgentResponse)
async def run_agent(req: AgentRequest):
    """
    Natural language entrypoint.
    Body: { "message": "reconcile 2025-08-15 to 2025-08-25 captured only" }
    Returns parsed JSON from tool_reconcile (summary, na_payment_ids, etc.)
    """
    try:
        out = await agent.ainvoke({"messages": [{"role": "user", "content": req.message}]})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {e}")

    # The prebuilt agent returns a dict with a 'messages' list of LangChain BaseMessage objects.
    messages = None
    if isinstance(out, dict):
        messages = out.get("messages") or out.get("result", {}).get("messages")
    if messages is None:
        # Some builds may return the list directly
        if isinstance(out, list):
            messages = out

    if not isinstance(messages, list) or not messages:
        return AgentResponse(result={"error": "No messages from agent", "raw": str(out)[:2000]})

    text = _find_last_json_text(messages)
    if not isinstance(text, str):
        return AgentResponse(result={"error": "No parsable assistant text", "raw": str(out)[:2000]})

    # Parse the JSON (the tool returns a JSON string)
    import json
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return AgentResponse(result={"error": "Assistant did not return valid JSON", "raw_text": text[:2000]})

    return AgentResponse(result=parsed)
