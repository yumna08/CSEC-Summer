import React, { useState } from "react";

interface AdminAuthModalProps {
  isOpen: boolean;
  currentKey: string;
  onClose: () => void;
  onSaveKey: (newKey: string) => void;
}

export function AdminAuthModal({
  isOpen,
  currentKey,
  onClose,
  onSaveKey,
}: AdminAuthModalProps) {
  const [keyInput, setKeyInput] = useState(currentKey);
  const [showKey, setShowKey] = useState(false);

  if (!isOpen) return null;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSaveKey(keyInput.trim());
    onClose();
  }

  function handleClear() {
    setKeyInput("");
    onSaveKey("");
    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="auth-modal-title"
    >
      <div
        className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl transition"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-100 pb-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-100 text-amber-700">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            </div>
            <div>
              <h3 id="auth-modal-title" className="text-lg font-bold text-slate-900">
                Admin Authentication
              </h3>
              <p className="text-xs text-slate-500">
                Configure X-Admin-Key for mutating knowledge operations
              </p>
            </div>
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

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <div>
            <label htmlFor="admin-key-input" className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
              Administrative Secret Key
            </label>
            <div className="relative mt-1.5">
              <input
                id="admin-key-input"
                type={showKey ? "text" : "password"}
                value={keyInput}
                onChange={(e) => setKeyInput(e.target.value)}
                placeholder="Enter ADMIN_API_KEY from backend"
                className="w-full rounded-xl border border-slate-200 px-3 py-2 pr-10 text-sm font-mono text-slate-900 outline-none focus:border-amber-500 focus:ring-2 focus:ring-amber-100"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600 text-xs font-medium"
              >
                {showKey ? "Hide" : "Show"}
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-slate-100 bg-slate-50 p-3 text-xs text-slate-600 leading-relaxed">
            <p className="font-semibold text-slate-800">Security Architecture:</p>
            <ul className="mt-1 list-disc list-inside space-y-1 text-[11px] text-slate-600">
              <li>In standard local development (<code>REQUIRE_ADMIN_AUTH=false</code>), backend permits actions without a key.</li>
              <li>When configured on the backend, this key is sent in the <code>X-Admin-Key</code> header for URL ingestion, uploads, deletions, and reindexing.</li>
              <li>The key is preserved only in this browser session and never committed to version control or <code>NEXT_PUBLIC_</code> environment variables.</li>
            </ul>
          </div>

          <div className="flex items-center justify-between pt-2 border-t border-slate-100">
            {currentKey ? (
              <button
                type="button"
                onClick={handleClear}
                className="text-xs font-medium text-rose-600 hover:underline"
              >
                Clear Key
              </button>
            ) : <div />}

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="rounded-xl bg-amber-600 px-4 py-2 text-xs font-semibold text-white hover:bg-amber-700 transition"
              >
                Save Key
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
