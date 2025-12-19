import { fetchAuthSession } from "aws-amplify/auth";
import { KnowledgeBase, Document, QueryResult } from "../types/knowledgeBase";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:3001";

export async function getAuthHeaders() {

  try {
    const session = await fetchAuthSession();
    const token = session.tokens?.idToken?.toString();
    if (!token) {
      throw new Error("No authentication token available");
    }
    return {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    };
  } catch (error) {
    console.error("Error getting auth headers:", error);
    throw error;
  }
}

// Knowledge Base APIs
export async function listKnowledgeBases(): Promise<{
  knowledgeBases: KnowledgeBase[];
  total: number;
}> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/knowledge-bases`, {
    method: "GET",
    headers,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || "Failed to list knowledge bases");
  }

  return response.json();
}

export async function getKnowledgeBase(kbId: string): Promise<KnowledgeBase> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/knowledge-bases/${kbId}`, {
    method: "GET",
    headers,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || "Failed to get knowledge base");
  }

  return response.json();
}

export async function createKnowledgeBase(data: {
  name: string;
  description?: string;
  embeddingModel?: string;
}): Promise<KnowledgeBase> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/knowledge-bases`, {
    method: "POST",
    headers,
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || "Failed to create knowledge base");
  }

  return response.json();
}

export async function updateKnowledgeBase(
  kbId: string,
  data: { name?: string; description?: string }
): Promise<KnowledgeBase> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/knowledge-bases/${kbId}`, {
    method: "PUT",
    headers,
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || "Failed to update knowledge base");
  }

  return response.json();
}

export async function deleteKnowledgeBase(kbId: string): Promise<void> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/knowledge-bases/${kbId}`, {
    method: "DELETE",
    headers,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || "Failed to delete knowledge base");
  }
}

// Document APIs
export async function generateUploadUrl(
  kbId: string,
  data: { filename: string; fileType: string; fileSize: number }
): Promise<{
  uploadUrl: string;
  documentId: string;
  s3Key: string;
  filename: string;
  fileType: string;
  fileSize: number;
}> {
  const headers = await getAuthHeaders();
  const response = await fetch(
    `${API_BASE_URL}/knowledge-bases/${kbId}/upload-url`,
    {
      method: "POST",
      headers,
      body: JSON.stringify(data),
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || "Failed to generate upload URL");
  }

  return response.json();
}

export async function uploadFileToS3(
  uploadUrl: string,
  file: File,
  fileType: string
): Promise<void> {
  const mimeTypes: { [key: string]: string } = {
    pdf: "application/pdf",
    txt: "text/plain",
    docx:
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    doc: "application/msword",
  };

  const contentType =
    mimeTypes[fileType] || `application/${fileType}`;

  const response = await fetch(uploadUrl, {
    method: "PUT",
    headers: {
      "Content-Type": contentType,
    },
    body: file,
  });

  if (!response.ok) {
    throw new Error("Failed to upload file to S3");
  }
}

export async function confirmDocumentUpload(
  kbId: string,
  data: {
    documentId: string;
    s3Key: string;
    filename: string;
    fileType: string;
    fileSize: number;
  }
): Promise<{ message: string; document: Document }> {
  const headers = await getAuthHeaders();
  const response = await fetch(
    `${API_BASE_URL}/knowledge-bases/${kbId}/documents`,
    {
      method: "POST",
      headers,
      body: JSON.stringify(data),
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || "Failed to confirm document upload");
  }

  return response.json();
}

export async function listDocuments(
  kbId: string,
  limit = 50
): Promise<{ documents: Document[]; count: number; lastKey: null }> {
  const headers = await getAuthHeaders();
  const response = await fetch(
    `${API_BASE_URL}/knowledge-bases/${kbId}/documents?limit=${limit}`,
    {
      method: "GET",
      headers,
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || "Failed to list documents");
  }

  return response.json();
}

export async function deleteDocument(
  kbId: string,
  documentId: string
): Promise<void> {
  const headers = await getAuthHeaders();
  const response = await fetch(
    `${API_BASE_URL}/knowledge-bases/${kbId}/documents/${documentId}`,
    {
      method: "DELETE",
      headers,
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || "Failed to delete document");
  }
}

// Query API
export async function queryKnowledgeBase(
  kbId: string,
  data: {
    query: string;
    modelId: string;
    history?: { role: string; content: string }[];
    k?: number;
    config?: {
      temperature?: number;
      maxTokens?: number;
      topP?: number;
    };
    distanceThreshold?: number;
  }
): Promise<QueryResult> {
  const headers = await getAuthHeaders();
  const response = await fetch(
    `${API_BASE_URL}/knowledge-bases/${kbId}/query`,
    {
      method: "POST",
      headers,
      body: JSON.stringify(data),
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || "Failed to query knowledge base");
  }

  return response.json();
}

