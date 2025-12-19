import React, { useState, useMemo } from "react";
import {
  generateUploadUrl,
  uploadFileToS3,
  confirmDocumentUpload,
} from "../../utils/api";

interface DocumentUploadProps {
  kbId: string;
  onUploadComplete: () => void;
}

interface FileStatus {
  file: File;
  id: string; // unique internal id for list rendering
  status: "pending" | "uploading" | "success" | "error";
  progress: number;
  errorMessage?: string;
}

const DocumentUpload: React.FC<DocumentUploadProps> = ({
  kbId,
  onUploadComplete,
}) => {
  const [files, setFiles] = useState<FileStatus[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [globalError, setGlobalError] = useState<string | null>(null);

  const supportedFileTypes = ["pdf", "txt", "docx", "doc"];

  // Calculate global progress
  const globalProgress = useMemo(() => {
    if (files.length === 0) return 0;
    const totalProgress = files.reduce((acc, curr) => acc + curr.progress, 0);
    return Math.round(totalProgress / files.length);
  }, [files]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = e.target.files;
    if (!selectedFiles || selectedFiles.length === 0) return;

    const newFiles: FileStatus[] = [];
    let errorMsg = null;

    Array.from(selectedFiles).forEach((file) => {
      const fileExtension = file.name.split(".").pop()?.toLowerCase();
      if (fileExtension && supportedFileTypes.includes(fileExtension)) {
        newFiles.push({
          file,
          id: Math.random().toString(36).substr(2, 9),
          status: "pending", // Initially pending
          progress: 0,
        });
      } else {
        errorMsg = `Some files were skipped. Supported types: ${supportedFileTypes.join(
          ", "
        )}`;
      }
    });

    if (errorMsg) {
      setGlobalError(errorMsg);
    } else {
      setGlobalError(null);
    }

    setFiles((prev) => [...prev, ...newFiles]);

    // Reset input
    e.target.value = "";
  };

  const removeFile = (id: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== id));
  };

  const uploadSingleFile = async (fileStatus: FileStatus) => {
    try {
      const file = fileStatus.file;
      const fileExtension =
        file.name.split(".").pop()?.toLowerCase() || "";

      // Step 1: Generate upload URL
      updateFileStatus(fileStatus.id, {
        status: "uploading",
        progress: 10,
        errorMessage: undefined,
      });

      const uploadData = await generateUploadUrl(kbId, {
        filename: file.name,
        fileType: fileExtension,
        fileSize: file.size,
      });

      // Step 2: Upload file to S3
      updateFileStatus(fileStatus.id, { progress: 40 });
      await uploadFileToS3(uploadData.uploadUrl, file, fileExtension);

      // Step 3: Confirm upload
      updateFileStatus(fileStatus.id, { progress: 80 });
      await confirmDocumentUpload(kbId, {
        documentId: uploadData.documentId,
        s3Key: uploadData.s3Key,
        filename: uploadData.filename,
        fileType: uploadData.fileType,
        fileSize: uploadData.fileSize,
      });

      updateFileStatus(fileStatus.id, { status: "success", progress: 100 });
      return true;
    } catch (err) {
      updateFileStatus(fileStatus.id, {
        status: "error",
        errorMessage:
          err instanceof Error ? err.message : "Failed to upload",
        progress: 100, // Mark as 100% complete (even if failed) for global progress
      });
      return false;
    }
  };

  const updateFileStatus = (id: string, updates: Partial<FileStatus>) => {
    setFiles((prev) =>
      prev.map((f) => (f.id === id ? { ...f, ...updates } : f))
    );
  };

  const handleUploadAll = async () => {
    const pendingFiles = files.filter(
      (f) => f.status === "pending" || f.status === "error"
    );
    if (pendingFiles.length === 0) return;

    setIsUploading(true);
    setGlobalError(null);

    try {
      // Execute uploads in parallel
      await Promise.all(pendingFiles.map((f) => uploadSingleFile(f)));

      onUploadComplete();

    } catch (err) {
      setGlobalError("An error occurred during the batch upload process.");
    } finally {
      setIsUploading(false);
    }
  };

  const clearCompleted = () => {
    setFiles((prev) => prev.filter((f) => f.status !== "success"));
  };

  const hasPendingFiles = files.some(
    (f) => f.status === "pending" || f.status === "error"
  );

  const hasSuccessFiles = files.some((f) => f.status === "success");

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">
        Upload Documents
      </h3>

      <div className="space-y-4">
        {/* File Drop / Select Area */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={(e) => {
            e.preventDefault();
            setIsDragging(false);
          }}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragging(false);
            const droppedFiles = e.dataTransfer.files;
            if (droppedFiles && droppedFiles.length > 0) {
              const newFiles: FileStatus[] = [];
              let errorMsg = null;

              Array.from(droppedFiles).forEach((file) => {
                const fileExtension = file.name.split(".").pop()?.toLowerCase();
                if (
                  fileExtension &&
                  supportedFileTypes.includes(fileExtension)
                ) {
                  newFiles.push({
                    file,
                    id: Math.random().toString(36).substr(2, 9),
                    status: "pending",
                    progress: 0,
                  });
                } else {
                  errorMsg = `Some files were skipped. Supported types: ${supportedFileTypes.join(
                    ", "
                  )}`;
                }
              });

              if (errorMsg) {
                setGlobalError(errorMsg);
              } else {
                setGlobalError(null);
              }

              setFiles((prev) => [...prev, ...newFiles]);
            }
          }}
          className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${isDragging
            ? "border-primary-500 bg-primary-50"
            : "border-gray-300 hover:bg-gray-50"
            }`}
        >
          <input
            id="file-upload"
            type="file"
            multiple
            onChange={handleFileSelect}
            disabled={isUploading}
            accept=".pdf,.txt,.doc,.docx"
            className="hidden"
          />
          <label
            htmlFor="file-upload"
            className={`cursor-pointer flex flex-col items-center justify-center space-y-2 ${isUploading ? "opacity-50 cursor-not-allowed" : ""
              }`}
          >
            <svg
              className="w-10 h-10 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
              />
            </svg>
            <span className="text-sm font-medium text-primary-600 hover:text-primary-700">
              Click to select files or drag and drop
            </span>
            <span className="text-xs text-gray-500">
              PDF, TXT, DOC, DOCX (Max 100MB)
            </span>
          </label>
        </div>

        {globalError && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-md">
            <p className="text-sm text-red-600">{globalError}</p>
          </div>
        )}

        {/* Global Progress Bar */}
        {isUploading && (
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-gray-600">
              <span>Uploading {files.length} files...</span>
              <span>{globalProgress}%</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
              <div
                className="bg-primary-500 h-2 rounded-full transition-all duration-300"
                style={{ width: `${globalProgress}%` }}
              />
            </div>
          </div>
        )}

        {/* File List */}
        {files.length > 0 && (
          <div className="space-y-3 mt-4 max-h-60 overflow-y-auto">
            {files.map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between p-3 bg-gray-50 rounded-md"
              >
                <div className="flex items-center space-x-3 flex-1 min-w-0">
                  <div className="flex-shrink-0">
                    {/* Status Icons */}
                    {item.status === "success" && (
                      <svg
                        className="w-5 h-5 text-green-500"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M5 13l4 4L19 7"
                        />
                      </svg>
                    )}
                    {item.status === "error" && (
                      <svg
                        className="w-5 h-5 text-red-500"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                        />
                      </svg>
                    )}
                    {(item.status === "pending" || item.status === "uploading") && (
                      <svg
                        className="w-5 h-5 text-gray-400"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                        />
                      </svg>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {item.file.name}
                    </p>
                    <div className="flex items-center text-xs text-gray-500 space-x-2">
                      <span>{(item.file.size / 1024 / 1024).toFixed(2)} MB</span>
                      {item.status === 'error' && (
                        <span className="text-red-500 font-medium"> - {item.errorMessage}</span>
                      )}
                      {item.status === 'success' && (
                        <span className="text-green-600 font-medium"> - Uploaded</span>
                      )}
                    </div>
                  </div>
                </div>

                {item.status !== "uploading" && (
                  <button
                    onClick={() => removeFile(item.id)}
                    className="ml-2 p-1 text-gray-400 hover:text-red-500 transition-colors"
                  >
                    <svg
                      className="w-5 h-5"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M6 18L18 6M6 6l12 12"
                      />
                    </svg>
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Action Buttons */}
        {files.length > 0 && !isUploading && (
          <div className="flex space-x-3 pt-2">
            {hasPendingFiles && (
              <button
                onClick={handleUploadAll}
                className="flex-1 px-4 py-2 bg-primary-500 text-white rounded-md text-sm font-medium hover:bg-primary-600 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
              >
                Upload {files.length} Files
              </button>
            )}

            {hasSuccessFiles && (
              <button
                onClick={clearCompleted}
                className="px-4 py-2 bg-gray-100 text-gray-700 rounded-md text-sm font-medium hover:bg-gray-200"
              >
                Clear Completed
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default DocumentUpload;
