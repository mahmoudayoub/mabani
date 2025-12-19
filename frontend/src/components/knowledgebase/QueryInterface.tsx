import React, { useState, useRef, useEffect } from "react";
import { queryKnowledgeBase } from "../../utils/api";
import { ChatMessage } from "../../types/knowledgeBase";

interface QueryInterfaceProps {
  kbId: string;
  kbName: string;
  isReady: boolean;
}

const QueryInterface: React.FC<QueryInterfaceProps> = ({
  kbId,
  kbName,
  isReady,
}) => {
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isQuerying, setIsQuerying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modelId, setModelId] = useState("amazon.nova-lite-v1:0");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || isQuerying || !isReady) return;

    const userMessage: ChatMessage = {
      role: "user",
      content: query.trim(),
      timestamp: Date.now(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setQuery("");
    setIsQuerying(true);
    setError(null);

    try {
      const history = messages.map((msg) => ({
        role: msg.role,
        content: msg.content,
      }));

      const result = await queryKnowledgeBase(kbId, {
        query: userMessage.content,
        modelId,
        history,
        k: 5,
        config: {
          temperature: 0.7,
          maxTokens: 2048,
          topP: 0.9,
        },
      });

      const assistantMessage: ChatMessage = {
        role: "assistant",
        content: result.answer,
        sources: result.sources,
        timestamp: Date.now(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to query knowledge base");
    } finally {
      setIsQuerying(false);
    }
  };

  const handleClear = () => {
    setMessages([]);
    setError(null);
  };

  if (!isReady) {
    return (
      <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-6">
        <div className="text-center py-8">
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
              d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
            />
          </svg>
          <h3 className="mt-2 text-sm font-medium text-gray-900">
            Knowledge Base Not Ready
          </h3>
          <p className="mt-1 text-sm text-gray-500">
            Please upload and index documents before querying
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden flex flex-col" style={{ height: "600px" }}>
      <div className="px-6 py-4 border-b border-gray-200 bg-gradient-to-r from-primary-50 to-white">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">
              Query Knowledge Base
            </h3>
            <p className="text-sm text-gray-600">{kbName}</p>
          </div>
          <div className="flex items-center space-x-3">
            <select
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
              className="text-xs border border-gray-300 rounded-md py-1 px-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="amazon.nova-lite-v1:0">Nova Lite</option>
              <option value="amazon.nova-pro-v1:0">Nova Pro</option>
              <option value="anthropic.claude-3-sonnet-20240229-v1:0">
                Claude 3 Sonnet
              </option>
              <option value="anthropic.claude-3-haiku-20240307-v1:0">
                Claude 3 Haiku
              </option>
            </select>
            {messages.length > 0 && (
              <button
                onClick={handleClear}
                className="text-xs text-gray-600 hover:text-gray-900 font-medium"
              >
                Clear Chat
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-gray-50">
        {messages.length === 0 ? (
          <div className="text-center py-12">
            <svg
              className="mx-auto h-12 w-12 text-primary-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
              />
            </svg>
            <h4 className="mt-2 text-sm font-medium text-gray-900">
              Start a conversation
            </h4>
            <p className="mt-1 text-sm text-gray-500">
              Ask questions about your documents and get AI-powered answers
            </p>
          </div>
        ) : (
          messages.map((message, index) => (
            <div
              key={index}
              className={`flex ${message.role === "user" ? "justify-end" : "justify-start"
                }`}
            >
              <div
                className={`max-w-3xl rounded-lg px-4 py-3 ${message.role === "user"
                  ? "bg-primary-500 text-white"
                  : "bg-white border border-gray-200 text-gray-900"
                  }`}
              >
                <div className="flex items-start space-x-2">
                  {message.role === "assistant" && (
                    <svg
                      className="w-5 h-5 text-primary-600 mt-0.5 flex-shrink-0"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                      />
                    </svg>
                  )}
                  <div className="flex-1">
                    <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                    {message.role === "assistant" &&
                      message.sources &&
                      message.sources.length > 0 && (
                        <div className="mt-3 pt-3 border-t border-gray-100">
                          <p className="text-xs font-medium text-gray-500 mb-1">
                            Sources:
                          </p>
                          <ul className="space-y-1">
                            {(() => {
                              // Group sources by filename
                              const groupedSources: {
                                [key: string]: number[];
                              } = {};

                              message.sources!.forEach((source) => {
                                // Expected format: "Filename.ext (Page X)" or just "Filename.ext"
                                const match = source.match(/^(.*?) \(Page (\d+)\)$/);
                                if (match) {
                                  const filename = match[1];
                                  const page = parseInt(match[2]);
                                  if (!groupedSources[filename]) {
                                    groupedSources[filename] = [];
                                  }
                                  groupedSources[filename].push(page);
                                } else {
                                  // Handle sources without page numbers
                                  if (!groupedSources[source]) {
                                    groupedSources[source] = [];
                                  }
                                }
                              });

                              return Object.entries(groupedSources).map(
                                ([filename, pages], idx) => (
                                  <li
                                    key={idx}
                                    className="text-xs text-gray-500 flex items-start"
                                  >
                                    <span className="mr-1.5 mt-0.5 text-primary-400">
                                      •
                                    </span>
                                    <span>
                                      {filename}
                                      {pages.length > 0 && (
                                        <span className="text-gray-400 ml-1">
                                          (Page{" "}
                                          {pages
                                            .sort((a, b) => a - b)
                                            .join(", ")}
                                          )
                                        </span>
                                      )}
                                    </span>
                                  </li>
                                )
                              );
                            })()}
                          </ul>
                        </div>
                      )}
                    <p
                      className={`text-xs mt-1 ${message.role === "user"
                        ? "text-primary-100"
                        : "text-gray-500"
                        }`}
                    >
                      {new Date(message.timestamp).toLocaleTimeString()}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
        {isQuerying && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-200 rounded-lg px-4 py-3">
              <div className="flex items-center space-x-2">
                <div className="animate-pulse flex space-x-1">
                  <div className="w-2 h-2 bg-primary-500 rounded-full"></div>
                  <div className="w-2 h-2 bg-primary-500 rounded-full animation-delay-200"></div>
                  <div className="w-2 h-2 bg-primary-500 rounded-full animation-delay-400"></div>
                </div>
                <span className="text-sm text-gray-600">Thinking...</span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {
        error && (
          <div className="px-6 py-3 bg-red-50 border-t border-red-200">
            <p className="text-sm text-red-600">{error}</p>
          </div>
        )
      }

      <div className="px-6 py-4 border-t border-gray-200 bg-white">
        <form onSubmit={handleSubmit} className="flex space-x-3">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={isQuerying}
            placeholder="Ask a question about your documents..."
            className="flex-1 border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
          />
          <button
            type="submit"
            disabled={!query.trim() || isQuerying}
            className="px-6 py-2 bg-primary-500 text-white rounded-lg font-medium hover:bg-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isQuerying ? (
              <svg
                className="animate-spin h-5 w-5"
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
            ) : (
              "Send"
            )}
          </button>
        </form>
      </div>
    </div >
  );
};

export default QueryInterface;

