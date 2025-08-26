"use client";
import { useState } from "react";

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export default function RazorpaySimpleDownloader() {
  const [status, setStatus] = useState("captured");
  const [fromDate, setFromDate] = useState(""); // "2025-08-01"
  const [toDate, setToDate] = useState("");     // "2025-08-31"
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function handleDownload() {
    setErr(null);
    setLoading(true);
    try {
      const url = new URL(`${API_BASE}/razorpay/payments-csv`);
      if (status) url.searchParams.set("status", status);
      if (fromDate) url.searchParams.set("from_date", fromDate);
      if (toDate) url.searchParams.set("to_date", toDate);

      const res = await fetch(url.toString(), { method: "GET" });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Export failed (${res.status}): ${text}`);
      }

      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "razorpay_payments.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(a.href);
    } catch (e: any) {
      setErr(e?.message || "Network error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-3 p-4 border rounded">
      <div className="flex gap-3 items-end flex-wrap">
        <div>
          <label className="block text-sm font-medium">Status</label>
          <select value={status} onChange={e => setStatus(e.target.value)} className="border rounded px-2 py-1">
            <option value="">(all)</option>
            <option value="captured">captured</option>
            <option value="authorized">authorized</option>
            <option value="failed">failed</option>
            <option value="refunded">refunded</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium">From date (YYYY-MM-DD)</label>
          <input value={fromDate} onChange={e=>setFromDate(e.target.value)} placeholder="2025-08-01"
                 className="border rounded px-2 py-1" />
        </div>
        <div>
          <label className="block text-sm font-medium">To date (YYYY-MM-DD)</label>
          <input value={toDate} onChange={e=>setToDate(e.target.value)} placeholder="2025-08-31"
                 className="border rounded px-2 py-1" />
        </div>
        <button
          type="button"
          onClick={handleDownload}
          className="px-4 py-2 rounded bg-black text-white disabled:opacity-50"
          disabled={loading}
        >
          {loading ? "Downloading..." : "Download CSV"}
        </button>
      </div>
      {err && <p className="text-red-600 text-sm">{err}</p>}
      <p className="text-xs text-gray-600">
        Hits <code>GET /razorpay/payments-csv</code> on your backend and streams a CSV with
        columns for UPI (<code>vpa</code>, <code>flow</code>) and acquirer data (<code>Payments_RRN</code>, <code>ARN</code>, <code>Auth_code</code>).
      </p>
    </div>
  );
}
