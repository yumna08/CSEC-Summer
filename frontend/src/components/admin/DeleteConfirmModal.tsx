import React from "react";
import { DocumentMetadata } from "@/types/knowledge";

interface DeleteConfirmModalProps {
  document: DocumentMetadata | null;
  loading: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function DeleteConfirmModal({
  document,
  loading,
  onConfirm,
  onCancel,
}: DeleteConfirmModalProps) {
  if (!document) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs"
      onClick={loading ? undefined : onCancel}
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-modal-title"
    >
      <div
        className="w-full max-w-md rounded-2xl border border-rose-200 bg-white p-6 shadow-2xl transition"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-rose-100 text-rose-600">
          <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
            />
          </svg>
        </div>

        <h3 id="delete-modal-title" className="mt-4 text-lg font-bold text-slate-900">
          Delete Knowledge Source?
        </h3>

        <p className="mt-2 text-sm text-slate-600 leading-relaxed">
          Are you sure you want to delete{" "}
          <strong className="text-slate-900 font-semibold">
            &ldquo;{document.source_title || document.document_name}&rdquo;
          </strong>
          ?
        </p>

        <div className="mt-3 rounded-xl border border-slate-100 bg-slate-50 p-3 text-xs text-slate-600 space-y-1">
          <div className="flex justify-between">
            <span className="text-slate-500">Document ID:</span>
            <span className="font-mono text-slate-800">{document.doc_id}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Vector Chunks to purge:</span>
            <span className="font-bold text-rose-600">{document.chunk_count}</span>
          </div>
        </div>

        <p className="mt-3 text-xs text-rose-700">
          ⚠️ This action is permanent and cannot be undone. All indexed vector embeddings will be purged from ChromaDB immediately.
        </p>

        <div className="mt-6 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-xl bg-rose-600 px-4 py-2 text-xs font-semibold text-white hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? (
              <>
                <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
                Deleting...
              </>
            ) : (
              "Yes, Delete Source"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
