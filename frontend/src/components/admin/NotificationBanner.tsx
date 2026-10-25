import React from "react";
import { NotificationState } from "@/types/knowledge";

interface NotificationBannerProps {
  notification: NotificationState | null;
  onDismiss: () => void;
}

export function NotificationBanner({
  notification,
  onDismiss,
}: NotificationBannerProps) {
  if (!notification) return null;

  const isSuccess = notification.type === "success";
  const isError = notification.type === "error";

  return (
    <div
      role="status"
      className={`flex items-start justify-between rounded-2xl border p-4 shadow-sm transition ${
        isSuccess
          ? "border-emerald-200 bg-emerald-50 text-emerald-950"
          : isError
          ? "border-rose-200 bg-rose-50 text-rose-950"
          : "border-blue-200 bg-blue-50 text-blue-950"
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 shrink-0">
          {isSuccess && (
            <div className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
              </svg>
            </div>
          )}
          {isError && (
            <div className="flex h-6 w-6 items-center justify-center rounded-full bg-rose-100 text-rose-600">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
          )}
        </div>
        <div>
          <p className="text-sm font-semibold">{notification.message}</p>
          {notification.details && (
            <p className="mt-0.5 text-xs opacity-90 leading-relaxed font-mono">{notification.details}</p>
          )}
        </div>
      </div>

      <button
        type="button"
        onClick={onDismiss}
        className="rounded-lg p-1 text-slate-400 hover:bg-black/5 hover:text-slate-700"
        aria-label="Dismiss notification"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}
