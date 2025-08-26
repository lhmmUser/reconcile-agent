# app/routers/reconcile.py
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any, List
import os
import httpx

from pymongo import MongoClient
from pymongo.errors import PyMongoError

router = APIRouter(prefix="/reconcile", tags=["reconcile"])

def norm(s: str | None, *, case_insensitive: bool) -> str:
    t = (s or "").replace("\u00A0", " ").strip()
    return t.lower() if case_insensitive else t

# ---- Razorpay fetcher (reuse your existing code) ----------------------------
from app.routers.razorpay_export import fetch_payments, _assert_keys
# ----------------------------------------------------------------------------

# ---- Mongo connection via ENV ----------------------------------------------
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    # Fail fast with a clear message instead of silently defaulting to localhost.
    raise RuntimeError("MONGO_URI not set")

client = MongoClient(MONGO_URI, tz_aware=True)
db = client["candyman"]
orders_collection = db["user_details"]


# ------------------------------ KEEP: /orders --------------------------------
@router.get("/orders")
def get_orders(
    sort_by: Optional[str] = Query(None, description="Field to sort by"),
    sort_dir: Optional[str] = Query("asc", description="asc or desc"),
    filter_status: Optional[str] = Query(None),
    filter_book_style: Optional[str] = Query(None),
    filter_print_approval: Optional[str] = Query(None),
    filter_discount_code: Optional[str] = Query(None),
    exclude_discount_code: Optional[str] = None,
):
    # Base query: only show paid orders
    query = {"paid": True}

    # Add additional filters
    if filter_status == "approved":
        query["approved"] = True
    elif filter_status == "uploaded":
        query["approved"] = False

    if filter_book_style:
        query["book_style"] = filter_book_style

    if filter_print_approval == "yes":
        query["print_approval"] = True
    elif filter_print_approval == "no":
        query["print_approval"] = False
    elif filter_print_approval == "not_found":
        query["print_approval"] = {"$exists": False}

    if filter_discount_code:
        if filter_discount_code.lower() == "none":
            query["discount_amount"] = 0
            query["paid"] = True
        else:
            query["discount_code"] = filter_discount_code.upper()

    if exclude_discount_code:
        if "discount_code" in query and isinstance(query["discount_code"], str):
            query["$and"] = [
                {"discount_code": query["discount_code"]},
                {"discount_code": {"$ne": exclude_discount_code.upper()}},
            ]
            del query["discount_code"]
        elif "discount_code" not in query:
            query["discount_code"] = {"$ne": exclude_discount_code.upper()}

    # Fetch and sort records
    sort_field = sort_by if sort_by else "created_at"
    sort_order = 1 if sort_dir == "asc" else -1

    projection = {
        "order_id": 1, "job_id": 1, "cover_url": 1, "book_url": 1, "preview_url": 1,
        "name": 1, "shipping_address": 1, "created_at": 1, "processed_at": 1,
        "approved_at": 1, "approved": 1, "book_id": 1, "book_style": 1,
        "print_status": 1, "price": 1, "total_price": 1, "amount": 1, "total_amount": 1,
        "feedback_email": 1, "print_approval": 1, "discount_code": 1,
        "currency": 1, "locale": 1, "_id": 0,
    }

    records = list(orders_collection.find(query, projection).sort(sort_field, sort_order))
    result = []
    for doc in records:
        result.append({
            "order_id": doc.get("order_id", ""),
            "job_id": doc.get("job_id", ""),
            "coverPdf": doc.get("cover_url", ""),
            "interiorPdf": doc.get("book_url", ""),
            "previewUrl": doc.get("preview_url", ""),
            "name": doc.get("name", ""),
            "city": doc.get("shipping_address", {}).get("city", ""),
            "price": doc.get("price", doc.get("total_price", doc.get("amount", doc.get("total_amount", 0)))),
            "paymentDate": doc.get("processed_at", ""),
            "approvalDate": doc.get("approved_at", ""),
            "status": "Approved" if doc.get("approved") else "Uploaded",
            "bookId": doc.get("book_id", ""),
            "bookStyle": doc.get("book_style", ""),
            "printStatus": doc.get("print_status", ""),
            "feedback_email": doc.get("feedback_email", False),
            "print_approval": doc.get("print_approval", None),
            "discount_code": doc.get("discount_code", ""),
            "currency": doc.get("currency", ""),
            "locale": doc.get("locale", ""),
        })
    return result
# ----------------------------------------------------------------------------


