import React, { useState, useEffect } from "react";
import { KnowledgeBase as KnowledgeBaseType } from "../types/knowledgeBase";
import {
  listKnowledgeBases,
  createKnowledgeBase,
  deleteKnowledgeBase,
} from "../utils/api";
import CreateKnowledgeBaseModal from "../components/knowledgebase/CreateKnowledgeBaseModal";
import KnowledgeBaseCard from "../components/knowledgebase/KnowledgeBaseCard";
import KnowledgeBaseDetails from "../components/knowledgebase/KnowledgeBaseDetails";

const KnowledgeBase: React.FC = () => {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [selectedKbId, setSelectedKbId] = useState<string | null>(null);

  const loadKnowledgeBases = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await listKnowledgeBases();
      setKnowledgeBases(data.knowledgeBases);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load knowledge bases"
      );
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadKnowledgeBases();
  }, []);

  const handleCreateKnowledgeBase = async (data: {
    name: string;
    description: string;
    embeddingModel: string;
  }) => {
    await createKnowledgeBase(data);
    await loadKnowledgeBases();
  };

  const handleDeleteKnowledgeBase = async (kbId: string, kbName: string) => {
    if (
      !confirm(
        `Are you sure you want to delete "${kbName}"? This will delete all documents and cannot be undone.`
      )
    ) {
      return;
    }

    try {
      await deleteKnowledgeBase(kbId);
      await loadKnowledgeBases();
    } catch (err) {
      alert(
        err instanceof Error ? err.message : "Failed to delete knowledge base"
      );
    }
  };

  if (selectedKbId) {
    return (
      <KnowledgeBaseDetails
        kbId={selectedKbId}
        onBack={() => {
          setSelectedKbId(null);
          loadKnowledgeBases();
        }}
      />
    );
  }

  return (
    <div className="px-4 py-6 sm:px-6 lg:px-8">
      <div className="mb-6 sm:mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-gray-900 mb-2">
              Knowledge Bases
            </h1>
            <p className="text-sm sm:text-base text-gray-600">
              Create and manage AI-powered knowledge bases for H&S documentation
            </p>
          </div>
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="flex items-center px-4 py-2 bg-primary-500 text-white rounded-md hover:bg-primary-600 transition-colors font-medium"
          >
            <svg
              className="w-5 h-5 mr-2"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 4v16m8-8H4"
              />
            </svg>
            Create New
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-red-600">{error}</p>
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
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
            <p className="mt-2 text-sm text-gray-600">Loading knowledge bases...</p>
          </div>
        </div>
      ) : knowledgeBases.length === 0 ? (
        <div className="bg-white border-2 border-dashed border-gray-300 rounded-lg p-12">
          <div className="text-center">
            <svg
              className="mx-auto h-12 w-12 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
              />
            </svg>
            <h3 className="mt-2 text-sm font-medium text-gray-900">
              No knowledge bases
            </h3>
            <p className="mt-1 text-sm text-gray-500">
              Get started by creating your first knowledge base
            </p>
            <div className="mt-6">
              <button
                onClick={() => setIsCreateModalOpen(true)}
                className="inline-flex items-center px-4 py-2 bg-primary-500 text-white rounded-md hover:bg-primary-600 transition-colors font-medium"
              >
                <svg
                  className="w-5 h-5 mr-2"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 4v16m8-8H4"
                  />
                </svg>
                Create Knowledge Base
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {knowledgeBases.map((kb) => (
            <KnowledgeBaseCard
              key={kb.kbId}
              kb={kb}
              onClick={() => setSelectedKbId(kb.kbId)}
              onDelete={() => handleDeleteKnowledgeBase(kb.kbId, kb.name)}
            />
          ))}
        </div>
      )}

      <CreateKnowledgeBaseModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onSubmit={handleCreateKnowledgeBase}
      />
    </div>
  );
};

export default KnowledgeBase;

