import React, { useState } from "react";
import { DocumentMetadata } from "@/types/knowledge";

interface DocumentPreviewModalProps {
  document: DocumentMetadata | null;
  onClose: () => void;
  onDelete: (doc: DocumentMetadata) => void;
  onRetryUrl?: (url: string) => void;
}

export function DocumentPreviewModal({
  document,
  onClose,
  onDelete,
  onRetryUrl,
}: DocumentPreviewModalProps) {
  const [copiedHash, setCopiedHash] = useState(false);

  if (!document) return null;

  function copyHash() {
    if (!document) return;
    navigator.clipboard.writeText(document.content_hash);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 2000);
  }

  const isVerified = document.verification_status === "verified";
  const isCandidate = document.verification_status === "candidate";
  const isFailed = document.verification_status === "failed";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="preview-modal-title"
    >
      <div
        className="w-full max-w-2xl rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl transition"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-100 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <span
                className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider ${
                  isVerified
                    ? "bg-emerald-100 text-emerald-800 border border-emerald-300"
                    : isCandidate
                    ? "bg-amber-100 text-amber-800 border border-amber-300"
                    : isFailed
                    ? "bg-rose-100 text-rose-800 border border-rose-300"
                    : "bg-slate-100 text-slate-700"
                }`}
              >
                {isVerified ? "✓ Verified Official Source" : isCandidate ? "⏳ Candidate (Unverified)" : "⚠️ Ingestion Failed"}
              </span>
              <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium uppercase text-slate-600">
                {document.source_type}
              </span>
            </div>
            <h2 id="preview-modal-title" className="mt-2 text-xl font-bold text-slate-900">
              {document.source_title || document.document_name}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            aria-label="Close dialog"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content Body */}
        <div className="mt-4 max-h-[60vh] space-y-4 overflow-y-auto pr-1 text-sm text-slate-700">
          {/* Failure Alert Banner */}
          {document.error_message && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-3.5 text-rose-800">
              <p className="font-semibold flex items-center gap-2">
                <svg className="h-4 w-4 text-rose-600 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Ingestion Error Details
              </p>
              <p className="mt-1 text-xs leading-5 font-mono">{document.error_message}</p>
            </div>
          )}

          {/* OCR Warning */}
          {document.requires_ocr && (
            <div className="rounded-xl border border-orange-200 bg-orange-50 p-3.5 text-orange-900">
              <p className="font-semibold flex items-center gap-2">
                <svg className="h-4 w-4 text-orange-600 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
                Scanned Document (OCR Required)
              </p>
              <p className="mt-1 text-xs leading-5">
                This PDF consists of scanned raster images or has no extractable text. Chunks could not be generated. To index this document, convert it with OCR or upload a text-accessible version.
              </p>
            </div>
          )}

          {/* Metadata Grid */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Document ID</span>
              <p className="mt-0.5 font-mono text-xs text-slate-800 break-all">{document.doc_id}</p>
            </div>

            <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Indexed Chunks</span>
              <p className="mt-0.5 text-base font-bold text-indigo-700">
                {document.chunk_count} {document.chunk_count === 1 ? "vector chunk" : "vector chunks"}
              </p>
            </div>

            <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Academic Year</span>
              <p className="mt-0.5 text-sm font-medium text-slate-800">{document.academic_year || "Not specified"}</p>
            </div>

            <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Publication Date</span>
              <p className="mt-0.5 text-sm font-medium text-slate-800">{document.publication_date || "Not specified"}</p>
            </div>

            <div className="rounded-xl border border-slate-100 bg-slate-50 p-3 sm:col-span-2">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Source URL</span>
              {document.source_url ? (
                <div className="mt-1 flex items-center justify-between gap-2">
                  <a
                    href={document.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="truncate text-xs font-medium text-blue-600 hover:underline flex items-center gap-1"
                  >
                    {document.source_url}
                    <svg className="h-3 w-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </a>
                  {onRetryUrl && (
                    <button
                      type="button"
                      onClick={() => {
                        onClose();
                        if (document.source_url) onRetryUrl(document.source_url);
                      }}
                      className="shrink-0 rounded-lg border border-blue-200 bg-blue-50 px-2 py-1 text-xs font-semibold text-blue-700 hover:bg-blue-100"
                    >
                      Retry Ingestion
                    </button>
                  )}
                </div>
              ) : (
                <p className="mt-0.5 text-xs text-slate-500">Local upload ({document.document_name})</p>
              )}
            </div>

            <div className="rounded-xl border border-slate-100 bg-slate-50 p-3 sm:col-span-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Content SHA-256 Hash</span>
                {document.content_hash && (
                  <button
                    onClick={copyHash}
                    className="text-xs font-medium text-blue-600 hover:underline"
                  >
                    {copiedHash ? "Copied!" : "Copy"}
                  </button>
                )}
              </div>
              <p className="mt-0.5 font-mono text-xs text-slate-600 break-all">
                {document.content_hash || "No hash available (empty or failed content)"}
              </p>
            </div>

            <div className="rounded-xl border border-slate-100 bg-slate-50 p-3 sm:col-span-2">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Last Indexed Timestamp</span>
              <p className="mt-0.5 text-xs text-slate-700 font-medium">
                {new Date(document.fetched_at).toLocaleString(undefined, {
                  dateStyle: "full",
                  timeStyle: "medium",
                })}
              </p>
            </div>
          </div>

          {/* Workflow & Verification Info */}
          <div className="rounded-xl border border-blue-100 bg-blue-50/60 p-3.5 text-xs text-blue-900 leading-relaxed">
            <span className="font-semibold block mb-1">ℹ️ Verification Workflow Note:</span>
            {isVerified ? (
              <p>
                This document is marked as <strong>Verified</strong>. Its facts are actively prioritized by the CampusGuide AI RAG pipeline for answering ASTU student questions.
              </p>
            ) : isCandidate ? (
              <p>
                This document is a <strong>Candidate</strong> under review. Candidate documents are stored in the catalog but are treated as unverified evidence until promoted. To promote a candidate to Verified status, re-ingest the URL or re-upload the document with &quot;Verified&quot; status selected.
              </p>
            ) : (
              <p>
                This document encountered an error during indexing. You can retry ingestion using the &quot;Retry Ingestion&quot; button above, or remove it from the catalog.
              </p>
            )}
          </div>
        </div>

        {/* Footer Actions */}
        <div className="mt-6 flex items-center justify-between border-t border-slate-100 pt-4">
          <button
            type="button"
            onClick={() => {
              onClose();
              onDelete(document);
            }}
            className="inline-flex items-center gap-1.5 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-100 transition"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
            Delete Document
          </button>

          <button
            type="button"
            onClick={onClose}
            className="rounded-xl bg-slate-900 px-5 py-2 text-xs font-semibold text-white hover:bg-slate-800 transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