@router.get("/vlookup-payment-to-orders/auto")
async def vlookup_payment_to_orders_auto(
    # Payments: ALL STATUSES by default (None)
    status: Optional[str] = Query(None, description="Filter payments fetched from Razorpay by status; omit for ALL"),
    max_fetch: int = Query(200_000, ge=1, le=1_000_000, description="Upper bound for Razorpay pulls"),
    from_date: Optional[str] = Query(None, description="YYYY-MM-DD / ISO; omit for ALL time"),
    to_date:   Optional[str] = Query(None, description="YYYY-MM-DD / ISO; omit for ALL time"),
    case_insensitive_ids: bool = Query(False, description="Lowercase both sides before matching"),

    # Orders paging (scan *all* orders)
    orders_batch_size: int = Query(50_000, ge=1_000, le=200_000, description="Mongo batch size"),

    # IMPORTANT: default to only NA with status=captured
    na_status: Optional[str] = Query("captured", description="Only include NA payments with this Razorpay status"),
):
    _assert_keys()

    def _to_unix(s: Optional[str]) -> Optional[int]:
        if not s:
            return None
        from dateutil import parser as dtparser
        return int(dtparser.parse(s).timestamp())

    # 1) Razorpay: fetch ALL (status=None => all statuses)
    try:
        async with httpx.AsyncClient(
            auth=(os.getenv("RAZORPAY_KEY_ID"), os.getenv("RAZORPAY_KEY_SECRET")),
            timeout=60.0
        ) as client:
            payments: List[Dict[str, Any]] = await fetch_payments(
                client=client,
                status_filter=status,   # None => all
                from_unix=_to_unix(from_date),
                to_unix=_to_unix(to_date),
                max_fetch=max_fetch,
            )
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Network error calling Razorpay: {e}")

    # Index: normalized id -> (raw id, status)
    pay_index: Dict[str, Dict[str, str]] = {}
    for p in payments:
        raw_id = str(p.get("id", "") or "")
        if not raw_id:
            continue
        key = norm(raw_id, case_insensitive=case_insensitive_ids)
        st = (p.get("status") or "").strip().lower()
        pay_index[key] = {"id": raw_id, "status": st}

    payment_keys = set(pay_index.keys())
    matched_keys: set[str] = set()

    # 2) Scan ALL orders by _id (Atlas-safe)
    total_orders_docs = 0
    orders_with_tx = 0
    last_id = None

    try:
        while True:
            q: Dict[str, Any] = {}
            if last_id is not None:
                q["_id"] = {"$gt": last_id}

            batch = list(
                orders_collection.find(q, projection={"transaction_id": 1, "order_id": 1})
                                 .sort([("_id", 1)])
                                 .limit(orders_batch_size)
            )
            if not batch:
                break

            total_orders_docs += len(batch)

            for doc in batch:
                raw_tx = doc.get("transaction_id")
                if not raw_tx:
                    continue
                tx_key = norm(str(raw_tx), case_insensitive=case_insensitive_ids)
                if not tx_key:
                    continue
                orders_with_tx += 1
                if tx_key in payment_keys:
                    matched_keys.add(tx_key)

            last_id = batch[-1]["_id"]
    except PyMongoError as e:
        raise HTTPException(status_code=502, detail=f"Mongo query failed: {e}")

    # 3) NA keys (in payments but not matched to any order)
    na_keys = payment_keys - matched_keys

    # Build NA items and FILTER by status (default captured)
    target_status = (na_status or "captured").strip().lower()
    na_items: List[Dict[str, str]] = []
    for k in na_keys:
        rec = pay_index.get(k)
        if not rec:
            continue
        if (rec.get("status") or "") == target_status:
            na_items.append({"id": rec["id"], "status": target_status})

    # Sort by id (status is uniform now)
    na_items.sort(key=lambda x: x["id"])

    # Group (will only contain the target status)
    na_by_status: Dict[str, List[str]] = {}
    for item in na_items:
        na_by_status.setdefault(item["status"], []).append(item["id"])

    matched_distinct = len(matched_keys)

    return JSONResponse({
        "summary": {
            "total_orders_docs_scanned": total_orders_docs,
            "orders_with_transaction_id": orders_with_tx,
            "total_payments_rows": len(payments),
            "payment_status_filter": status or "(ALL)",
            "case_insensitive_ids": case_insensitive_ids,
            "matched_distinct_payment_ids": matched_distinct,
            # IMPORTANT: now counts ONLY the chosen status (default captured)
            "na_count": len(na_items),
            "max_fetch": max_fetch,
            "date_window": {
                "from_date": from_date or "(all-time)",
                "to_date": to_date or "(all-time)",
            },
            "orders_batch_size": orders_batch_size,
            "na_status_filter": target_status,
        },
        # Only the chosen status (default captured)
        "na_payment_ids": [x["id"] for x in na_items],
        "na_by_status": na_by_status,  # contains only the chosen status
    })
