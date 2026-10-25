import React, { useState } from "react";
import { knowledgeApi } from "@/services/api";
import { IngestWebsitesResponse, SourceRegistryItem } from "@/types/knowledge";

interface CrawlWebsitesModalProps {
  isOpen: boolean;
  sources: SourceRegistryItem[];
  adminKey?: string;
  onClose: () => void;
  onSuccess: (response: IngestWebsitesResponse) => void;
}

export function CrawlWebsitesModal({
  isOpen,
  sources,
  adminKey,
  onClose,
  onSuccess,
}: CrawlWebsitesModalProps) {
  const [maxPages, setMaxPages] = useState<number>(15);
  const [discoverPdfs, setDiscoverPdfs] = useState<boolean>(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [crawlResult, setCrawlResult] = useState<IngestWebsitesResponse | null>(null);

  if (!isOpen) return null;

  async function handleStartCrawl() {
    setLoading(true);
    setError(null);
    setCrawlResult(null);

    try {
      const response = await knowledgeApi.crawlWebsites(
        {
          max_pages: maxPages,
          discover_pdfs: discoverPdfs,
        },
        { adminKey }
      );

      setCrawlResult(response);
      onSuccess(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Website crawl failed.");
    } finally {
      setLoading(false);
    }
  }

  function handleReset() {
    setError(null);
    setCrawlResult(null);
    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs"
      onClick={loading ? undefined : handleReset}
      role="dialog"
      aria-modal="true"
      aria-labelledby="crawl-modal-title"
    >
      <div
        className="w-full max-w-2xl rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl transition"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-100 pb-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-100 text-purple-700">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
              </svg>
            </div>
            <div>
              <h3 id="crawl-modal-title" className="text-lg font-bold text-slate-900">
                Crawl Approved ASTU Websites
              </h3>
              <p className="text-xs text-slate-500">
                Batch crawl candidate and approved sources from the source registry
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
              Crawl Execution Failed
            </p>
            <p className="mt-1">{error}</p>
          </div>
        )}

        {/* Live Loading State */}
        {loading && (
          <div className="my-6 rounded-2xl border border-purple-200 bg-purple-50/60 p-6 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-purple-100 text-purple-700">
              <svg className="h-6 w-6 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
            </div>
            <h4 className="mt-3 text-sm font-bold text-purple-950">
              Crawl In Progress...
            </h4>
            <p className="mt-1 text-xs text-purple-700 max-w-sm mx-auto">
              Scanning approved ASTU domains, respecting robots.txt, checking links, and indexing newly updated documents.
            </p>
          </div>
        )}

        {/* Results Feedback */}
        {crawlResult && !loading && (
          <div className="mt-4 space-y-3">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5 text-center text-xs">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-2.5">
                <span className="text-slate-500 font-semibold block text-[11px] uppercase">Attempted</span>
                <span className="text-base font-bold text-slate-900">{crawlResult.total_attempted}</span>
              </div>
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-2.5">
                <span className="text-emerald-700 font-semibold block text-[11px] uppercase">Successful</span>
                <span className="text-base font-bold text-emerald-800">{crawlResult.successful}</span>
              </div>
              <div className="rounded-xl border border-blue-200 bg-blue-50 p-2.5">
                <span className="text-blue-700 font-semibold block text-[11px] uppercase">Unchanged</span>
                <span className="text-base font-bold text-blue-800">{crawlResult.unchanged}</span>
              </div>
              <div className="rounded-xl border border-orange-200 bg-orange-50 p-2.5">
                <span className="text-orange-700 font-semibold block text-[11px] uppercase">Needs OCR</span>
                <span className="text-base font-bold text-orange-800">{crawlResult.requires_ocr}</span>
              </div>
              <div className="rounded-xl border border-rose-200 bg-rose-50 p-2.5">
                <span className="text-rose-700 font-semibold block text-[11px] uppercase">Failed</span>
                <span className="text-base font-bold text-rose-800">{crawlResult.failed}</span>
              </div>
            </div>

            <div className="max-h-48 overflow-y-auto rounded-xl border border-slate-200 bg-slate-50 p-2 text-xs">
              <p className="px-2 py-1 font-semibold text-slate-500 text-[11px] uppercase tracking-wider">
                Crawled Document Details
              </p>
              <div className="divide-y divide-slate-200">
                {crawlResult.results.map((r, i) => (
                  <div key={i} className="flex items-center justify-between p-2">
                    <div className="truncate pr-2">
                      <p className="font-medium text-slate-800 truncate">{r.document_name}</p>
                      <p className="text-[11px] text-slate-500 truncate">{r.message}</p>
                    </div>
                    <span
                      className={`shrink-0 rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase ${
                        r.status === "indexed"
                          ? "bg-emerald-100 text-emerald-800"
                          : r.status === "unchanged"
                          ? "bg-blue-100 text-blue-800"
                          : r.status === "scanned_requires_ocr"
                          ? "bg-orange-100 text-orange-800"
                          : "bg-rose-100 text-rose-800"
                      }`}
                    >
                      {r.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Configuration Form */}
        {!crawlResult && !loading && (
          <div className="mt-4 space-y-4">
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-600 block mb-2">
                Active Source Registry ({sources.length} Configured URLs)
              </span>
              <ul className="space-y-1 text-xs text-slate-700 max-h-32 overflow-y-auto pr-1">
                {sources.map((s, idx) => (
                  <li key={idx} className="flex items-center justify-between bg-white px-2.5 py-1.5 rounded-lg border border-slate-200">
                    <span className="truncate font-medium">{s.title || s.url}</span>
                    <span className="text-[10px] text-slate-400 font-mono shrink-0 ml-2">
                      {s.last_status || "candidate"}
                    </span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label htmlFor="max-pages-input" className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
                  Maximum Crawl Pages
                </label>
                <input
                  id="max-pages-input"
                  type="number"
                  min={1}
                  max={50}
                  value={maxPages}
                  onChange={(e) => setMaxPages(parseInt(e.target.value) || 15)}
                  className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-100"
                />
                <p className="mt-1 text-[11px] text-slate-500">
                  Caps crawling depth to prevent excessive load on university servers.
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
                  Linked PDF Discovery
                </label>
                <label className="mt-2.5 flex cursor-pointer items-center gap-2.5 rounded-xl border border-slate-200 bg-slate-50 p-2.5 text-xs text-slate-700 hover:bg-slate-100">
                  <input
                    type="checkbox"
                    checked={discoverPdfs}
                    onChange={(e) => setDiscoverPdfs(e.target.checked)}
                    className="rounded text-purple-600 focus:ring-purple-500"
                  />
                  <span className="font-medium">Discover & Ingest Linked PDFs</span>
                </label>
                <p className="mt-1 text-[11px] text-slate-500">
                  Finds downloadable official ASTU PDF attachments and schedules.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Footer Actions */}
        <div className="mt-6 flex items-center justify-end gap-3 border-t border-slate-100 pt-4">
          <button
            type="button"
            onClick={handleReset}
            disabled={loading}
            className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {crawlResult ? "Done" : "Cancel"}
          </button>
          {!crawlResult && (
            <button
              type="button"
              onClick={handleStartCrawl}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-xl bg-purple-700 px-5 py-2 text-xs font-semibold text-white hover:bg-purple-800 disabled:cursor-not-allowed disabled:opacity-50 transition"
            >
              Start Website Crawl
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
