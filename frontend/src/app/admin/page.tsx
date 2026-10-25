"use client";

import Link from "next/link";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AdminAuthModal } from "@/components/admin/AdminAuthModal";
import { CrawlWebsitesModal } from "@/components/admin/CrawlWebsitesModal";
import { DeleteConfirmModal } from "@/components/admin/DeleteConfirmModal";
import { DocumentPreviewModal } from "@/components/admin/DocumentPreviewModal";
import { DocumentTable } from "@/components/admin/DocumentTable";
import { IngestUrlModal } from "@/components/admin/IngestUrlModal";
import { NotificationBanner } from "@/components/admin/NotificationBanner";
import { OverviewCards } from "@/components/admin/OverviewCards";
import { ReindexConfirmModal } from "@/components/admin/ReindexConfirmModal";
import { UploadDocumentModal } from "@/components/admin/UploadDocumentModal";
import { knowledgeApi } from "@/services/api";
import {
  DocumentMetadata,
  NotificationState,
  OverviewStats,
  SourceRegistryItem,
} from "@/types/knowledge";

export default function AdminDashboardPage() {
  const [documents, setDocuments] = useState<DocumentMetadata[]>([]);
  const [sources, setSources] = useState<SourceRegistryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [adminKey, setAdminKey] = useState<string>("");
  const [notification, setNotification] = useState<NotificationState | null>(null);

  // Modal states
  const [previewDoc, setPreviewDoc] = useState<DocumentMetadata | null>(null);
  const [deleteDoc, setDeleteDoc] = useState<DocumentMetadata | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [isUrlModalOpen, setIsUrlModalOpen] = useState(false);
  const [initialIngestUrl, setInitialIngestUrl] = useState<string>("");
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [isCrawlModalOpen, setIsCrawlModalOpen] = useState(false);
  const [isReindexModalOpen, setIsReindexModalOpen] = useState(false);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);

  // Compute overview statistics
  const stats: OverviewStats = useMemo(() => {
    let verified = 0;
    let candidate = 0;
    let failed = 0;
    let totalChunks = 0;
    let requiresOcrCount = 0;

    documents.forEach((d) => {
      totalChunks += d.chunk_count || 0;
      if (d.requires_ocr) requiresOcrCount++;
      if (d.verification_status === "verified") verified++;
      else if (d.verification_status === "candidate") candidate++;
      else if (d.verification_status === "failed") failed++;
    });

    return {
      totalDocuments: documents.length,
      verifiedDocuments: verified,
      candidateDocuments: candidate,
      failedSources: failed,
      totalChunks,
      requiresOcrCount,
    };
  }, [documents]);

  // Load documents and configured sources for manual triggers / mutations
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [docsResp, sourcesResp] = await Promise.allSettled([
        knowledgeApi.fetchDocuments({ adminKey }),
        knowledgeApi.fetchSources({ adminKey }),
      ]);

      if (docsResp.status === "fulfilled") {
        setDocuments(docsResp.value.documents || []);
      } else {
        setNotification({
          type: "error",
          message: "Failed to load documents catalog.",
          details: docsResp.reason instanceof Error ? docsResp.reason.message : String(docsResp.reason),
        });
      }

      if (sourcesResp.status === "fulfilled") {
        setSources(sourcesResp.value.sources || []);
      }
    } finally {
      setLoading(false);
    }
  }, [adminKey]);

  useEffect(() => {
    let ignore = false;

    async function initialFetch() {
      try {
        const [docsResp, sourcesResp] = await Promise.allSettled([
          knowledgeApi.fetchDocuments({ adminKey }),
          knowledgeApi.fetchSources({ adminKey }),
        ]);

        if (ignore) return;

        if (docsResp.status === "fulfilled") {
          setDocuments(docsResp.value.documents || []);
        } else {
          setNotification({
            type: "error",
            message: "Failed to load documents catalog.",
            details: docsResp.reason instanceof Error ? docsResp.reason.message : String(docsResp.reason),
          });
        }

        if (sourcesResp.status === "fulfilled") {
          setSources(sourcesResp.value.sources || []);
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    }

    initialFetch();

    return () => {
      ignore = true;
    };
  }, [adminKey]);

  // Handle document deletion
  async function handleDeleteDocument() {
    if (!deleteDoc) return;
    setDeleteLoading(true);

    try {
      const resp = await knowledgeApi.deleteDocument(deleteDoc.doc_id, { adminKey });
      setNotification({
        type: "success",
        message: `Deleted "${deleteDoc.source_title || deleteDoc.document_name}"`,
        details: resp.message,
      });
      setDeleteDoc(null);
      await loadData();
    } catch (err) {
      setNotification({
        type: "error",
        message: "Failed to delete document.",
        details: err instanceof Error ? err.message : "Backend error",
      });
    } finally {
      setDeleteLoading(false);
    }
  }

  function handleRetryUrl(url: string) {
    setInitialIngestUrl(url);
    setIsUrlModalOpen(true);
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col">
      {/* Top Navigation Bar */}
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur-xs">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between px-4 py-3 sm:px-6">
          {/* Brand */}
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-700 text-base font-bold text-white shadow-xs">
              C
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-bold text-slate-900 sm:text-lg">
                  ASTU CampusGuide AI
                </h1>
                <span className="rounded-md bg-blue-100 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider text-blue-800">
                  Admin
                </span>
              </div>
              <p className="text-xs text-slate-500">
                Knowledge Management &amp; Ingestion Control Panel
              </p>
            </div>
          </div>

          {/* Header Controls */}
          <div className="flex items-center gap-2 sm:gap-3">
            {/* Admin Key Status Button */}
            <button
              onClick={() => setIsAuthModalOpen(true)}
              className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-semibold transition ${
                adminKey
                  ? "border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100"
                  : "border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100"
              }`}
              title="Configure X-Admin-Key"
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  adminKey ? "bg-emerald-600" : "bg-slate-400"
                }`}
              />
              <span className="hidden sm:inline">
                {adminKey ? "Admin Authenticated" : "Dev Auth Mode"}
              </span>
              <span className="sm:hidden">Auth</span>
            </button>

            {/* Refresh Button */}
            <button
              onClick={loadData}
              disabled={loading}
              className="rounded-xl border border-slate-200 bg-white p-2 text-slate-600 hover:bg-slate-50 hover:text-slate-900 disabled:opacity-50"
              title="Refresh knowledge base"
              aria-label="Refresh knowledge base"
            >
              <svg
                className={`h-4 w-4 ${loading ? "animate-spin text-blue-600" : ""}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>

            {/* Back to Student Chatbot */}
            <Link
              href="/"
              className="inline-flex items-center gap-1.5 rounded-xl bg-slate-900 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 transition shadow-xs"
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              <span>Student Chat</span>
            </Link>
          </div>
        </div>
      </header>

      {/* Main Workspace */}
      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 p-4 sm:p-6 lg:p-8">
        {/* Notification Banner */}
        <NotificationBanner
          notification={notification}
          onDismiss={() => setNotification(null)}
        />

        {/* Action Controls & Overview Header */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-xl font-bold tracking-tight text-slate-900 sm:text-2xl">
              Knowledge Repository
            </h2>
            <p className="mt-1 text-xs sm:text-sm text-slate-500">
              Manage ASTU official reference materials, crawled web domains, and uploaded files.
            </p>
          </div>

          {/* Quick Actions Buttons */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => {
                setInitialIngestUrl("");
                setIsUrlModalOpen(true);
              }}
              className="inline-flex items-center gap-1.5 rounded-xl bg-blue-700 px-3.5 py-2 text-xs font-semibold text-white hover:bg-blue-800 transition shadow-xs"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
              </svg>
              Ingest Webpage
            </button>

            <button
              onClick={() => setIsUploadModalOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition shadow-xs"
            >
              <svg className="h-4 w-4 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
              Upload Document
            </button>

            <button
              onClick={() => setIsCrawlModalOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition shadow-xs"
            >
              <svg className="h-4 w-4 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
              </svg>
              Crawl Websites
            </button>

            <button
              onClick={() => setIsReindexModalOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition shadow-xs"
              title="Check hashes and update out-of-date vector chunks"
            >
              <svg className="h-4 w-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Reindex All
            </button>
          </div>
        </div>

        {/* Overview Stats Cards */}
        <OverviewCards stats={stats} loading={loading} />

        {/* Documents Table */}
        <section aria-labelledby="documents-table-title" className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 id="documents-table-title" className="text-base font-bold text-slate-900">
              Indexed Documents &amp; Sources
            </h3>
            <span className="text-xs text-slate-500">
              Click any row to view metadata, hashes, and OCR status
            </span>
          </div>

          <DocumentTable
            documents={documents}
            loading={loading}
            onPreview={(doc) => setPreviewDoc(doc)}
            onDelete={(doc) => setDeleteDoc(doc)}
            onRetryUrl={handleRetryUrl}
          />
        </section>
      </main>

      {/* Footer */}
      <footer className="mt-auto border-t border-slate-200 bg-white py-4 text-center text-xs text-slate-500">
        <p>
          ASTU CampusGuide AI • Admin Knowledge Management • Connected to ChromaDB &amp; Gemini RAG Pipeline
        </p>
      </footer>

      {/* Modals & Dialogs */}
      <DocumentPreviewModal
        document={previewDoc}
        onClose={() => setPreviewDoc(null)}
        onDelete={(doc) => {
          setPreviewDoc(null);
          setDeleteDoc(doc);
        }}
        onRetryUrl={handleRetryUrl}
      />

      <DeleteConfirmModal
        document={deleteDoc}
        loading={deleteLoading}
        onConfirm={handleDeleteDocument}
        onCancel={() => setDeleteDoc(null)}
      />

      <IngestUrlModal
        isOpen={isUrlModalOpen}
        initialUrl={initialIngestUrl}
        adminKey={adminKey}
        onClose={() => setIsUrlModalOpen(false)}
        onSuccess={async (result) => {
          setIsUrlModalOpen(false);
          setNotification({
            type: "success",
            message: `Webpage ingested: "${result.document_name}"`,
            details: `${result.chunk_count} vector chunks generated (${result.status}).`,
          });
          await loadData();
        }}
      />

      <UploadDocumentModal
        isOpen={isUploadModalOpen}
        adminKey={adminKey}
        onClose={() => setIsUploadModalOpen(false)}
        onSuccess={async (result) => {
          setIsUploadModalOpen(false);
          setNotification({
            type: "success",
            message: `Document indexed: "${result.document_name}"`,
            details: `${result.chunk_count} vector chunks generated (${result.status}).`,
          });
          await loadData();
        }}
      />

      <CrawlWebsitesModal
        isOpen={isCrawlModalOpen}
        sources={sources}
        adminKey={adminKey}
        onClose={() => setIsCrawlModalOpen(false)}
        onSuccess={async (response) => {
          setNotification({
            type: "success",
            message: "Website crawl finished",
            details: `Processed ${response.total_attempted} targets (${response.successful} successful, ${response.unchanged} unchanged, ${response.failed} failed).`,
          });
          await loadData();
        }}
      />

      <ReindexConfirmModal
        isOpen={isReindexModalOpen}
        adminKey={adminKey}
        onClose={() => setIsReindexModalOpen(false)}
        onSuccess={async (response) => {
          setIsReindexModalOpen(false);
          setNotification({
            type: "success",
            message: "Reindex complete",
            details: `Successfully processed ${response.total_reindexed} registered sources.`,
          });
          await loadData();
        }}
      />

      <AdminAuthModal
        isOpen={isAuthModalOpen}
        currentKey={adminKey}
        onClose={() => setIsAuthModalOpen(false)}
        onSaveKey={(newKey) => {
          setAdminKey(newKey);
          setNotification({
            type: "info",
            message: newKey ? "Admin authorization key saved for this session." : "Admin key cleared (using dev mode).",
          });
        }}
      />
    </div>
  );
}
