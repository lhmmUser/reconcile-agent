# tools/reconcile_tool.py
from langchain.tools import tool
import httpx, os
from typing import Optional, Dict, Any

API_BASE = os.getenv("INTERNAL_API_BASE", "http://127.0.0.1:8000")

@tool("reconcile_orders_payments", return_direct=False)
async def reconcile_orders_payments(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    na_status: str = "captured",
    case_insensitive_ids: bool = False,
    max_fetch: int = 200000,
) -> Dict[str, Any]:
    """Reconcile Razorpay payments vs Mongo orders. 
    Args:
        from_date: start date (YYYY-MM-DD)
        to_date: end date (YYYY-MM-DD)
        na_status: Only include NA payments of this status
        case_insensitive_ids: Lowercase IDs before match
        max_fetch: Max payments to fetch
    Returns:
        JSON summary with counts and NA payment IDs
    """
    url = f"{API_BASE}/reconcile/vlookup-payment-to-orders/auto"
    params = {
        "na_status": na_status,
        "case_insensitive_ids": str(case_insensitive_ids).lower(),
        "max_fetch": max_fetch,
    }
    if from_date: params["from_date"] = from_date
    if to_date:   params["to_date"] = to_date

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
