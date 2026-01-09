import React, { useState, useEffect, useRef } from 'react';
import {
    uploadPriceCodeFile,
    getPriceCodeStatus,
    getPriceCodeDownloadUrl,
    listAvailablePriceCodes,
    deletePriceCodeEstimate,
    PriceCodeEstimate
} from '../services/priceCodeService';

type Mode = 'index' | 'allocate';

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

    // Available Price Codes (for allocation mode)
    const [availableCodes, setAvailableCodes] = useState<string[]>([]);
    const [loadingCodes, setLoadingCodes] = useState(false);
    const [selectedCodes, setSelectedCodes] = useState<string[]>([]);
    const [showCodePicker, setShowCodePicker] = useState(false);

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
                        setCompletedFilePath(`output/pricecode/${filenameBase}_pricecode.xlsx`);
                        setTimeRemaining('');
                        setResultData(status.result || null);

                        // Delete estimate file
                        try {
                            await deletePriceCodeEstimate(filename);
                            console.log('Estimate file deleted');
                        } catch (err) {
                            console.error('Failed to delete estimate:', err);
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
                            <button
                                onClick={handleDownload}
                                className="bg-green-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-green-700 transition-colors"
                            >
                                📥 Download
                            </button>
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
            </div>
        </div>
    );
};

export default CodeAllocation;
