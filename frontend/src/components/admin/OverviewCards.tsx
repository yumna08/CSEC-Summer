import React from "react";
import { OverviewStats } from "@/types/knowledge";

interface OverviewCardsProps {
  stats: OverviewStats;
  loading?: boolean;
}

export function OverviewCards({ stats, loading }: OverviewCardsProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="animate-pulse rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
          >
            <div className="h-4 w-1/2 rounded bg-slate-200" />
            <div className="mt-3 h-8 w-2/3 rounded bg-slate-200" />
            <div className="mt-2 h-3 w-3/4 rounded bg-slate-100" />
          </div>
        ))}
      </div>
    );
  }

  const cards = [
    {
      label: "Total Documents",
      value: stats.totalDocuments,
      description: "Indexed in catalog",
      color: "text-slate-900",
      badgeBg: "bg-slate-100",
      badgeText: "text-slate-700",
      icon: (
        <svg className="h-5 w-5 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      ),
    },
    {
      label: "Verified Sources",
      value: stats.verifiedDocuments,
      description: "Official ASTU data",
      color: "text-emerald-700",
      badgeBg: "bg-emerald-50",
      badgeText: "text-emerald-700",
      icon: (
        <svg className="h-5 w-5 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
        </svg>
      ),
    },
    {
      label: "Candidate Sources",
      value: stats.candidateDocuments,
      description: "Pending verification",
      color: "text-amber-700",
      badgeBg: "bg-amber-50",
      badgeText: "text-amber-800",
      icon: (
        <svg className="h-5 w-5 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
      ),
    },
    {
      label: "Failed Ingestions",
      value: stats.failedSources,
      description: stats.failedSources > 0 ? "Requires attention" : "All healthy",
      color: stats.failedSources > 0 ? "text-rose-700" : "text-slate-700",
      badgeBg: stats.failedSources > 0 ? "bg-rose-50 border border-rose-200" : "bg-slate-100",
      badgeText: stats.failedSources > 0 ? "text-rose-700 font-semibold" : "text-slate-600",
      icon: (
        <svg className={`h-5 w-5 ${stats.failedSources > 0 ? "text-rose-600" : "text-slate-400"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
    },
    {
      label: "Indexed Chunks",
      value: stats.totalChunks,
      description: "In ChromaDB vectors",
      color: "text-indigo-700",
      badgeBg: "bg-indigo-50",
      badgeText: "text-indigo-700",
      icon: (
        <svg className="h-5 w-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
        </svg>
      ),
    },
    {
      label: "Requires OCR",
      value: stats.requiresOcrCount,
      description: stats.requiresOcrCount > 0 ? "Scanned PDFs detected" : "Zero scanned docs",
      color: stats.requiresOcrCount > 0 ? "text-orange-700" : "text-slate-700",
      badgeBg: stats.requiresOcrCount > 0 ? "bg-orange-50 border border-orange-200" : "bg-slate-100",
      badgeText: stats.requiresOcrCount > 0 ? "text-orange-700 font-semibold" : "text-slate-600",
      icon: (
        <svg className={`h-5 w-5 ${stats.requiresOcrCount > 0 ? "text-orange-600" : "text-slate-400"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
        </svg>
      ),
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
      {cards.map((card) => (
        <div
          key={card.label}
          className="flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition hover:shadow-md"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              {card.label}
            </span>
            <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${card.badgeBg}`}>
              {card.icon}
            </div>
          </div>
          <div className="mt-3">
            <span className={`text-2xl font-bold tracking-tight sm:text-3xl ${card.color}`}>
              {card.value.toLocaleString()}
            </span>
            <p className="mt-1 text-xs text-slate-500">{card.description}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
