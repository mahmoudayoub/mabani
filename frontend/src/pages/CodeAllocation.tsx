import React, { useState, useEffect, useRef } from 'react';
import {
    uploadPriceCodeFile,
    getPriceCodeStatus,
    getPriceCodeDownloadUrl,
    listAvailablePriceCodes,
    listPriceCodeOutputFiles,
    listActivePriceCodeJobs,
    deletePriceCodeEstimate,
    fetchTextContent,
    PriceCodeEstimate,
    PriceCodeOutputFile
} from '../services/priceCodeService';

type Mode = 'index' | 'allocate';

interface PriceCodeSummary {
    fileInfo: {
        inputFile: string;
        outputFile: string;
        sheet: string;
        generated: string;
        processingTime: string;
    };
    stats: {
        totalItems: number;
        matched: number;
        notMatched: number;
        errors: number;
        matchRate: string;
    };
}

const parsePriceCodeSummary = (text: string): PriceCodeSummary | null => {
    try {
        const lines = text.split('\n').map(l => l.trim());
        const summary: any = { fileInfo: {}, stats: {} };
        let currentSection = '';

        lines.forEach(line => {
            if (line.includes('FILE INFORMATION')) currentSection = 'info';
            else if (line.includes('PROCESSING STATISTICS')) currentSection = 'stats';
            else if (line.includes(':')) {
                const [key, ...values] = line.split(':');
                const value = values.join(':').trim();
                const cleanKey = key.trim().toLowerCase();

                if (currentSection === 'info') {
                    if (cleanKey === 'input file') summary.fileInfo.inputFile = value;
                    else if (cleanKey === 'output file') summary.fileInfo.outputFile = value;
                    else if (cleanKey === 'sheet') summary.fileInfo.sheet = value;
                    else if (cleanKey === 'generated') summary.fileInfo.generated = value;
                    else if (cleanKey === 'processing time') summary.fileInfo.processingTime = value;
                } else if (currentSection === 'stats') {
                    if (cleanKey === 'total items') summary.stats.totalItems = parseInt(value) || 0;
                    else if (cleanKey === 'matched') summary.stats.matched = parseInt(value) || 0;
                    else if (cleanKey === 'not matched') summary.stats.notMatched = parseInt(value) || 0;
                    else if (cleanKey === 'errors') summary.stats.errors = parseInt(value) || 0;
                    else if (cleanKey === 'match rate') summary.stats.matchRate = value;
                }
            }
        });

        // Basic validation
        if (!summary.stats.totalItems && !summary.fileInfo.inputFile) return null;

        return summary as PriceCodeSummary;
    } catch (e) {
        console.error('Failed to parse summary:', e);
        return null;
    }
};

