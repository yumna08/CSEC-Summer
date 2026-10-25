import React, { useState } from "react";
import { knowledgeApi } from "@/services/api";
import { IngestResult } from "@/types/knowledge";

interface IngestUrlModalProps {
  isOpen: boolean;
  initialUrl?: string;
  adminKey?: string;
  onClose: () => void;
  onSuccess: (result: IngestResult) => void;
}

export function IngestUrlModal({
  isOpen,
  initialUrl = "",
  adminKey,
  onClose,
  onSuccess,
}: IngestUrlModalProps) {
  const [url, setUrl] = useState(initialUrl);
  const [sourceTitle, setSourceTitle] = useState("");
  const [verificationStatus, setVerificationStatus] = useState<string>("candidate");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<IngestResult | null>(null);

  if (!isOpen) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const cleanUrl = url.trim();
    if (!cleanUrl || loading) return;

    setError(null);
    setLastResult(null);
    setLoading(true);

    try {
      const result = await knowledgeApi.ingestUrl(
        {
          url: cleanUrl,
          source_title: sourceTitle.trim() || undefined,
          verification_status: verificationStatus,
        },
        { adminKey }
      );

      setLastResult(result);
      if (result.status === "failed") {
        setError(result.message || "Ingestion failed on backend.");
      } else {
        onSuccess(result);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to ingest URL.");
    } finally {
      setLoading(false);
    }
  }

  function handleReset() {
    setUrl("");
    setSourceTitle("");
    setVerificationStatus("candidate");
    setError(null);
    setLastResult(null);
    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs"
      onClick={loading ? undefined : handleReset}
      role="dialog"
      aria-modal="true"
      aria-labelledby="ingest-url-title"
    >
      <div
        className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl transition"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-100 pb-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-100 text-blue-700">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
              </svg>
            </div>
            <div>
              <h3 id="ingest-url-title" className="text-lg font-bold text-slate-900">
                Ingest Approved ASTU Webpage
              </h3>
              <p className="text-xs text-slate-500">Fetch HTML, clean navigation/footers, and generate vector chunks</p>
            </div>
          </div>
          <button
            onClick={handleReset}
            disabled={loading}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-50"
            aria-label="Close dialog"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {error && (
          <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800" role="alert">
            <p className="font-semibold flex items-center gap-1.5">
              <svg className="h-4 w-4 shrink-0 text-rose-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Ingestion Failed
            </p>
            <p className="mt-1">{error}</p>
          </div>
        )}

        {lastResult && lastResult.status !== "failed" && (
          <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3.5 text-xs text-emerald-900">
            <p className="font-semibold flex items-center gap-1.5">
              <svg className="h-4 w-4 shrink-0 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
              </svg>
              Ingestion Completed Successfully
            </p>
            <p className="mt-1 text-slate-700">{lastResult.message}</p>
            <div className="mt-2 flex items-center gap-2 font-mono text-[11px] text-slate-600">
              <span className="rounded bg-white px-2 py-0.5 border border-emerald-200">
                Status: {lastResult.status}
              </span>
              <span className="rounded bg-white px-2 py-0.5 border border-emerald-200 font-bold text-indigo-700">
                {lastResult.chunk_count} Chunks Indexed
              </span>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <div>
            <label htmlFor="ingest-url-input" className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
              Webpage URL <span className="text-rose-500">*</span>
            </label>
            <input
              id="ingest-url-input"
              type="url"
              required
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://www.astu.edu.et/page-path"
              className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            />
            <p className="mt-1 text-[11px] text-slate-500 flex items-center gap-1">
              <span>Security rule: Must be on approved ASTU domains:</span>
              <code className="rounded bg-slate-100 px-1 py-0.5 text-slate-700">astu.edu.et</code>
              <span>or</span>
              <code className="rounded bg-slate-100 px-1 py-0.5 text-slate-700">portal.astu.edu.et</code>
            </p>
          </div>

          <div>
            <label htmlFor="source-title-input" className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
              Custom Source Title <span className="text-slate-400 font-normal lowercase">(optional)</span>
            </label>
            <input
              id="source-title-input"
              type="text"
              value={sourceTitle}
              onChange={(e) => setSourceTitle(e.target.value)}
              placeholder="e.g. ASTU Dormitory Rules 2026/2027"
              className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            />
            <p className="mt-1 text-[11px] text-slate-500">
              If omitted, CampusGuide will automatically extract the HTML &lt;title&gt; or heading.
            </p>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
              Verification Status
            </label>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <label
                className={`flex cursor-pointer flex-col rounded-xl border p-3 text-xs transition ${
                  verificationStatus === "candidate"
                    ? "border-amber-400 bg-amber-50/50 text-amber-900"
                    : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                }`}
              >
                <div className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="verification_status"
                    value="candidate"
                    checked={verificationStatus === "candidate"}
                    onChange={(e) => setVerificationStatus(e.target.value)}
                    className="text-amber-600 focus:ring-amber-500"
                  />
                  <span className="font-semibold">Candidate (Review)</span>
                </div>
                <span className="mt-1 text-[11px] text-slate-500 leading-normal pl-5">
                  Stored as candidate source awaiting manual review before prioritization.
                </span>
              </label>

              <label
                className={`flex cursor-pointer flex-col rounded-xl border p-3 text-xs transition ${
                  verificationStatus === "verified"
                    ? "border-emerald-400 bg-emerald-50/50 text-emerald-900"
                    : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                }`}
              >
                <div className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="verification_status"
                    value="verified"
                    checked={verificationStatus === "verified"}
                    onChange={(e) => setVerificationStatus(e.target.value)}
                    className="text-emerald-600 focus:ring-emerald-500"
                  />
                  <span className="font-semibold">Verified (Official)</span>
                </div>
                <span className="mt-1 text-[11px] text-slate-500 leading-normal pl-5">
                  High-confidence official ASTU facts directly cited by student AI.
                </span>
              </label>
            </div>
          </div>

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
            <button
              type="button"
              onClick={handleReset}
              disabled={loading}
              className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!url.trim() || loading}
              className="inline-flex items-center gap-2 rounded-xl bg-blue-700 px-5 py-2 text-xs font-semibold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50 transition"
            >
              {loading ? (
                <>
                  <svg className="h-4 w-4 animate-spin text-white" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Fetching & Indexing...
                </>
              ) : (
                "Ingest Webpage"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
