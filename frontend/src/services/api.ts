import {
  DeleteDocumentResponse,
  DocumentListResponse,
  IngestResult,
  IngestUrlRequest,
  IngestWebsitesRequest,
  IngestWebsitesResponse,
  ReindexResponse,
  SourcesResponse,
} from "@/types/knowledge";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface RequestOptions {
  adminKey?: string;
  headers?: Record<string, string>;
}

/**
 * Safely parse API responses, preventing runtime crashes on non-JSON payloads (e.g. HTML error pages).
 */
async function handleResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get("content-type") || "";
  let data: Record<string, unknown> | null = null;
  let rawText = "";

  if (contentType.includes("application/json")) {
    try {
      data = (await response.json()) as Record<string, unknown>;
    } catch {
      data = null;
    }
  } else {
    rawText = await response.text();
  }

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error(
        "Administrative authorization required (401 Unauthorized). Please provide a valid Admin Key via 'Set Admin Key'."
      );
    }
    if (response.status === 503) {
      const detail = data && typeof data.detail === "string" ? data.detail : "";
      throw new Error(
        detail ||
          "Administrative operations are unavailable (503). Ensure ADMIN_API_KEY is configured on the backend if required."
      );
    }
    if (response.status === 413) {
      throw new Error(
        "Uploaded file exceeds the maximum allowed size of 10MB (413 Payload Too Large)."
      );
    }
    if (data && typeof data.detail === "string") {
      throw new Error(data.detail);
    }
    if (rawText) {
      const cleanSnippet = rawText.replace(/<[^>]+>/g, " ").slice(0, 160).trim();
      throw new Error(
        `Server returned error (${response.status}): ${cleanSnippet || "Non-JSON response"}`
      );
    }
    throw new Error(`Request failed with status ${response.status}`);
  }

  return data as unknown as T;
}

function buildHeaders(options?: RequestOptions, isJson = true): Record<string, string> {
  const headers: Record<string, string> = { ...options?.headers };
  if (isJson) {
    headers["Content-Type"] = "application/json";
  }
  if (options?.adminKey?.trim()) {
    headers["X-Admin-Key"] = options.adminKey.trim();
  }
  return headers;
}

export const knowledgeApi = {
  /**
   * Fetch all indexed knowledge documents from ChromaDB and catalog.
   */
  async fetchDocuments(options?: RequestOptions): Promise<DocumentListResponse> {
    const response = await fetch(`${API_BASE_URL}/api/knowledge/documents`, {
      method: "GET",
      headers: buildHeaders(options, false),
      cache: "no-store",
    });
    return handleResponse<DocumentListResponse>(response);
  },

  /**
   * Fetch configured source registry items.
   */
  async fetchSources(options?: RequestOptions): Promise<SourcesResponse> {
    const response = await fetch(`${API_BASE_URL}/api/knowledge/sources`, {
      method: "GET",
      headers: buildHeaders(options, false),
      cache: "no-store",
    });
    return handleResponse<SourcesResponse>(response);
  },

  /**
   * Ingest a single approved ASTU webpage URL.
   */
  async ingestUrl(
    request: IngestUrlRequest,
    options?: RequestOptions
  ): Promise<IngestResult> {
    const response = await fetch(`${API_BASE_URL}/api/knowledge/ingest-url`, {
      method: "POST",
      headers: buildHeaders(options, true),
      body: JSON.stringify(request),
    });
    return handleResponse<IngestResult>(response);
  },

  /**
   * Upload and index a document file (PDF, DOCX, TXT).
   */
  async uploadDocument(
    file: File,
    verificationStatus: string = "verified",
    options?: RequestOptions
  ): Promise<IngestResult> {
    const formData = new FormData();
    formData.append("file", file);

    const headers: Record<string, string> = {};
    if (options?.adminKey?.trim()) {
      headers["X-Admin-Key"] = options.adminKey.trim();
    }

    const queryParams = new URLSearchParams({
      verification_status: verificationStatus,
    });

    const response = await fetch(
      `${API_BASE_URL}/api/knowledge/upload?${queryParams.toString()}`,
      {
        method: "POST",
        headers,
        body: formData,
      }
    );
    return handleResponse<IngestResult>(response);
  },

  /**
   * Crawl approved ASTU websites and discovered PDFs.
   */
  async crawlWebsites(
    request: IngestWebsitesRequest = {},
    options?: RequestOptions
  ): Promise<IngestWebsitesResponse> {
    const response = await fetch(`${API_BASE_URL}/api/knowledge/ingest-websites`, {
      method: "POST",
      headers: buildHeaders(options, true),
      body: JSON.stringify(request),
    });
    return handleResponse<IngestWebsitesResponse>(response);
  },

  /**
   * Delete document and purge its vector chunks.
   */
  async deleteDocument(
    documentId: string,
    options?: RequestOptions
  ): Promise<DeleteDocumentResponse> {
    const response = await fetch(
      `${API_BASE_URL}/api/knowledge/documents/${encodeURIComponent(documentId)}`,
      {
        method: "DELETE",
        headers: buildHeaders(options, false),
      }
    );
    return handleResponse<DeleteDocumentResponse>(response);
  },

  /**
   * Trigger full reindexing of registered sources.
   */
  async reindexSources(options?: RequestOptions): Promise<ReindexResponse> {
    const response = await fetch(`${API_BASE_URL}/api/knowledge/reindex`, {
      method: "POST",
      headers: buildHeaders(options, false),
    });
    return handleResponse<ReindexResponse>(response);
  },
};
