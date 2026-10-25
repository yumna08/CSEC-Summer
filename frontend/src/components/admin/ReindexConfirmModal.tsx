import React, { useState } from "react";
import { knowledgeApi } from "@/services/api";
import { ReindexResponse } from "@/types/knowledge";

interface ReindexConfirmModalProps {
  isOpen: boolean;
  adminKey?: string;
  onClose: () => void;
  onSuccess: (response: ReindexResponse) => void;
}

export function ReindexConfirmModal({
  isOpen,
  adminKey,
  onClose,
  onSuccess,
}: ReindexConfirmModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reindexResult, setReindexResult] = useState<ReindexResponse | null>(null);

  if (!isOpen) return null;

  async function handleReindex() {
    setLoading(true);
    setError(null);
    setReindexResult(null);

    try {
      const response = await knowledgeApi.reindexSources({ adminKey });
      setReindexResult(response);
      onSuccess(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reindexing failed.");
    } finally {
      setLoading(false);
    }
  }

  function handleReset() {
    setError(null);
    setReindexResult(null);
    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs"
      onClick={loading ? undefined : handleReset}
      role="dialog"
      aria-modal="true"
      aria-labelledby="reindex-modal-title"
    >
      <div
        className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl transition"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-100 text-blue-700">
          <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </div>

        <h3 id="reindex-modal-title" className="mt-4 text-lg font-bold text-slate-900">
          Reindex All Registered Sources?
        </h3>

        <p className="mt-2 text-sm text-slate-600 leading-relaxed">
          This will fetch all sources in the registry, check content hashes for changes, and update out-of-date vector chunks in ChromaDB. Unchanged documents are automatically skipped for idempotency.
        </p>

        {error && (
          <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800" role="alert">
            <p className="font-semibold">Reindexing Error</p>
            <p className="mt-0.5">{error}</p>
          </div>
        )}

        {reindexResult && (
          <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3.5 text-xs text-emerald-950">
            <p className="font-semibold flex items-center gap-1.5">
              <svg className="h-4 w-4 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
              </svg>
              Reindexing Finished
            </p>
            <p className="mt-1">
              Successfully processed {reindexResult.total_reindexed} sources.
            </p>
          </div>
        )}

        <div className="mt-6 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={handleReset}
            disabled={loading}
            className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {reindexResult ? "Close" : "Cancel"}
          </button>
          {!reindexResult && (
            <button
              type="button"
              onClick={handleReindex}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-xl bg-blue-700 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50 transition"
            >
              {loading ? (
                <>
                  <svg className="h-4 w-4 animate-spin text-white" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Reindexing...
                </>
              ) : (
                "Start Reindexing"
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
