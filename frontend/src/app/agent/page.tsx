// src/app/(dashboard)/agent/page.tsx
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { runAgent, AgentResult } from "@/lib/api";

type ChatMsg = { role: "user" | "assistant" | "system"; content: string; raw?: any };

function extractSummaryFromAgent(out: any) {
  // Our backend returns { result: <langgraph_output> }.
  // We try to find a JSON blob with "summary" or known fields.
  // If your prompt/tool returns the full backend JSON, you can display summary directly.
  if (!out) return null;

  // Common shapes:
  // 1) out.result = { summary: {...}, ... }
  if (out?.result?.summary) return out.result.summary;

  // 2) Sometimes prebuilt agent returns { messages: [...] }, tool output is in last message
  const msgs = out?.result?.messages || out?.messages;
  if (Array.isArray(msgs) && msgs.length) {
    const last = msgs[msgs.length - 1];
    // If tool output was returned as JSON in content:
    try {
      if (typeof last?.content === "string") {
        const maybe = JSON.parse(last.content);
        if (maybe?.summary) return maybe.summary;
      } else if (Array.isArray(last?.content)) {
        // content may be a list of parts (OpenAI style)
        for (const part of last.content) {
          if (typeof part?.text === "string") {
            const maybe = JSON.parse(part.text);
            if (maybe?.summary) return maybe.summary;
          }
        }
      }
    } catch {}
  }

  return null;
}

function Bubble({ msg }: { msg: ChatMsg }) {
  const mine = msg.role === "user";
  return (
    <div className={`flex ${mine ? "justify-end" : "justify-start"} my-1`}>
      <div
        className={`max-w-[80%] px-3 py-2 rounded-lg text-sm whitespace-pre-wrap break-words
          ${mine ? "bg-black text-white rounded-tr-none" : "bg-gray-100 text-gray-900 rounded-tl-none"}`}
      >
        {msg.content}
      </div>
    </div>
  );
}

function SummaryBlock({ summary }: { summary: any }) {
  // Show key numbers if present
  const items: { label: string; value: any }[] = [];
  const push = (label: string, key: string) => {
    if (summary && summary[key] !== undefined) items.push({ label, value: summary[key] });
  };
  push("Orders (scanned)", "total_orders_docs_scanned");
  push("Orders with TX", "orders_with_transaction_id");
  push("Payments fetched", "total_payments_rows");
  push("Matched (distinct)", "matched_distinct_payment_ids");
  push("NA count", "na_count");
  push("NA status filter", "na_status_filter");
  const fromD = summary?.date_window?.from_date;
  const toD   = summary?.date_window?.to_date;

  return (
    <div className="mt-2 border rounded-lg p-3 bg-white">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {items.map((it) => (
          <div key={it.label} className="rounded border p-2 text-sm">
            <div className="text-gray-500">{it.label}</div>
            <div className="font-semibold">{String(it.value)}</div>
          </div>
        ))}
        {(fromD || toD) && (
          <div className="rounded border p-2 text-sm col-span-2 md:col-span-3">
            <div className="text-gray-500">Date window</div>
            <div className="font-semibold">
              {fromD ?? "(all-time)"} → {toD ?? "(all-time)"}
            </div>
          </div>
        )}
      </div>
      <details className="mt-3">
        <summary className="cursor-pointer text-sm text-gray-700">Show raw summary JSON</summary>
        <pre className="bg-gray-100 p-3 rounded text-xs overflow-auto mt-2">
{JSON.stringify(summary, null, 2)}
        </pre>
      </details>
    </div>
  );
}

export default function AgentChatPage() {
  const [msgs, setMsgs] = useState<ChatMsg[]>([
    { role: "system", content: "Ask me to reconcile Razorpay vs Orders (e.g., 'reconcile 2025-08-15 to 2025-08-25 captured only')." }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [lastAgentRaw, setLastAgentRaw] = useState<any>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [msgs, loading]);

  const lastSummary = useMemo(() => extractSummaryFromAgent(lastAgentRaw), [lastAgentRaw]);

  async function send() {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMsgs((m) => [...m, { role: "user", content: text }]);
    setLoading(true);

    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 120_000);

    try {
      const res: AgentResult = await runAgent(text, ctrl.signal);
      setLastAgentRaw(res);
      // For the visible assistant bubble, we keep it concise:
      const summary = extractSummaryFromAgent(res);
      const assistantText =
        summary
          ? `NA: ${summary.na_count} | Matched: ${summary.matched_distinct_payment_ids} | Payments: ${summary.total_payments_rows}`
          : `Done. (No parsable summary found)\n${JSON.stringify(res).slice(0, 800)}${JSON.stringify(res).length > 800 ? "…" : ""}`;
      setMsgs((m) => [...m, { role: "assistant", content: assistantText, raw: res }]);
    } catch (e: any) {
      setMsgs((m) => [...m, { role: "assistant", content: `Error: ${e?.message || e}` }]);
    } finally {
      clearTimeout(timer);
      setLoading(false);
    }
  }

  function onKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="max-w-4xl mx-auto p-4 space-y-4">
      <h1 className="text-xl font-semibold">Reconcile Agent</h1>

      <div ref={listRef} className="border rounded-lg p-3 h-[56vh] overflow-auto bg-white">
        {msgs.map((m, i) => <Bubble key={i} msg={m} />)}
        {loading && <div className="text-sm text-gray-500 mt-2">Agent is thinking…</div>}
      </div>

      {lastSummary && <SummaryBlock summary={lastSummary} />}

      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          placeholder="e.g., reconcile 2025-08-15 to 2025-08-25 captured only"
          className="flex-1 border rounded px-3 py-2"
        />
        <button
          onClick={send}
          disabled={loading || input.trim().length === 0}
          className="px-4 py-2 rounded bg-black text-white disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </div>
  );
}
