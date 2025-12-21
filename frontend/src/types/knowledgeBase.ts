export interface KnowledgeBase {
  kbId: string;
  userId: string;
  name: string;
  description?: string;
  embeddingModel: string;
  documentCount: number;
  totalSize: number;
  indexStatus: "empty" | "processing" | "ready" | "error";
  createdAt: number;
  updatedAt: number;
  shared?: boolean;
  permission?: string;
}

export interface Document {
  documentId: string;
  kbId: string;
  filename: string;
  fileType: string;
  fileSize: number;
  s3Key: string;
  status: "pending" | "processing" | "indexed" | "failed";
  uploadedAt: number;
  indexedAt?: number;
  errorMessage?: string;
  extractionMethod?: string;
}

export interface QueryResult {
  answer: string;
  sources: string[];
  retrievedChunks: number;
  query: string;
  modelId: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: string[];
  timestamp: number;
}

