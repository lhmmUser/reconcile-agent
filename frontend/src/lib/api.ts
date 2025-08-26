// src/lib/api.ts
const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export type AgentSummary = Record<string, any>;

export type AgentResult = {
  result: any; // LangGraph output (we'll extract summary if present)
};

export async function runAgent(message: string, signal?: AbortSignal): Promise<AgentResult> {
  const res = await fetch(`${API_BASE}/agent/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
    signal,
  });
  if (!res.ok) {
    const j = await res.json().catch(() => null);
    throw new Error(j?.detail || `Agent error (${res.status})`);
  }
  return res.json();
}

// Optional: direct call to your reconcile tool (bypasses LLM).
export async function reconcileDirect(params: {
  from_date?: string;
  to_date?: string;
  na_status?: string;            // default 'captured'
  case_insensitive_ids?: boolean;// default false
  max_fetch?: number;            // default 200000
}, signal?: AbortSignal): Promise<any> {
  const qs = new URLSearchParams();
  if (params.from_date) qs.set("from_date", params.from_date);
  if (params.to_date)   qs.set("to_date", params.to_date);
  qs.set("na_status", (params.na_status ?? "captured"));
  qs.set("case_insensitive_ids", String(!!params.case_insensitive_ids));
  qs.set("max_fetch", String(params.max_fetch ?? 200000));

  const url = `${API_BASE}/reconcile/vlookup-payment-to-orders/auto?${qs.toString()}`;
  const res = await fetch(url, { method: "GET", signal });
  if (!res.ok) {
    const j = await res.json().catch(() => null);
    throw new Error(j?.detail || `Reconcile error (${res.status})`);
  }
  return res.json();
}
