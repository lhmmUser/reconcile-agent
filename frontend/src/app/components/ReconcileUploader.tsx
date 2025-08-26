// src/app/(dashboard)/components/ReconcileUploader.tsx
"use client";

import { useMemo, useState } from "react";

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

type ApiResponse = {
  summary: {
    total_orders_docs: number;
    orders_with_transaction_id: number;
    total_payments_rows: number;
    filter_status: string;
    case_insensitive_ids: boolean;
    na_count: number;
    matched_count: number;
    max_fetch: number;
    date_window: { from_date: string; to_date: string };
  };
  na_payment_ids: string[];
};

export default function ReconcileUploader() {
  const [result, setResult] = useState<ApiResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // controls
  const [status, setStatus] = useState<string>("captured");  // leave empty string for "all"
  const [caseInsensitive, setCaseInsensitive] = useState(false);
  const [maxFetch, setMaxFetch] = useState<number>(50000);
  const [fromDate, setFromDate] = useState<string>("");      // empty => all-time
  const [toDate, setToDate] = useState<string>("");          // empty => all-time

  async function runReconcile() {
    setErr(null);
    setResult(null);
    setLoading(true);

    const qs = new URLSearchParams();
    if (status) qs.set("status", status);
    if (caseInsensitive) qs.set("case_insensitive_ids", "true");
    if (maxFetch) qs.set("max_fetch", String(maxFetch));
    if (fromDate) qs.set("from_date", fromDate);
    if (toDate) qs.set("to_date", toDate);

    const url = `${API_BASE}/reconcile/vlookup-payment-to-orders/auto${qs.toString() ? `?${qs}` : ""}`;
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 180_000);

    try {
      const res = await fetch(url, { method: "GET", signal: ctrl.signal });
      const json = (await res.json().catch(() => null)) as ApiResponse | null;
      if (!res.ok || !json) {
        setErr((json as any)?.detail || (json as any)?.error || `Server error (${res.status})`);
        return;
        }
      setResult(json);
    } catch (e: any) {
      setErr(e?.name === "AbortError" ? "Request timed out." : e?.message || "Network error");
    } finally {
      clearTimeout(timer);
      setLoading(false);
    }
  }

  const naPreview = useMemo(() => {
    if (!result?.na_payment_ids?.length) return [];
    return result.na_payment_ids.slice(0, 25);
  }, [result]);

  const downloadNAasCSV = () => {
    if (!result?.na_payment_ids?.length) return;
    const csv = ["payment_id", ...result.na_payment_ids].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "na_payment_ids.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-5 p-5 border rounded-lg bg-white">
      <div className="grid md:grid-cols-4 gap-4 items-end">
        <div>
          <label className="block text-sm font-medium mb-1">Payment status</label>
          <input
            className="border rounded px-2 py-1 w-full"
            placeholder='e.g. "captured" (leave blank for all)'
            value={status}
            onChange={(e) => setStatus(e.target.value.trim())}
          />
          <p className="text-xs text-gray-500 mt-1">Common: captured | failed | refunded</p>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Max fetch</label>
          <input
            type="number"
            className="border rounded px-2 py-1 w-full"
            min={1}
            max={100000}
            value={maxFetch}
            onChange={(e) => setMaxFetch(Number(e.target.value) || 0)}
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">From date (optional)</label>
          <input
            type="date"
            className="border rounded px-2 py-1 w-full"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">To date (optional)</label>
          <input
            type="date"
            className="border rounded px-2 py-1 w-full"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
          />
        </div>
      </div>

      <div className="flex items-center gap-6">
        <label className="inline-flex items-center gap-2">
          <input
            type="checkbox"
            checked={caseInsensitive}
            onChange={(e) => setCaseInsensitive(e.target.checked)}
          />
          <span className="text-sm">Case-insensitive ID match</span>
        </label>

        <button
          onClick={runReconcile}
          className="px-4 py-2 rounded bg-black text-white disabled:opacity-50"
          disabled={loading}
        >
          {loading ? "Reconciling…" : "Run Reconcile"}
        </button>

        {!!result?.na_payment_ids?.length && (
          <button
            onClick={downloadNAasCSV}
            className="px-3 py-2 rounded border text-sm"
          >
            Download NA IDs (CSV)
          </button>
        )}
      </div>

      {err && <p className="text-red-600">{err}</p>}

      {result && (
        <div className="mt-4 space-y-3">
          <div className="text-sm">
            <div>Orders (total docs scanned): <strong>{result.summary.total_orders_docs}</strong></div>
            <div>Orders with <code>transaction_id</code>: <strong>{result.summary.orders_with_transaction_id}</strong></div>
            <div>Payments fetched: <strong>{result.summary.total_payments_rows}</strong></div>
            <div>Filter status: <strong>{result.summary.filter_status}</strong></div>
            <div>Case-insensitive: <strong>{String(result.summary.case_insensitive_ids)}</strong></div>
            <div>Matched count: <strong className="text-green-700">{result.summary.matched_count}</strong></div>
            <div>#N/A count: <strong className="text-red-700">{result.summary.na_count}</strong></div>
            <div>Date window: <strong>{result.summary.date_window.from_date}</strong> → <strong>{result.summary.date_window.to_date}</strong></div>
            <div>max_fetch: <strong>{result.summary.max_fetch}</strong></div>
          </div>

          <div className="mt-2">
            <h2 className="font-medium mb-1 text-sm">First 25 NA Payment IDs</h2>
            {result.na_payment_ids.length === 0 ? (
              <p className="text-sm text-gray-600">No NA payment IDs 🎉</p>
            ) : (
              <ul className="text-xs max-h-64 overflow-auto list-disc pl-5">
                {naPreview.map((id) => (
                  <li key={id} className="break-all">{id}</li>
                ))}
              </ul>
            )}
          </div>

          <details className="mt-3">
            <summary className="cursor-pointer text-sm text-gray-700">Show raw JSON</summary>
            <pre className="bg-gray-100 p-3 rounded text-xs overflow-auto mt-2">
{JSON.stringify(result, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </div>
  );
}