const CodeAllocation: React.FC = () => {
    // View State
    const [currentView, setCurrentView] = useState<'landing' | 'allocate' | 'index'>('landing');
    // Mode Toggle
    const [currentMode, setCurrentMode] = useState<Mode>('allocate');

    // File Upload State
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [isUploading, setIsUploading] = useState(false);
    const [uploadError, setUploadError] = useState<string | null>(null);

    // Processing State
    const [isProcessing, setIsProcessing] = useState(false);
    const [progressPercent, setProgressPercent] = useState(0);
    const [processingStatus, setProcessingStatus] = useState('');
    const [timeRemaining, setTimeRemaining] = useState('');
    const [estimateData, setEstimateData] = useState<PriceCodeEstimate | null>(null);

    // Completion State
    const [completedFilePath, setCompletedFilePath] = useState<string | null>(null);
    const [resultData, setResultData] = useState<{ matched: number; not_matched: number; match_rate: number } | null>(null);
    const [showSummary, setShowSummary] = useState(false);
    const [viewContent, setViewContent] = useState<string | null>(null);
    const [viewSummaryData, setViewSummaryData] = useState<PriceCodeSummary | null>(null);
    const [viewTitle, setViewTitle] = useState<string>('');

    const handleViewSummary = async (file: PriceCodeOutputFile) => {
        try {
            const text = await fetchTextContent(file.downloadUrl);
            const parsed = parsePriceCodeSummary(text);

            if (parsed) {
                setViewSummaryData(parsed);
                setViewTitle('Allocation Summary');
                setViewContent(null);
            } else {
                setViewContent(text);
                setViewSummaryData(null);
                setViewTitle(file.filename);
            }
            setShowSummary(true); // Ensure modal opens
        } catch (error) {
            console.error('Failed to view file:', error);
            alert('Failed to view file content.');
        }
    };

    // Available Price Codes (for allocation mode)
    const [availableCodes, setAvailableCodes] = useState<string[]>([]);
    const [loadingCodes, setLoadingCodes] = useState(false);
    const [selectedCodes, setSelectedCodes] = useState<string[]>([]);
    const [showCodePicker, setShowCodePicker] = useState(false);

    // Output Files State
    const [outputFiles, setOutputFiles] = useState<PriceCodeOutputFile[]>([]);
    const [loadingOutputFiles, setLoadingOutputFiles] = useState(false);

    // Refs for intervals
    const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
    const progressIntervalRef = useRef<NodeJS.Timeout | null>(null);

    // Load available price codes on mount
    useEffect(() => {
        const fetchCodes = async () => {
            setLoadingCodes(true);
            try {
                const codes = await listAvailablePriceCodes();
                setAvailableCodes(codes);
            } catch (error) {
                console.error('Failed to fetch price codes:', error);
            } finally {
                setLoadingCodes(false);
            }
        };
        fetchCodes();
    }, []);

    // Check for active jobs on mount (for persistence)
    useEffect(() => {
        const checkActiveJobs = async () => {
            try {
                const activeJobs = await listActivePriceCodeJobs();

                if (activeJobs.length > 0) {
                    const job = activeJobs[0];
                    console.log('Found active price code job:', job);

                    // Switch to allocate mode
                    setCurrentMode('allocate');
                    setCurrentView('allocate');
                    setIsProcessing(true);
                    setEstimateData(job);
                    setProcessingStatus('Resuming processing...');

                    // Calculate elapsed time
                    // IMPORTANT: started_at is UTC, append 'Z' to parse correctly
                    const startTime = new Date(job.started_at + 'Z').getTime();
                    const elapsed = (Date.now() - startTime) / 1000;

                    // Calculate initial progress
                    const initialProgress = Math.min((elapsed / job.estimated_seconds) * 100, 95);
                    setProgressPercent(initialProgress);
                    setProcessingStatus(initialProgress >= 95 ? 'Finalizing...' : 'Processing...');

                    // Continue animating progress from current point
                    let currentProgress = initialProgress;
                    const updateIntervalMs = 500;
                    const progressIncrement = (100 / job.estimated_seconds) * (updateIntervalMs / 1000);

                    // Clear any existing interval
                    if (progressIntervalRef.current) clearInterval(progressIntervalRef.current);

                    progressIntervalRef.current = setInterval(() => {
                        currentProgress += progressIncrement;

                        if (currentProgress >= 95) {
                            currentProgress = 95;
                            setProcessingStatus('Finalizing...');
                        }

                        setProgressPercent(Math.min(currentProgress, 95));

                        // Update time remaining
                        const newElapsed = (Date.now() - startTime) / 1000;
                        const remaining = Math.max(0, job.estimated_seconds - newElapsed);

                        if (remaining > 60) {
                            setTimeRemaining(`~${Math.ceil(remaining / 60)} min remaining`);
                        } else {
                            setTimeRemaining(`${Math.ceil(remaining)} sec remaining`);
                        }
                    }, updateIntervalMs);

                    // Start polling for completion
                    startPolling(job.filename);
                }
            } catch (error) {
                console.error('Failed to check active jobs:', error);
            }
        };

        checkActiveJobs();
    }, []);

    // Load output files on mount
    useEffect(() => {
        const fetchOutputFiles = async () => {
            setLoadingOutputFiles(true);
            try {
                const files = await listPriceCodeOutputFiles();
                setOutputFiles(files);
            } catch (error) {
                console.error('Failed to load output files:', error);
            } finally {
                setLoadingOutputFiles(false);
            }
        };
        fetchOutputFiles();
    }, []);

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            if (!file.name.endsWith('.xlsx')) {
                setUploadError('Please select an Excel (.xlsx) file');
                return;
            }
            setSelectedFile(file);
            setUploadError(null);
        }
    };

    const handleUpload = async () => {
        if (!selectedFile) return;

        setIsUploading(true);
        setUploadError(null);

        try {
            // Upload file with selected codes as source-files metadata
            await uploadPriceCodeFile(
                selectedFile,
                currentMode,
                currentMode === 'allocate' ? selectedCodes : undefined
            );

            if (currentMode === 'allocate') {
                // Start processing for allocate mode
                setIsProcessing(true);
                setProcessingStatus('Processing started...');

                // Start polling for status
                startPolling(selectedFile.name);
                startProgressAnimation();
            } else {
                // Index mode - just show success
                setProcessingStatus('File uploaded for indexing. Processing will begin shortly.');
                setTimeout(() => {
                    setProcessingStatus('');
                    listAvailablePriceCodes().then(codes => setAvailableCodes(codes));
                }, 3000);
            }

            setSelectedFile(null);
        } catch (error) {
            console.error('Upload failed:', error);
            setUploadError(`Upload failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
        } finally {
            setIsUploading(false);
        }
    };

    const startPolling = (filename: string) => {
        const filenameBase = filename.replace('.xlsx', '');

        pollIntervalRef.current = setInterval(async () => {
            try {
                const status = await getPriceCodeStatus(filename);

                console.log('[Polling] Status:', status);

                if (status.complete) {
                    console.log('[Worker] Completion signal received:', status);
                    cleanupProgressTracking();

                    if (status.success) {
                        setProgressPercent(100);
                        setProcessingStatus('Complete!');
                        setCompletedFilePath(`output/pricecode/fills/${filenameBase}_pricecode.xlsx`);
                        setTimeRemaining('');
                        setResultData(status.result || null);

                        // Delete estimate file
                        try {
                            await deletePriceCodeEstimate(filename);
                            console.log('Estimate file deleted');
                        } catch (err) {
                            console.error('Failed to delete estimate:', err);
                        }

                        // Refresh file list
                        try {
                            const files = await listPriceCodeOutputFiles();
                            setOutputFiles(files);
                        } catch (err) {
                            console.error('Failed to refresh file list:', err);
                        }
                    } else {
                        setIsProcessing(false);
                        setProcessingStatus(`Failed: ${status.error || 'Unknown error'}`);
                        setProgressPercent(0);

                        try {
                            await deletePriceCodeEstimate(filename);
                        } catch (err) {
                            console.error('Failed to delete estimate:', err);
                        }
                    }
                    return;
                } else {
                    // Update estimate data for progress calculation
                    setEstimateData(status);
                }
            } catch (error) {
                // Estimate not found yet - worker hasn't created it
                console.log('[Polling] Waiting for estimate file...');
            }
        }, 3000);
    };

    const startProgressAnimation = () => {
        const startTime = Date.now();

        progressIntervalRef.current = setInterval(() => {
            if (!estimateData?.estimated_seconds) return;

            const elapsed = (Date.now() - startTime) / 1000;
            const progress = Math.min((elapsed / estimateData.estimated_seconds) * 95, 95);

            setProgressPercent(Math.round(progress));

            const remaining = Math.max(0, estimateData.estimated_seconds - elapsed);
            if (remaining > 60) {
                setTimeRemaining(`~${Math.ceil(remaining / 60)} min remaining`);
            } else {
                setTimeRemaining(`~${Math.ceil(remaining)} sec remaining`);
            }
        }, 1000);
    };

    const cleanupProgressTracking = () => {
        if (progressIntervalRef.current) {
            clearInterval(progressIntervalRef.current);
            progressIntervalRef.current = null;
        }
        if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
        }
    };

    const handleDownload = async () => {
        if (!completedFilePath) return;

        try {
            const filename = completedFilePath.split('/').pop() || 'output.xlsx';
            const { url } = await getPriceCodeDownloadUrl(filename);
            window.open(url, '_blank');
        } catch (error) {
            console.error('Download failed:', error);
        }
    };

    const handleCodeToggle = (code: string, checked: boolean) => {
        if (checked) {
            setSelectedCodes(prev => [...prev, code]);
        } else {
            setSelectedCodes(prev => prev.filter(c => c !== code));
        }
    };

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            cleanupProgressTracking();
        };
    }, []);

    // Landing Page View
    if (currentView === 'landing') {
        return (
            <div className="min-h-screen bg-gray-100 py-8">
                <div className="max-w-4xl mx-auto px-4">
                    {/* Header */}
                    <div className="mb-8">
                        <h1 className="text-3xl font-bold text-gray-900">Code Allocation</h1>
                        <p className="text-gray-600 mt-2">
                            Index price codes or allocate them to BOQ files
                        </p>
                    </div>

                    {/* Mode Selection Cards */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        {/* Allocate BOQ Option */}
                        <button
                            onClick={() => {
                                setCurrentMode('allocate');
                                setCurrentView('allocate');
                            }}
                            className="bg-white rounded-xl shadow-sm hover:shadow-lg transition-all duration-200 p-8 text-left border-2 border-transparent hover:border-blue-500 group"
                        >
                            <div className="text-5xl mb-4">📊</div>
                            <h2 className="text-xl font-semibold text-gray-900 mb-2">Allocate BOQ</h2>
                            <p className="text-gray-600">
                                Allocate price codes to Bill of Quantities using AI-powered matching.
                            </p>
                        </button>

                        {/* Index Codes Option */}
                        <button
                            onClick={() => {
                                setCurrentMode('index');
                                setCurrentView('index');
                            }}
                            className="bg-white rounded-xl shadow-sm hover:shadow-lg transition-all duration-200 p-8 text-left border-2 border-transparent hover:border-green-500 group"
                        >
                            <div className="text-5xl mb-4">📁</div>
                            <h2 className="text-xl font-semibold text-gray-900 mb-2">Index Codes</h2>
                            <p className="text-gray-600">
                                Upload and index price code files to your library.
                            </p>
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-100 py-8">
            <div className="max-w-4xl mx-auto px-4">
                {/* Header with Back Button */}
                <div className="mb-8 flex items-center justify-between">
                    <div>
                        <h1 className="text-3xl font-bold text-gray-900">Code Allocation</h1>
                        <p className="text-gray-600 mt-2">
                            {currentMode === 'allocate' ? 'Allocate codes to BOQ' : 'Index price codes'}
                        </p>
                    </div>
                    <button
                        onClick={() => setCurrentView('landing')}
                        className="text-sm text-gray-600 hover:text-gray-900 flex items-center"
                    >
                        <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                        </svg>
                        Back
                    </button>
                </div>

                {/* Upload Section */}
                <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
                    <h2 className="text-lg font-semibold mb-4">
                        {currentMode === 'index' ? 'Upload Price Codes' : 'Upload BOQ File'}
                    </h2>

                    {/* Code Selection (allocate mode only) */}
                    {currentMode === 'allocate' && (
                        <div className="mb-6">
                            <button
                                onClick={() => setShowCodePicker(!showCodePicker)}
                                className="w-full flex items-center justify-between p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
                            >
                                <span className="font-medium text-gray-900">Choose Price Code Set</span>
                                {selectedCodes.length > 0 && (
                                    <span className="text-sm text-blue-600">{selectedCodes.length} selected</span>
                                )}
                            </button>

                            {showCodePicker && (
                                <div className="mt-2 p-4 bg-gray-50 rounded-lg">
                                    {loadingCodes ? (
                                        <p className="text-gray-400">Loading codes...</p>
                                    ) : availableCodes.length === 0 ? (
                                        <p className="text-gray-400">No price codes indexed yet. Use "Index Codes" mode first.</p>
                                    ) : (
                                        <div className="space-y-2 max-h-48 overflow-y-auto">
                                            {availableCodes.map(code => (
                                                <label key={code} className="flex items-center space-x-2 cursor-pointer p-2 hover:bg-white rounded">
                                                    <input
                                                        type="checkbox"
                                                        checked={selectedCodes.includes(code)}
                                                        onChange={(e) => handleCodeToggle(code, e.target.checked)}
                                                        className="rounded"
                                                    />
                                                    <span className="text-gray-900">{code}</span>
                                                </label>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    )}

                    {/* File Input */}
                    <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
                        <input
                            type="file"
                            accept=".xlsx"
                            onChange={handleFileSelect}
                            className="hidden"
                            id="file-upload"
                            disabled={isProcessing || isUploading}
                        />
                        <label
                            htmlFor="file-upload"
                            className={`cursor-pointer ${isProcessing || isUploading ? 'opacity-50' : ''}`}
                        >
                            <div className="text-5xl mb-4">📄</div>
                            <p className="text-gray-600">
                                {selectedFile ? selectedFile.name : 'Click to select an Excel file (.xlsx)'}
                            </p>
                        </label>
                    </div>

                    {uploadError && (
                        <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-600">
                            {uploadError}
                        </div>
                    )}

                    {/* Upload Button */}
                    {selectedFile && !isProcessing && (
                        <button
                            onClick={handleUpload}
                            disabled={isUploading}
                            className="mt-6 w-full bg-blue-600 text-white py-3 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
                        >
                            {isUploading ? 'Uploading...' : `Upload & Process`}
                        </button>
                    )}
                </div>

                {/* Progress Section */}
                {isProcessing && (
                    <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
                        <h2 className="text-lg font-semibold mb-4">Processing</h2>

                        {/* Progress Bar */}
                        <div className="mb-4">
                            <div className="flex justify-between text-sm text-gray-600 mb-2">
                                <span>{processingStatus}</span>
                                <span>{progressPercent}%</span>
                            </div>
                            <div className="w-full bg-gray-200 rounded-full h-4 overflow-hidden">
                                <div
                                    className="h-full bg-blue-600 rounded-full transition-all duration-500"
                                    style={{ width: `${progressPercent}%` }}
                                />
                            </div>
                            {timeRemaining && (
                                <p className="text-sm text-gray-500 mt-2">{timeRemaining}</p>
                            )}
                        </div>
                    </div>
                )}

                {/* Completion Section */}
                {completedFilePath && (
                    <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
                        <div className="flex items-center justify-between">
                            <div>
                                <h2 className="text-lg font-semibold text-green-700">✅ Processing Complete</h2>
                                {resultData && (
                                    <div className="mt-2 text-sm text-gray-600">
                                        <p>Matched: {resultData.matched} | Not Matched: {resultData.not_matched}</p>
                                        <p>Match Rate: {(resultData.match_rate * 100).toFixed(1)}%</p>
                                    </div>
                                )}
                            </div>
                            <div className="flex items-center space-x-3">
                                <button
                                    onClick={() => setShowSummary(true)}
                                    className="text-blue-600 hover:text-blue-800 font-medium px-4 py-2"
                                >
                                    View Summary
                                </button>
                                <button
                                    onClick={handleDownload}
                                    className="bg-green-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-green-700 transition-colors"
                                >
                                    📥 Download
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* Status Message */}
                {processingStatus && !isProcessing && !completedFilePath && (
                    <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
                        <p className="text-gray-600">{processingStatus}</p>
                    </div>
                )}

                {/* Available Codes List (Index Mode) */}
                {currentMode === 'index' && (
                    <div className="bg-white rounded-xl shadow-sm p-6">
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-semibold">Indexed Price Codes</h2>
                            <button
                                onClick={() => {
                                    setLoadingCodes(true);
                                    listAvailablePriceCodes()
                                        .then(codes => setAvailableCodes(codes))
                                        .finally(() => setLoadingCodes(false));
                                }}
                                className="text-blue-600 hover:text-blue-800 text-sm"
                            >
                                Refresh
                            </button>
                        </div>

                        {loadingCodes ? (
                            <p className="text-gray-400">Loading...</p>
                        ) : availableCodes.length === 0 ? (
                            <p className="text-gray-400">No price codes indexed yet.</p>
                        ) : (
                            <ul className="divide-y divide-gray-100">
                                {availableCodes.map(code => (
                                    <li key={code} className="py-3 flex items-center">
                                        <span className="text-2xl mr-3">📋</span>
                                        <span className="font-medium text-gray-900">{code}</span>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>
                )}

                {/* Completed Files List (allocate mode) */}
                {currentMode === 'allocate' && (
                    <div className="bg-white rounded-xl shadow-sm p-6">
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-semibold">Completed Files</h2>
                            <button
                                onClick={async () => {
                                    setLoadingOutputFiles(true);
                                    try {
                                        const files = await listPriceCodeOutputFiles();
                                        setOutputFiles(files);
                                    } finally {
                                        setLoadingOutputFiles(false);
                                    }
                                }}
                                className="text-blue-600 hover:text-blue-800 text-sm"
                            >
                                Refresh
                            </button>
                        </div>

                        {loadingOutputFiles ? (
                            <p className="text-gray-400">Loading...</p>
                        ) : outputFiles.length === 0 ? (
                            <p className="text-gray-400">No completed files yet.</p>
                        ) : (
                            <ul className="divide-y divide-gray-200">
                                {outputFiles.map(file => (
                                    <li key={file.key} className="px-6 py-4 flex items-center justify-between hover:bg-gray-50">
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm font-medium text-gray-900 truncate">{file.filename}</p>
                                            <p className="text-xs text-gray-500">
                                                {new Date(file.lastModified).toLocaleString()} &bull; {(file.size / 1024).toFixed(1)} KB
                                            </p>
                                        </div>
                                        <div className="ml-4 flex-shrink-0 flex space-x-4">
                                            {file.filename.endsWith('.txt') && (
                                                <button
                                                    onClick={() => handleViewSummary(file)}
                                                    className="font-medium text-indigo-600 hover:text-indigo-500 text-sm"
                                                >
                                                    View
                                                </button>
                                            )}
                                            <a
                                                href={file.downloadUrl}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="font-medium text-primary-600 hover:text-primary-500 text-sm"
                                            >
                                                Download
                                            </a>
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>
                )}

                {/* Summary Modal */}
                {/* Summary Modal */}
                {((resultData && showSummary) || viewContent || viewSummaryData) && (
                    <div className="fixed inset-0 z-50 overflow-y-auto" aria-labelledby="modal-title" role="dialog" aria-modal="true">
                        <div className="flex items-end justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
                            <div className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity" aria-hidden="true" onClick={() => { setShowSummary(false); setViewContent(null); setViewSummaryData(null); }}></div>
                            <span className="hidden sm:inline-block sm:align-middle sm:h-screen" aria-hidden="true">&#8203;</span>
                            <div className="inline-block align-bottom bg-white rounded-lg px-4 pt-5 pb-4 text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-lg sm:w-full sm:p-6">
                                <div>
                                    <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-green-100">
                                        <svg className="h-6 w-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                        </svg>
                                    </div>
                                    <div className="mt-3 text-center sm:mt-5">
                                        <h3 className="text-lg leading-6 font-medium text-gray-900" id="modal-title">
                                            {viewTitle || 'Allocation Summary'}
                                        </h3>
                                        <div className="mt-4 text-left">
                                            {viewSummaryData ? (
                                                <div className="space-y-4">
                                                    <div className="bg-gray-50 rounded-lg p-4">
                                                        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">File Information</h4>
                                                        <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                                                            <div><span className="text-gray-500">Input File:</span> <span className="font-medium text-gray-900">{viewSummaryData.fileInfo.inputFile}</span></div>
                                                            <div><span className="text-gray-500">Sheet:</span> <span className="font-medium text-gray-900">{viewSummaryData.fileInfo.sheet}</span></div>
                                                            <div className="col-span-2"><span className="text-gray-500">Generated:</span> <span className="font-medium text-gray-900">{viewSummaryData.fileInfo.generated}</span></div>
                                                            <div className="col-span-2"><span className="text-gray-500">Time:</span> <span className="font-medium text-gray-900">{viewSummaryData.fileInfo.processingTime}</span></div>
                                                        </div>
                                                    </div>

                                                    <div className="bg-gray-50 rounded-lg p-4">
                                                        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Processing Statistics</h4>
                                                        <div className="grid grid-cols-2 gap-4">
                                                            <div>
                                                                <p className="text-sm font-medium text-gray-500">Total Items</p>
                                                                <p className="mt-1 text-2xl font-semibold text-gray-900">{viewSummaryData.stats.totalItems}</p>
                                                            </div>
                                                            <div>
                                                                <p className="text-sm font-medium text-gray-500">Match Rate</p>
                                                                <p className={`mt-1 text-2xl font-semibold ${parseFloat(viewSummaryData.stats.matchRate) > 80 ? 'text-green-600' :
                                                                        parseFloat(viewSummaryData.stats.matchRate) > 50 ? 'text-yellow-600' : 'text-red-600'
                                                                    }`}>
                                                                    {viewSummaryData.stats.matchRate}
                                                                </p>
                                                            </div>
                                                            <div>
                                                                <p className="text-sm font-medium text-gray-500">Matched</p>
                                                                <p className="mt-1 text-lg font-medium text-green-600">{viewSummaryData.stats.matched}</p>
                                                            </div>
                                                            <div>
                                                                <p className="text-sm font-medium text-gray-500">Not Matched</p>
                                                                <p className="mt-1 text-lg font-medium text-red-600">{viewSummaryData.stats.notMatched}</p>
                                                            </div>
                                                            {viewSummaryData.stats.errors > 0 && (
                                                                <div className="col-span-2 mt-2 pt-2 border-t border-gray-200">
                                                                    <p className="text-sm font-medium text-red-600">Errors: {viewSummaryData.stats.errors}</p>
                                                                </div>
                                                            )}
                                                        </div>
                                                    </div>
                                                </div>
                                            ) : viewContent ? (
                                                <div className="bg-gray-50 rounded-lg p-4 max-h-96 overflow-auto">
                                                    <pre className="text-sm text-gray-800 whitespace-pre-wrap font-mono">
                                                        {viewContent}
                                                    </pre>
                                                </div>
                                            ) : resultData ? (
                                                <div className="bg-gray-50 rounded-lg p-4">
                                                    <div className="grid grid-cols-2 gap-4">
                                                        <div>
                                                            <p className="text-sm font-medium text-gray-500">Total Items</p>
                                                            <p className="mt-1 text-2xl font-semibold text-gray-900">{resultData.matched + resultData.not_matched}</p>
                                                        </div>
                                                        <div>
                                                            <p className="text-sm font-medium text-gray-500">Match Rate</p>
                                                            <p className={`mt-1 text-2xl font-semibold ${resultData.match_rate > 0.8 ? 'text-green-600' :
                                                                resultData.match_rate > 0.5 ? 'text-yellow-600' : 'text-red-600'
                                                                }`}>
                                                                {(resultData.match_rate * 100).toFixed(1)}%
                                                            </p>
                                                        </div>
                                                        <div>
                                                            <p className="text-sm font-medium text-gray-500">Matched</p>
                                                            <p className="mt-1 text-lg font-medium text-green-600">{resultData.matched}</p>
                                                        </div>
                                                        <div>
                                                            <p className="text-sm font-medium text-gray-500">Not Matched</p>
                                                            <p className="mt-1 text-lg font-medium text-red-600">{resultData.not_matched}</p>
                                                        </div>
                                                    </div>
                                                </div>
                                            ) : null}

                                            {!viewContent && !viewSummaryData && completedFilePath && (
                                                <div className="mt-4 flex justify-center">
                                                    <button
                                                        type="button"
                                                        className="inline-flex justify-center w-full rounded-md border border-transparent shadow-sm px-4 py-2 bg-blue-600 text-base font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 sm:text-sm"
                                                        onClick={handleDownload}
                                                    >
                                                        Download Result File
                                                    </button>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>
                                <div className="mt-5 sm:mt-6">
                                    <button
                                        type="button"
                                        className="inline-flex justify-center w-full rounded-md border border-gray-300 shadow-sm px-4 py-2 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 sm:text-sm"
                                        onClick={() => { setShowSummary(false); setViewContent(null); setViewSummaryData(null); }}
                                    >
                                        Close
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div >
    );
};

export default CodeAllocation;
