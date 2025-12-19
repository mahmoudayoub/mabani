import React, { useState, useEffect, useRef } from "react";
import { KnowledgeBase, Document } from "../../types/knowledgeBase";
import {
  getKnowledgeBase,
  listDocuments,
  deleteDocument,
} from "../../utils/api";
import DocumentUpload from "./DocumentUpload";
import DocumentList from "./DocumentList";
import QueryInterface from "./QueryInterface";

interface KnowledgeBaseDetailsProps {
  kbId: string;
  onBack: () => void;
}

const KnowledgeBaseDetails: React.FC<KnowledgeBaseDetailsProps> = ({
  kbId,
  onBack,
}) => {
  const [kb, setKb] = useState<KnowledgeBase | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [activeTab, setActiveTab] = useState<"documents" | "query">(
    "documents"
  );
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingDocId, setDeletingDocId] = useState<string | null>(null);
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const loadKnowledgeBase = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const [kbData, docsData] = await Promise.all([
        getKnowledgeBase(kbId),
        listDocuments(kbId),
      ]);
      setKb(kbData);
      setDocuments(docsData.documents);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load knowledge base"
      );
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadKnowledgeBase();
  }, [kbId]);

  // Poll for document status updates when there are processing documents
  useEffect(() => {
    // Clear any existing polling interval
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }

    const hasProcessingDocuments = documents.some(
      (doc) => doc.status === "processing" || doc.status === "pending"
    );

    if (!hasProcessingDocuments) return;

    let pollCount = 0;
    const maxPolls = 60; // Poll for up to 3 minutes (60 * 3 seconds)

    const pollInterval = setInterval(async () => {
      pollCount++;

      // Stop polling after max attempts
      if (pollCount > maxPolls) {
        clearInterval(pollInterval);
        pollingIntervalRef.current = null;
        return;
      }

      try {
        const docsData = await listDocuments(kbId);
        const stillProcessing = docsData.documents.some(
          (doc) => doc.status === "processing" || doc.status === "pending"
        );

        setDocuments(docsData.documents);

        // Also refresh KB to update document count and index status
        const kbData = await getKnowledgeBase(kbId);
        setKb(kbData);

        // Stop polling if no processing documents remain
        if (!stillProcessing) {
          clearInterval(pollInterval);
          pollingIntervalRef.current = null;
        }
      } catch (err) {
        console.error("Error polling document status:", err);
        // Continue polling even on error
      }
    }, 3000); // Poll every 3 seconds

    pollingIntervalRef.current = pollInterval;

    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    };
  }, [documents, kbId]);

  const handleDocumentDelete = async (documentId: string) => {
    if (!confirm("Are you sure you want to delete this document?")) return;

    setDeletingDocId(documentId);
    try {
      await deleteDocument(kbId, documentId);
      await loadKnowledgeBase();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete document");
    } finally {
      setDeletingDocId(null);
    }
  };

  const handleUploadComplete = () => {
    loadKnowledgeBase();
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <svg
            className="animate-spin h-8 w-8 text-primary-500 mx-auto"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
          <p className="mt-2 text-sm text-gray-600">Loading...</p>
        </div>
      </div>
    );
  }

  if (error || !kb) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-6">
        <button
          onClick={onBack}
          className="mb-4 text-primary-600 hover:text-primary-700 font-medium flex items-center"
        >
          <svg
            className="w-5 h-5 mr-1"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15 19l-7-7 7-7"
            />
          </svg>
          Back
        </button>
        <div className="bg-red-50 border border-red-200 rounded-lg p-6">
          <p className="text-red-600">{error || "Knowledge base not found"}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <button
        onClick={onBack}
        className="mb-4 text-primary-600 hover:text-primary-700 font-medium flex items-center"
      >
        <svg
          className="w-5 h-5 mr-1"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M15 19l-7-7 7-7"
          />
        </svg>
        Back
      </button>

      <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-6 mb-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{kb.name}</h1>
            {kb.description && (
              <p className="mt-2 text-gray-600">{kb.description}</p>
            )}
            <div className="mt-4 flex items-center space-x-4 text-sm text-gray-600">
              <span className="flex items-center">
                <svg
                  className="w-4 h-4 mr-1"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
                  />
                </svg>
                {kb.documentCount} documents
              </span>
              <span className="flex items-center">
                <svg
                  className="w-4 h-4 mr-1"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M13 10V3L4 14h7v7l9-11h-7z"
                  />
                </svg>
                {kb.embeddingModel}
              </span>
            </div>
          </div>
          <span
            className={`px-3 py-1 rounded-full text-sm font-medium ${
              kb.indexStatus === "ready"
                ? "bg-green-100 text-green-800"
                : kb.indexStatus === "processing"
                ? "bg-yellow-100 text-yellow-800"
                : kb.indexStatus === "error"
                ? "bg-red-100 text-red-800"
                : "bg-gray-100 text-gray-800"
            }`}
          >
            {kb.indexStatus}
          </span>
        </div>
      </div>

      <div className="mb-6">
        <div className="border-b border-gray-200">
          <nav className="flex space-x-8">
            <button
              onClick={() => setActiveTab("documents")}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === "documents"
                  ? "border-primary-500 text-primary-600"
                  : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
              }`}
            >
              Documents
            </button>
            <button
              onClick={() => setActiveTab("query")}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === "query"
                  ? "border-primary-500 text-primary-600"
                  : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
              }`}
            >
              Query
            </button>
          </nav>
        </div>
      </div>

      {activeTab === "documents" ? (
        <div className="space-y-6">
          <DocumentUpload kbId={kbId} onUploadComplete={handleUploadComplete} />
          <DocumentList
            documents={documents}
            onDelete={handleDocumentDelete}
            isDeleting={deletingDocId}
          />
        </div>
      ) : (
        <QueryInterface
          kbId={kbId}
          kbName={kb.name}
          isReady={kb.indexStatus === "ready"}
        />
      )}
    </div>
  );
};

export default KnowledgeBaseDetails;
