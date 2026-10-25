import React, { useMemo, useState } from "react";
import { DocumentMetadata, SourceType, VerificationStatus } from "@/types/knowledge";

interface DocumentTableProps {
  documents: DocumentMetadata[];
  loading: boolean;
  onPreview: (doc: DocumentMetadata) => void;
  onDelete: (doc: DocumentMetadata) => void;
  onRetryUrl?: (url: string) => void;
}

export function DocumentTable({
  documents,
  loading,
  onPreview,
  onDelete,
  onRetryUrl,
}: DocumentTableProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [sortBy, setSortBy] = useState<string>("newest");

  // Filter and sort documents
  const filteredDocuments = useMemo(() => {
    return documents
      .filter((doc) => {
        // Search query
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase().trim();
          const matchesTitle = (doc.source_title || "").toLowerCase().includes(q);
          const matchesDocName = (doc.document_name || "").toLowerCase().includes(q);
          const matchesUrl = (doc.source_url || "").toLowerCase().includes(q);
          const matchesId = (doc.doc_id || "").toLowerCase().includes(q);
          if (!matchesTitle && !matchesDocName && !matchesUrl && !matchesId) {
            return false;
          }
        }

        // Status filter
        if (statusFilter !== "all") {
          if (statusFilter === "requires_ocr") {
            if (!doc.requires_ocr) return false;
          } else if (doc.verification_status !== statusFilter) {
            return false;
          }
        }

        // Type filter
        if (typeFilter !== "all") {
          if (doc.source_type.toLowerCase() !== typeFilter.toLowerCase()) {
            return false;
          }
        }

        return true;
      })
      .sort((a, b) => {
        if (sortBy === "newest") {
          return new Date(b.fetched_at).getTime() - new Date(a.fetched_at).getTime();
        }
        if (sortBy === "oldest") {
          return new Date(a.fetched_at).getTime() - new Date(b.fetched_at).getTime();
        }
        if (sortBy === "title_asc") {
          return (a.source_title || a.document_name).localeCompare(b.source_title || b.document_name);
        }
        if (sortBy === "title_desc") {
          return (b.source_title || b.document_name).localeCompare(a.source_title || a.document_name);
        }
        if (sortBy === "chunks_desc") {
          return b.chunk_count - a.chunk_count;
        }
        return 0;
      });
  }, [documents, searchQuery, statusFilter, typeFilter, sortBy]);

  function getStatusBadge(status: VerificationStatus, requiresOcr: boolean) {
    if (requiresOcr) {
      return (
        <span className="inline-flex items-center gap-1 rounded-full border border-orange-200 bg-orange-50 px-2.5 py-0.5 text-xs font-semibold text-orange-800">
          <span className="h-1.5 w-1.5 rounded-full bg-orange-500" />
          OCR Required
        </span>
      );
    }
    if (status === "verified") {
      return (
        <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-800">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          Verified
        </span>
      );
    }
    if (status === "candidate") {
      return (
        <span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-0.5 text-xs font-semibold text-amber-800">
          <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
          Candidate
        </span>
      );
    }
    if (status === "failed") {
      return (
        <span className="inline-flex items-center gap-1 rounded-full border border-rose-200 bg-rose-50 px-2.5 py-0.5 text-xs font-semibold text-rose-800">
          <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
          Failed
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-xs font-semibold text-slate-700">
        {status}
      </span>
    );
  }

  function getTypeBadge(type: SourceType) {
    const t = (type || "").toLowerCase();
    let bg = "bg-slate-100 text-slate-700 border-slate-200";
    let icon = "📄";
    if (t === "webpage") {
      bg = "bg-blue-50 text-blue-700 border-blue-200";
      icon = "🌐";
    } else if (t === "pdf") {
      bg = "bg-rose-50 text-rose-700 border-rose-200";
      icon = "📕";
    } else if (t === "docx") {
      bg = "bg-indigo-50 text-indigo-700 border-indigo-200";
      icon = "📘";
    } else if (t === "txt" || t === "text" || t === "md") {
      bg = "bg-emerald-50 text-emerald-700 border-emerald-200";
      icon = "📝";
    }
    return (
      <span className={`inline-flex items-center gap-1 rounded-lg border px-2 py-0.5 text-[11px] font-medium uppercase ${bg}`}>
        <span>{icon}</span>
        <span>{t}</span>
      </span>
    );
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-xs">
      {/* Controls Bar: Search, Filters, Sorting */}
      <div className="border-b border-slate-200 p-4 sm:p-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          {/* Search Bar */}
          <div className="relative flex-1 max-w-md">
            <svg
              className="absolute left-3.5 top-3 h-4 w-4 text-slate-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search title, document, URL, or ID..."
              className="w-full rounded-xl border border-slate-200 bg-slate-50/50 py-2 pl-9.5 pr-4 text-xs sm:text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-blue-500 focus:bg-white focus:ring-2 focus:ring-blue-100"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                className="absolute right-3 top-2.5 text-xs text-slate-400 hover:text-slate-600"
              >
                Clear
              </button>
            )}
          </div>

          {/* Filter Dropdowns */}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            {/* Status Filter */}
            <div className="flex items-center gap-1.5">
              <label htmlFor="status-filter" className="text-slate-500 font-semibold uppercase text-[10px]">
                Status:
              </label>
              <select
                id="status-filter"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="rounded-xl border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs text-slate-700 outline-none focus:border-blue-500"
              >
                <option value="all">All Statuses</option>
                <option value="verified">Verified Official</option>
                <option value="candidate">Candidate Sources</option>
                <option value="failed">Failed Ingestions</option>
                <option value="requires_ocr">OCR Required</option>
              </select>
            </div>

            {/* Type Filter */}
            <div className="flex items-center gap-1.5">
              <label htmlFor="type-filter" className="text-slate-500 font-semibold uppercase text-[10px]">
                Type:
              </label>
              <select
                id="type-filter"
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="rounded-xl border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs text-slate-700 outline-none focus:border-blue-500"
              >
                <option value="all">All Types</option>
                <option value="webpage">Webpages</option>
                <option value="pdf">PDF Documents</option>
                <option value="docx">Word (DOCX)</option>
                <option value="txt">Text (TXT/MD)</option>
              </select>
            </div>

            {/* Sorting */}
            <div className="flex items-center gap-1.5">
              <label htmlFor="sort-by" className="text-slate-500 font-semibold uppercase text-[10px]">
                Sort:
              </label>
              <select
                id="sort-by"
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                className="rounded-xl border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs text-slate-700 outline-none focus:border-blue-500"
              >
                <option value="newest">Newest First</option>
                <option value="oldest">Oldest First</option>
                <option value="title_asc">Title (A-Z)</option>
                <option value="title_desc">Title (Z-A)</option>
                <option value="chunks_desc">Chunks (High-Low)</option>
              </select>
            </div>
          </div>
        </div>

        {/* Counter & Active Filter Indicators */}
        <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
          <div>
            Showing <strong className="text-slate-800">{filteredDocuments.length}</strong> of{" "}
            <strong className="text-slate-800">{documents.length}</strong> indexed documents
          </div>
          {(searchQuery || statusFilter !== "all" || typeFilter !== "all") && (
            <button
              onClick={() => {
                setSearchQuery("");
                setStatusFilter("all");
                setTypeFilter("all");
              }}
              className="text-blue-600 hover:underline font-medium"
            >
              Reset Filters
            </button>
          )}
        </div>
      </div>

      {/* Table Content */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs sm:text-sm">
          <thead className="border-b border-slate-200 bg-slate-50/70 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            <tr>
              <th scope="col" className="px-4 py-3 sm:px-6">Document & Source</th>
              <th scope="col" className="px-3 py-3">Type</th>
              <th scope="col" className="px-3 py-3">Status</th>
              <th scope="col" className="px-3 py-3 text-right">Chunks</th>
              <th scope="col" className="px-4 py-3 sm:px-6">Indexed At</th>
              <th scope="col" className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              // Loading Skeleton Rows
              Array.from({ length: 5 }).map((_, idx) => (
                <tr key={idx} className="animate-pulse">
                  <td className="px-4 py-4 sm:px-6">
                    <div className="h-4 w-48 rounded bg-slate-200" />
                    <div className="mt-2 h-3 w-64 rounded bg-slate-100" />
                  </td>
                  <td className="px-3 py-4">
                    <div className="h-5 w-16 rounded bg-slate-200" />
                  </td>
                  <td className="px-3 py-4">
                    <div className="h-5 w-20 rounded bg-slate-200" />
                  </td>
                  <td className="px-3 py-4 text-right">
                    <div className="ml-auto h-4 w-8 rounded bg-slate-200" />
                  </td>
                  <td className="px-4 py-4 sm:px-6">
                    <div className="h-3 w-28 rounded bg-slate-200" />
                  </td>
                  <td className="px-4 py-4 text-right">
                    <div className="ml-auto h-7 w-20 rounded bg-slate-200" />
                  </td>
                </tr>
              ))
            ) : filteredDocuments.length === 0 ? (
              // Empty State
              <tr>
                <td colSpan={6} className="py-12 text-center text-slate-500">
                  <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-400">
                    <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 13h6m-3-3v6m-9 1V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
                    </svg>
                  </div>
                  <p className="mt-3 text-sm font-semibold text-slate-800">
                    {documents.length === 0 ? "Knowledge Base is Empty" : "No Matching Documents Found"}
                  </p>
                  <p className="mt-1 text-xs text-slate-500 max-w-sm mx-auto">
                    {documents.length === 0
                      ? "Use 'Ingest Webpage', 'Upload File', or 'Crawl Websites' to populate official ASTU documents."
                      : "Try adjusting your search query or reset the status/type filters."}
                  </p>
                </td>
              </tr>
            ) : (
              // Document Rows
              filteredDocuments.map((doc) => (
                <tr
                  key={doc.doc_id}
                  className="transition hover:bg-slate-50/80 cursor-pointer"
                  onClick={() => onPreview(doc)}
                >
                  {/* Title & Document Name */}
                  <td className="px-4 py-3.5 sm:px-6 max-w-xs sm:max-w-md">
                    <div className="font-semibold text-slate-900 truncate">
                      {doc.source_title || doc.document_name}
                    </div>
                    <div className="mt-0.5 flex items-center gap-1.5 text-xs text-slate-500 truncate">
                      {doc.source_url ? (
                        <a
                          href={doc.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="truncate hover:text-blue-600 hover:underline flex items-center gap-1"
                          title={doc.source_url}
                        >
                          <span className="truncate">{doc.source_url}</span>
                          <svg className="h-3 w-3 shrink-0 opacity-60" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                          </svg>
                        </a>
                      ) : (
                        <span className="truncate font-mono">{doc.document_name}</span>
                      )}
                    </div>
                  </td>

                  {/* Type */}
                  <td className="px-3 py-3.5 whitespace-nowrap">
                    {getTypeBadge(doc.source_type)}
                  </td>

                  {/* Status */}
                  <td className="px-3 py-3.5 whitespace-nowrap">
                    {getStatusBadge(doc.verification_status, doc.requires_ocr)}
                  </td>

                  {/* Chunks */}
                  <td className="px-3 py-3.5 text-right whitespace-nowrap">
                    <span className="font-bold text-slate-800 font-mono">
                      {doc.chunk_count}
                    </span>
                  </td>

                  {/* Indexed Date */}
                  <td className="px-4 py-3.5 sm:px-6 whitespace-nowrap text-xs text-slate-500">
                    <div>{new Date(doc.fetched_at).toLocaleDateString(undefined, { dateStyle: "medium" })}</div>
                    <div className="text-[10px] text-slate-400 font-mono">
                      {new Date(doc.fetched_at).toLocaleTimeString(undefined, { timeStyle: "short" })}
                    </div>
                  </td>

                  {/* Actions */}
                  <td className="px-4 py-3.5 text-right whitespace-nowrap">
                    <div className="flex items-center justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        onClick={() => onPreview(doc)}
                        className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition"
                        title="View details and metadata"
                      >
                        Inspect
                      </button>

                      {doc.source_url && onRetryUrl && doc.verification_status === "failed" && (
                        <button
                          type="button"
                          onClick={() => onRetryUrl(doc.source_url!)}
                          className="rounded-lg border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700 hover:bg-blue-100 transition"
                          title="Retry ingestion for this URL"
                        >
                          Retry
                        </button>
                      )}

                      <button
                        type="button"
                        onClick={() => onDelete(doc)}
                        className="rounded-lg p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600 transition"
                        title="Delete document"
                        aria-label="Delete document"
                      >
                        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
