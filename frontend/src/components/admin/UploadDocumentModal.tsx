import React, { useRef, useState } from "react";
import { knowledgeApi } from "@/services/api";
import { IngestResult } from "@/types/knowledge";

interface UploadDocumentModalProps {
  isOpen: boolean;
  adminKey?: string;
  onClose: () => void;
  onSuccess: (result: IngestResult) => void;
}

const ALLOWED_EXTENSIONS = [".pdf", ".docx", ".txt", ".text", ".md"];
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

export function UploadDocumentModal({
  isOpen,
  adminKey,
  onClose,
  onSuccess,
}: UploadDocumentModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [verificationStatus, setVerificationStatus] = useState<string>("verified");
  const [dragActive, setDragActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<IngestResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!isOpen) return null;

  function handleFileSelected(selectedFile: File) {
    setError(null);
    setLastResult(null);

    const ext = "." + selectedFile.name.split(".").pop()?.toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      setError(
        `Unsupported file type '${ext}'. Allowed types: ${ALLOWED_EXTENSIONS.join(", ")}`
      );
      setFile(null);
      return;
    }

    if (selectedFile.size > MAX_FILE_SIZE) {
      setError("File exceeds the maximum allowed size of 10MB.");
      setFile(null);
      return;
    }

    if (selectedFile.size === 0) {
      setError("The selected file is empty.");
      setFile(null);
      return;
    }

    setFile(selectedFile);
  }

  function handleDrag(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || loading) return;

    setLoading(true);
    setError(null);
    setLastResult(null);

    try {
      const result = await knowledgeApi.uploadDocument(
        file,
        verificationStatus,
        { adminKey }
      );

      setLastResult(result);
      if (result.status === "failed") {
        setError(result.message || "Failed to process uploaded file.");
      } else {
        onSuccess(result);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload file.");
    } finally {
      setLoading(false);
    }
  }

  function handleReset() {
    setFile(null);
    setVerificationStatus("verified");
    setError(null);
    setLastResult(null);
    setDragActive(false);
    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs"
      onClick={loading ? undefined : handleReset}
      role="dialog"
      aria-modal="true"
      aria-labelledby="upload-modal-title"
    >
      <div
        className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl transition"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-100 pb-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-100 text-indigo-700">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
            </div>
            <div>
              <h3 id="upload-modal-title" className="text-lg font-bold text-slate-900">
                Upload University Document
              </h3>
              <p className="text-xs text-slate-500">
                Index PDF, DOCX, or TXT documents into the vector store
              </p>
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
              Upload Error
            </p>
            <p className="mt-1">{error}</p>
          </div>
        )}

        {lastResult && (
          <div
            className={`mt-4 rounded-xl border p-3.5 text-xs ${
              lastResult.status === "scanned_requires_ocr"
                ? "border-orange-200 bg-orange-50 text-orange-950"
                : "border-emerald-200 bg-emerald-50 text-emerald-950"
            }`}
          >
            <p className="font-semibold flex items-center gap-1.5">
              {lastResult.status === "scanned_requires_ocr" ? "⚠️ Scanned PDF Detected" : "✓ Ingestion Complete"}
            </p>
            <p className="mt-1">{lastResult.message}</p>
            <div className="mt-2 flex items-center gap-2 font-mono text-[11px]">
              <span className="rounded bg-white px-2 py-0.5 border border-slate-200">
                Chunks: {lastResult.chunk_count}
              </span>
              <span className="rounded bg-white px-2 py-0.5 border border-slate-200">
                Status: {lastResult.status}
              </span>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          {/* Drag & Drop Box */}
          <div
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed p-6 text-center transition ${
              dragActive
                ? "border-indigo-500 bg-indigo-50/60"
                : file
                ? "border-emerald-300 bg-emerald-50/30"
                : "border-slate-200 bg-slate-50/50 hover:bg-slate-100/60 hover:border-slate-300"
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.txt,.text,.md"
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  handleFileSelected(e.target.files[0]);
                }
              }}
              className="hidden"
            />

            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white shadow-xs border border-slate-200 text-indigo-600">
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
            </div>

            {file ? (
              <div className="mt-3">
                <p className="font-semibold text-slate-900 text-sm truncate max-w-xs">{file.name}</p>
                <p className="text-xs text-slate-500 font-mono mt-0.5">
                  {(file.size / (1024 * 1024)).toFixed(2)} MB • {file.name.split(".").pop()?.toUpperCase()}
                </p>
                <span className="mt-2 inline-block rounded-md bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-800">
                  Ready to index
                </span>
              </div>
            ) : (
              <div className="mt-3">
                <p className="text-sm font-semibold text-slate-800">
                  Click to browse or drop your document here
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Supports PDF, DOCX, TXT, and Markdown (Max 10 MB)
                </p>
              </div>
            )}
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
              Verification Status
            </label>
            <div className="mt-2 grid grid-cols-2 gap-2">
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
                    name="upload_verification_status"
                    value="verified"
                    checked={verificationStatus === "verified"}
                    onChange={(e) => setVerificationStatus(e.target.value)}
                    className="text-emerald-600 focus:ring-emerald-500"
                  />
                  <span className="font-semibold">Verified (Official)</span>
                </div>
                <span className="mt-1 text-[11px] text-slate-500 leading-normal pl-5">
                  Direct official evidence cited for ASTU queries.
                </span>
              </label>

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
                    name="upload_verification_status"
                    value="candidate"
                    checked={verificationStatus === "candidate"}
                    onChange={(e) => setVerificationStatus(e.target.value)}
                    className="text-amber-600 focus:ring-amber-500"
                  />
                  <span className="font-semibold">Candidate (Review)</span>
                </div>
                <span className="mt-1 text-[11px] text-slate-500 leading-normal pl-5">
                  Held as unverified candidate until review.
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
              disabled={!file || loading}
              className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2 text-xs font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50 transition"
            >
              {loading ? (
                <>
                  <svg className="h-4 w-4 animate-spin text-white" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Extracting & Indexing...
                </>
              ) : (
                "Upload & Index"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
