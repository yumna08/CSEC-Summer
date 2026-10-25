"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type SourceCitation = {
  title: string;
  url?: string | null;
  document_name?: string | null;
  academic_year?: string | null;
  publication_date?: string | null;
  snippet?: string | null;
};

type Message = {
  role: "user" | "assistant";
  content: string;
  sources?: SourceCitation[];
};

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(() =>
    typeof window === "undefined"
      ? null
      : window.localStorage.getItem("campusguide_session_id"),
  );
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function startNewChat() {
    window.localStorage.removeItem("campusguide_session_id");
    setSessionId(null);
    setMessages([]);
    setError("");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const question = input.trim();
    if (!question || loading) return;

    setMessages((previous) => [
      ...previous,
      { role: "user", content: question },
    ]);
    setInput("");
    setError("");
    setLoading(true);

    try {
      const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
      const response = await fetch(`${apiBaseUrl}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: question,
          ...(sessionId ? { session_id: sessionId } : {}),
        }),
      });

      const contentType = response.headers.get("content-type") || "";
      let data: {
        reply?: string;
        answer?: string;
        session_id?: string;
        sources?: SourceCitation[];
        detail?: string;
      } = {};

      if (contentType.includes("application/json")) {
        data = await response.json();
      } else {
        const text = await response.text();
        throw new Error(text || `Server returned non-JSON response (${response.status})`);
      }

      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Unable to get a response. Please try again.",
        );
      }

      if (data.session_id) {
        window.localStorage.setItem("campusguide_session_id", data.session_id);
        setSessionId(data.session_id);
      }

      setMessages((previous) => [
        ...previous,
        {
          role: "assistant",
          content: data.reply || data.answer || "",
          sources: Array.isArray(data.sources) ? data.sources : [],
        },
      ]);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not connect to CampusGuide. Check that the backend is running.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex w-full max-w-4xl items-center justify-between px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-700 text-lg font-bold text-white">
              C
            </div>
            <div>
              <h1 className="text-lg font-bold">ASTU CampusGuide AI</h1>
              <p className="text-sm text-slate-500">
                Your student-focused AI assistant
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2.5">
            <div className="hidden sm:flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200 text-xs font-medium">
              <span className="h-2 w-2 rounded-full bg-blue-600"></span>
              ASTU RAG Grounding
            </div>
            <Link
              href="/admin"
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition shadow-xs"
            >
              <svg className="h-3.5 w-3.5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              <span>Admin Portal</span>
            </Link>
            <button
              type="button"
              onClick={startNewChat}
              className="rounded-xl border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-700 transition hover:bg-blue-100"
            >
              New chat
            </button>
          </div>
        </div>
      </header>

      <section className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4 py-8">
        {messages.length === 0 ? (
          <div className="my-auto py-12 text-center">
            <p className="text-sm font-semibold uppercase tracking-widest text-blue-700">
              Welcome to CampusGuide
            </p>
            <h2 className="mt-4 text-3xl font-bold tracking-tight sm:text-4xl">
              What would you like to know?
            </h2>
            <p className="mx-auto mt-4 max-w-lg leading-7 text-slate-600">
              Ask a question about university life, learning, or student
              resources. Verified ASTU information will be added as we build
              the knowledge base.
            </p>

            <div className="mx-auto mt-8 grid max-w-xl gap-3 text-left sm:grid-cols-2">
              {[
                "How can I prepare for exams?",
                "Give me a study plan for this week.",
                "How can I improve my programming skills?",
                "What information should a new student look for?",
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => setInput(suggestion)}
                  className="rounded-xl border border-slate-200 bg-white p-4 text-sm transition hover:border-blue-400 hover:bg-blue-50"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div
            className="flex-1 space-y-6"
            aria-live="polite"
            aria-busy={loading}
          >
            {messages.map((message, index) => (

              <div
                key={`${message.role}-${index}`}
                className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[90%] rounded-2xl px-4 py-3 leading-7 sm:max-w-[80%] ${message.role === "user"
                      ? "bg-blue-700 text-white whitespace-pre-wrap"
                      : "border border-slate-200 bg-white text-slate-800 shadow-sm whitespace-normal"
                    }`}
                >
                  {message.role === "user" ? (
                    <div className="text-sm leading-7 break-words">{message.content}</div>
                  ) : (
                    <div className="text-sm leading-7 break-words space-y-2">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          h1: ({ children }) => (
                            <h1 className="text-lg font-bold my-2 text-slate-900">{children}</h1>
                          ),
                          h2: ({ children }) => (
                            <h2 className="text-base font-bold my-2 text-slate-900">{children}</h2>
                          ),
                          h3: ({ children }) => (
                            <h3 className="text-sm font-semibold my-1.5 text-slate-900">{children}</h3>
                          ),
                          p: ({ children }) => (
                            <p className="mb-2.5 last:mb-0 leading-relaxed text-slate-800">{children}</p>
                          ),
                          ul: ({ children }) => (
                            <ul className="my-2 list-disc space-y-1 pl-5 text-slate-800">{children}</ul>
                          ),
                          ol: ({ children }) => (
                            <ol className="my-2 list-decimal space-y-1 pl-5 text-slate-800">{children}</ol>
                          ),
                          li: ({ children }) => (
                            <li className="pl-0.5 leading-relaxed">{children}</li>
                          ),
                          strong: ({ children }) => (
                            <strong className="font-semibold text-slate-900">{children}</strong>
                          ),
                          em: ({ children }) => (
                            <em className="italic">{children}</em>
                          ),
                          blockquote: ({ children }) => (
                            <blockquote className="border-l-4 border-blue-200 pl-3 my-2 text-slate-600 italic">
                              {children}
                            </blockquote>
                          ),
                          code: ({ children, ...props }: React.ComponentPropsWithoutRef<"code">) => {
                            const isBlock = typeof children === "string" && children.includes("\n");
                            return isBlock ? (
                              <pre className="my-2 overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100 font-mono">
                                <code>{children}</code>
                              </pre>
                            ) : (
                              <code
                                className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-800"
                                {...props}
                              >
                                {children}
                              </code>
                            );
                          },
                          a: ({ children, href }) => (
                            <a
                              href={href}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="break-all font-medium text-blue-700 underline underline-offset-2 hover:text-blue-900"
                            >
                              {children}
                            </a>
                          ),
                        }}
                      >
                        {message.content}
                      </ReactMarkdown>
                    </div>
                  )}

                  {message.role === "assistant" && (() => {
                    const sources = Array.isArray(message.sources) ? message.sources : [];
                    const deduplicatedSources = sources.filter((src, idx, arr) => {
                      if (!src || (!src.title && !src.url && !src.document_name)) return false;
                      const key = `${(src.url || "").trim().toLowerCase()}|${(src.title || "").trim().toLowerCase()}`;
                      return (
                        arr.findIndex(
                          (s) =>
                            `${(s.url || "").trim().toLowerCase()}|${(s.title || "").trim().toLowerCase()}` === key
                        ) === idx
                      );
                    });

                    if (deduplicatedSources.length === 0) return null;

                    return (
                      <div className="mt-3 border-t border-slate-100 pt-2.5 text-xs text-slate-600">
                        <div className="font-semibold text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                          <span aria-hidden="true" className="flex-shrink-0 text-blue-600">
                            <svg
                              className="w-3.5 h-3.5"
                              aria-hidden="true"
                              focusable="false"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth="2"
                                d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
                              />
                            </svg>
                          </span>
                          <span>Sources</span>
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {deduplicatedSources.map((src, idx) =>
                            src.url ? (
                              <a
                                key={`${src.url}-${idx}`}
                                href={src.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 transition border border-blue-200 font-medium text-xs"
                                title={src.snippet || src.title}
                              >
                                <span>{src.title || src.document_name || "ASTU Source"}</span>
                                <span aria-hidden="true" className="flex-shrink-0 text-blue-500">
                                  <svg
                                    className="w-3 h-3 opacity-75"
                                    aria-hidden="true"
                                    focusable="false"
                                    fill="none"
                                    stroke="currentColor"
                                    viewBox="0 0 24 24"
                                  >
                                    <path
                                      strokeLinecap="round"
                                      strokeLinejoin="round"
                                      strokeWidth="2"
                                      d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                                    />
                                  </svg>
                                </span>
                              </a>
                            ) : (
                              <span
                                key={`${src.title || "doc"}-${idx}`}
                                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-100 text-slate-700 border border-slate-200 text-xs font-medium"
                                title={src.snippet || src.title}
                              >
                                <span aria-hidden="true">📄</span>
                                <span>{src.title || src.document_name || "ASTU Document"}</span>
                              </span>
                            )
                          )}
                        </div>
                      </div>
                    );
                  })()}
                </div>
              </div>
            ))}

            {loading && (
              <p className="text-sm text-slate-500" role="status">
                CampusGuide is thinking...
              </p>
            )}
          </div>
        )}

        {error && (
          <p
            className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
            role="alert"
          >
            {error}
          </p>
        )}

        <form
          onSubmit={handleSubmit}
          className="mt-8 flex items-end gap-3 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm"
        >
          <label htmlFor="question" className="sr-only">
            Ask CampusGuide a question
          </label>
          <textarea
            id="question"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (
                event.key === "Enter" &&
                !event.shiftKey &&
                !event.nativeEvent.isComposing
              ) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder="Ask your question..."
            maxLength={2000}
            rows={2}
            className="max-h-40 min-h-12 flex-1 resize-y bg-transparent px-2 py-3 text-sm outline-none placeholder:text-slate-400"
          />
          <button
            type="submit"
            disabled={!input.trim() || loading}
            className="rounded-xl bg-blue-700 px-5 py-3 text-sm font-semibold text-white transition hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Sending..." : "Send"}
          </button>
        </form>

        <p className="mt-4 text-center text-xs leading-5 text-slate-500">
          AI responses may be inaccurate. Verify university policies and
          deadlines through official sources. Independent student project,
          not an official ASTU service.
        </p>
      </section>
    </main>
  );
}
