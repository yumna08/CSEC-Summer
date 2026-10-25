export type SourceType = "webpage" | "pdf" | "docx" | "txt" | string;

export type VerificationStatus = "verified" | "candidate" | "unverified" | "failed" | string;

export interface DocumentMetadata {
  doc_id: string;
  source_url: string | null;
  source_title: string;
  source_type: SourceType;
  document_name: string;
  content_hash: string;
  fetched_at: string;
  academic_year: string | null;
  publication_date: string | null;
  verification_status: VerificationStatus;
  chunk_count: number;
  requires_ocr: boolean;
  error_message: string | null;
}

export interface DocumentListResponse {
  total: number;
  documents: DocumentMetadata[];
}

export interface SourceRegistryItem {
  url: string;
  title: string;
  description?: string;
  verification_status: string;
  added_at?: string;
  last_checked?: string | null;
  last_status?: string;
  error_message?: string | null;
}

export interface SourcesResponse {
  sources: SourceRegistryItem[];
}

export interface IngestResult {
  doc_id?: string | null;
  source_url?: string | null;
  document_name: string;
  status: "indexed" | "unchanged" | "scanned_requires_ocr" | "failed" | string;
  chunk_count: number;
  message: string;
}

export interface IngestUrlRequest {
  url: string;
  source_title?: string;
  verification_status?: string;
}

export interface IngestWebsitesRequest {
  urls?: string[];
  discover_pdfs?: boolean;
  max_pages?: number;
}

export interface IngestWebsitesResponse {
  total_attempted: number;
  successful: number;
  unchanged: number;
  failed: number;
  requires_ocr: number;
  results: IngestResult[];
}

export interface DeleteDocumentResponse {
  doc_id: string;
  deleted_chunks: number;
  message: string;
}

export interface ReindexResponse {
  total_reindexed: number;
  results: IngestResult[];
}

export interface OverviewStats {
  totalDocuments: number;
  verifiedDocuments: number;
  candidateDocuments: number;
  failedSources: number;
  totalChunks: number;
  requiresOcrCount: number;
}

export interface NotificationState {
  type: "success" | "error" | "info";
  message: string;
  details?: string;
}
