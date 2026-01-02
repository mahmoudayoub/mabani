import React, { useState, useEffect, useRef } from 'react';
import {
    getUploadUrl,
    uploadFileToS3,
    listOutputFiles,
    fetchTextContent,
    listAvailableSheets,
    getEstimate,
    checkFileExists,
    OutputFile,
    EstimateData
} from '../services/fileProcessingService';
// import { KnowledgeBase, Document } from '../types/knowledgeBase';

interface SummaryData {
    input: string;
    output: string;
    sheet: string;
    generated: string;
    processingTime: string;
    stats: {
        totalItems: string;
        processed: string;
        exactMatches: string;
        expertMatches: string;
        estimates: string;
        noMatches: string;
        errors: string;
        fillRate: string;
    };
    ratios: {
        exact: string;
        expert: string;
        estimates: string;
        noMatch: string;
        errors: string;
    };
}

const FileProcessing: React.FC = () => {
    // View State
    const [currentView, setCurrentView] = useState<'landing' | 'fill' | 'parse'>('landing');

    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [mode, setMode] = useState<'fill' | 'parse'>('fill');
    const [uploading, setUploading] = useState(false);
    const [files, setFiles] = useState<OutputFile[]>([]);
    const [loadingFiles, setLoadingFiles] = useState(false);

    // Sheet Selection State
    const [availableSheets, setAvailableSheets] = useState<string[]>([]);
    const [selectedSheets, setSelectedSheets] = useState<string[]>([]);
    const [loadingSheets, setLoadingSheets] = useState(false);
    const [showSheetPicker, setShowSheetPicker] = useState(false);

    // Modal State
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [summaryData, setSummaryData] = useState<SummaryData | null>(null);
    const [loadingSummary, setLoadingSummary] = useState(false);

    // Progress Tracking State
    const [isProcessing, setIsProcessing] = useState(false);
    const [progressPercent, setProgressPercent] = useState(0);
    const [estimateData, setEstimateData] = useState<EstimateData | null>(null);
    const [processingStatus, setProcessingStatus] = useState('');
    const [timeRemaining, setTimeRemaining] = useState('');
    const [completedFilePath, setCompletedFilePath] = useState<string | null>(null);

    const progressIntervalRef = useRef<NodeJS.Timeout | null>(null);
    const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

    // Save progress state to localStorage
    useEffect(() => {
        if (isProcessing && estimateData) {
            const progressState = {
                isProcessing,
                progressPercent,
                estimateData,
                processingStatus,
                filename: estimateData.filename,
                startedAt: Date.now()
            };
            localStorage.setItem('fileProcessingProgress', JSON.stringify(progressState));
        } else if (!isProcessing) {
            localStorage.removeItem('fileProcessingProgress');
        }
    }, [isProcessing, progressPercent, estimateData, processingStatus]);

    // Resume progress tracking on mount
    useEffect(() => {
        const savedProgress = localStorage.getItem('fileProcessingProgress');
        if (savedProgress) {
            try {
                const state = JSON.parse(savedProgress);
                const elapsed = (Date.now() - state.startedAt) / 1000;

                // Only resume if not too old (within 2x estimated time)
                if (elapsed < state.estimateData.estimated_seconds * 2) {
                    setIsProcessing(true);
                    setEstimateData(state.estimateData);
                    setProcessingStatus('Resuming...');

                    // Resume tracking
                    setTimeout(() => {
                        pollForCompletion(state.filename + '.xlsx', state.estimateData);
                    }, 1000);
                } else {
                    // Too old, clear it
                    localStorage.removeItem('fileProcessingProgress');
                }
            } catch (error) {
                console.error('Failed to resume progress:', error);
                localStorage.removeItem('fileProcessingProgress');
            }
        }
    }, []);

    const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        if (event.target.files && event.target.files.length > 0) {
            setSelectedFile(event.target.files[0]);
        }
    };

    // Load Available Sheets on mount
    useEffect(() => {
        const fetchSheets = async () => {
            setLoadingSheets(true);
            try {
                const sheets = await listAvailableSheets();
                setAvailableSheets(sheets);
            } catch (error) {
                console.error("Failed to fetch available sheets", error);
            } finally {
                setLoadingSheets(false);
            }
        };
        fetchSheets();
    }, []);

    const handleSheetToggle = (sheetName: string, checked: boolean) => {
        if (checked) {
            setSelectedSheets(prev => [...prev, sheetName]);
        } else {
            setSelectedSheets(prev => prev.filter(name => name !== sheetName));
        }
    };

    const handleUpload = async () => {
        if (!selectedFile) return;

        setUploading(true);
        try {
            // 1. Get presigned URL with metadata
            const { uploadUrl } = await getUploadUrl(
                selectedFile.name,
                mode,
                mode === 'fill' ? selectedSheets : undefined
            );

            // 2. Upload file
            await uploadFileToS3(uploadUrl, selectedFile);

            setSelectedFile(null);
            setSelectedSheets([]); // Reset selection

            // 3. Start progress tracking for fill mode
            if (mode === 'fill') {
                startProgressTracking(selectedFile.name);
            } else {
                alert('File uploaded successfully! Processing started.');
            }
        } catch (error) {
            console.error(error);
            alert('Failed to upload file.');
        } finally {
            setUploading(false);
        }
    };

    const startProgressTracking = async (filename: string) => {
        setIsProcessing(true);
        setProgressPercent(0);
        setProcessingStatus('Initializing...');
        setCompletedFilePath(null);

        // Wait for worker to start and upload estimate
        await new Promise(resolve => setTimeout(resolve, 2000));

        // Try to fetch estimate with retries
        let estimate: EstimateData | null = null;
        for (let attempt = 1; attempt <= 3; attempt++) {
            try {
                console.log(`Fetching estimate (attempt ${attempt}/3)...`);
                estimate = await getEstimate(filename);
                console.log('Estimate received:', estimate);
                break;
            } catch (error) {
                console.warn(`Estimate fetch attempt ${attempt} failed:`, error);
                if (attempt < 3) {
                    // Wait longer between retries (2s, 4s, 6s)
                    await new Promise(resolve => setTimeout(resolve, 2000 * attempt));
                }
            }
        }

        if (estimate) {
            setEstimateData(estimate);
            setProcessingStatus('Processing...');

            // Start smooth progress animation
            let currentProgress = 0;
            const updateIntervalMs = 500;
            const progressIncrement = (100 / estimate.estimated_seconds) * (updateIntervalMs / 1000);

            progressIntervalRef.current = setInterval(() => {
                currentProgress += progressIncrement;

                // Stall at 95% - don't go beyond until file is ready
                if (currentProgress >= 95) {
                    currentProgress = 95;
                    setProcessingStatus('Finalizing...');
                }

                setProgressPercent(Math.min(currentProgress, 95));
                updateTimeRemaining(estimate, currentProgress);
            }, updateIntervalMs);

            // Start polling for completion
            pollForCompletion(filename, estimate);
        } else {
            // Fall back to indeterminate progress
            console.warn('No estimate available after 3 attempts. Showing indeterminate progress.');
            setProcessingStatus('Processing (time estimate unavailable)...');
            setProgressPercent(50); // Show some progress
            pollForCompletion(filename, null);
        }
    };

    const pollForCompletion = (filename: string, estimate: EstimateData | null) => {
        const filenameBase = filename.replace('.xlsx', '');
        const outputPath = `output/fills/${filenameBase}_filled.xlsx`;

        pollIntervalRef.current = setInterval(async () => {
            try {
                const exists = await checkFileExists(outputPath);

                if (exists) {
                    // File is ready!
                    cleanupProgressTracking();

                    // Fill to 100%
                    setProgressPercent(100);
                    setProcessingStatus('Complete!');
                    setCompletedFilePath(outputPath);

                    // Refresh file list
                    setTimeout(() => {
                        fetchFiles();
                    }, 1000);
                }
            } catch (error) {
                console.error('Error checking file:', error);
            }
        }, 3000); // Check every 3 seconds

        // Cleanup after max time (estimate * 3 to be safe, or 30 min default)
        const maxWaitMs = estimate ? estimate.estimated_seconds * 3 * 1000 : 30 * 60 * 1000;
        setTimeout(() => {
            if (progressPercent < 100) {
                cleanupProgressTracking();
                setProcessingStatus('Processing took longer than expected. Please check results.');
            }
        }, maxWaitMs);
    };

    const updateTimeRemaining = (estimate: EstimateData, currentProgress: number) => {
        if (currentProgress >= 95) {
            setTimeRemaining('Finalizing...');
            return;
        }

        const elapsed = (Date.now() - new Date(estimate.started_at).getTime()) / 1000;
        const remaining = Math.max(0, estimate.estimated_seconds - elapsed);
        const minutes = Math.floor(remaining / 60);
        const seconds = Math.floor(remaining % 60);

        setTimeRemaining(`${minutes}:${seconds.toString().padStart(2, '0')} remaining`);
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

    const resetProcessing = () => {
        cleanupProgressTracking();
        setIsProcessing(false);
        setProgressPercent(0);
        setEstimateData(null);
        setProcessingStatus('');
        setTimeRemaining('');
        setCompletedFilePath(null);
    };

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            cleanupProgressTracking();
        };
    }, []);

    const fetchFiles = async () => {
        setLoadingFiles(true);
        try {
            const fileList = await listOutputFiles();
            setFiles(fileList);
        } catch (error) {
            console.error(error);
            // Fail silently or show toast
        } finally {
            setLoadingFiles(false);
        }
    };

    useEffect(() => {
        fetchFiles();
    }, []);

    const formatBytes = (bytes: number) => {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    };

    // Refined extraction to handle duplicate labels in different sections
    const extractSummaryData = (text: string): SummaryData => {
        const lines = text.split('\n');
        const data: any = { stats: {}, ratios: {} };

        let section = '';
        lines.forEach(line => {
            if (line.includes('FILE INFORMATION')) section = 'info';
            else if (line.includes('PROCESSING STATISTICS')) section = 'stats';
            else if (line.includes('Ratios over total items')) section = 'ratios';

            const parts = line.split(':');
            if (parts.length >= 2) {
                const key = parts[0].trim();
                const val = parts[1].trim();

                if (section === 'info') {
                    if (key === 'Input File') data.input = val;
                    if (key === 'Output File') data.output = val;
                    if (key === 'Sheet') data.sheet = val;
                    if (key === 'Generated') data.generated = val + (parts[2] ? ':' + parts[2] : '') + (parts[3] ? ':' + parts[3] : ''); // quick fix for time colons
                    if (key === 'Processing Time') data.processingTime = val + (parts[2] ? ':' + parts[2] : '');
                } else if (section === 'stats') {
                    if (key === 'Total Items') data.stats.totalItems = val;
                    if (key === 'Processed') data.stats.processed = val;
                    if (key === 'Exact Matches') data.stats.exactMatches = val;
                    if (key === 'Expert Matches') data.stats.expertMatches = val;
                    if (key === 'Estimates') data.stats.estimates = val;
                    if (key === 'No Matches') data.stats.noMatches = val;
                    if (key === 'Errors' && !data.stats.errors) data.stats.errors = val;
                    if (key === 'Fill Rate') data.stats.fillRate = val;
                } else if (section === 'ratios') {
                    if (key === 'Exact') data.ratios.exact = val;
                    if (key === 'Expert') data.ratios.expert = val;
                    if (key === 'Estimates') data.ratios.estimates = val;
                    if (key === 'No Match') data.ratios.noMatch = val;
                    if (key === 'Errors') data.ratios.errors = val;
                }
            }
        });
        return data as SummaryData;
    };


    const handleViewSummary = async (file: OutputFile) => {
        setLoadingSummary(true);
        setIsModalOpen(true);
        try {
            const text = await fetchTextContent(file.downloadUrl);
            const parsed = extractSummaryData(text);
            setSummaryData(parsed);
        } catch (error) {
            console.error(error);
            alert('Failed to fetch summary.');
            setIsModalOpen(false);
        } finally {
            setLoadingSummary(false);
        }
    };

    // Landing Page View
    if (currentView === 'landing') {
        return (
            <div className="px-4 py-6 sm:px-6 lg:px-8">
                <div className="mb-8 text-center">
                    <h1 className="text-3xl font-bold text-gray-900">Price Allocation</h1>
                    <p className="text-sm text-gray-600 mt-2">Choose your operation</p>
                </div>

                <div className="max-w-4xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Filling Option */}
                    <button
                        onClick={() => {
                            setMode('fill');
                            setCurrentView('fill');
                        }}
                        className="group bg-white rounded-xl shadow-lg hover:shadow-xl transition-all duration-200 p-8 text-left border-2 border-transparent hover:border-primary-500"
                    >
                        <div className="flex items-center justify-center w-16 h-16 bg-primary-100 rounded-lg mb-4 group-hover:bg-primary-200 transition-colors">
                            <svg className="w-8 h-8 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                        </div>
                        <h2 className="text-xl font-semibold text-gray-900 mb-2">Filling</h2>
                        <p className="text-sm text-gray-600">Extract data and fill Bill of Quantities using AI-powered matching from your smart library.</p>
                    </button>

                    {/* Upload to Smart Library Option */}
                    <button
                        onClick={() => {
                            setMode('parse');
                            setCurrentView('parse');
                        }}
                        className="group bg-white rounded-xl shadow-lg hover:shadow-xl transition-all duration-200 p-8 text-left border-2 border-transparent hover:border-green-500"
                    >
                        <div className="flex items-center justify-center w-16 h-16 bg-green-100 rounded-lg mb-4 group-hover:bg-green-200 transition-colors">
                            <svg className="w-8 h-8 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                            </svg>
                        </div>
                        <h2 className="text-xl font-semibold text-gray-900 mb-2">Upload to Smart Library</h2>
                        <p className="text-sm text-gray-600">Parse and index Excel files to expand your searchable knowledge base.</p>
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="px-4 py-6 sm:px-6 lg:px-8">
            <div className="mb-6 flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">
                        {currentView === 'fill' ? 'Filling' : 'Upload to Smart Library'}
                    </h1>
                    <p className="text-sm text-gray-600">
                        {currentView === 'fill'
                            ? 'Upload Excel files for AI-powered price filling.'
                            : 'Parse and index Excel files to your knowledge base.'}
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

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Upload Section */}
                <div className="lg:col-span-1">
                    <div className="bg-white rounded-lg shadow p-6">
                        <h2 className="text-lg font-semibold text-gray-900 mb-4">Upload New File</h2>

                        {currentView === 'fill' && (
                            <div className="mb-6">
                                <button
                                    onClick={() => setShowSheetPicker(!showSheetPicker)}
                                    className="w-full flex items-center justify-between px-4 py-3 bg-primary-50 hover:bg-primary-100 rounded-lg transition-colors border border-primary-200"
                                >
                                    <div className="flex items-center">
                                        <svg className="w-5 h-5 text-primary-600 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                        </svg>
                                        <span className="font-medium text-gray-900">Choose Data Sheets</span>
                                    </div>
                                    <div className="flex items-center">
                                        {selectedSheets.length > 0 && (
                                            <span className="text-xs bg-primary-600 text-white px-2 py-1 rounded-full mr-2">
                                                {selectedSheets.length} selected
                                            </span>
                                        )}
                                        <svg
                                            className={`w-5 h-5 text-gray-600 transition-transform ${showSheetPicker ? 'rotate-180' : ''}`}
                                            fill="none"
                                            stroke="currentColor"
                                            viewBox="0 0 24 24"
                                        >
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                        </svg>
                                    </div>
                                </button>

                                {showSheetPicker && (
                                    <div className="mt-3 border border-gray-200 rounded-lg p-3 bg-gray-50">
                                        {loadingSheets ? (
                                            <p className="text-xs text-gray-400">Loading sheets...</p>
                                        ) : availableSheets.length === 0 ? (
                                            <p className="text-xs text-gray-400">No available sheets found.</p>
                                        ) : (
                                            <div className="max-h-60 overflow-y-auto space-y-2">
                                                {availableSheets.map(sheetName => (
                                                    <label key={sheetName} className="flex items-start space-x-2 cursor-pointer p-2 hover:bg-white rounded transition-colors">
                                                        <input
                                                            type="checkbox"
                                                            className="mt-1 h-4 w-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                                                            checked={selectedSheets.includes(sheetName)}
                                                            onChange={(e) => handleSheetToggle(sheetName, e.target.checked)}
                                                        />
                                                        <div className="text-xs">
                                                            <p className="font-medium text-gray-900 break-all">{sheetName}</p>
                                                        </div>
                                                    </label>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        )}

                        <div className="mb-6">
                            <label className="block text-sm font-medium text-gray-700 mb-2">File</label>
                            <div className="mt-1 flex justify-center px-6 pt-5 pb-6 border-2 border-gray-300 border-dashed rounded-md">
                                <div className="space-y-1 text-center">
                                    <svg className="mx-auto h-12 w-12 text-gray-400" stroke="currentColor" fill="none" viewBox="0 0 48 48" aria-hidden="true">
                                        <path d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                                    </svg>
                                    <div className="flex text-sm text-gray-600">
                                        <label htmlFor="file-upload" className="relative cursor-pointer bg-white rounded-md font-medium text-primary-600 hover:text-primary-500 focus-within:outline-none focus-within:ring-2 focus-within:ring-offset-2 focus-within:ring-primary-500">
                                            <span>Upload a file</span>
                                            <input id="file-upload" name="file-upload" type="file" className="sr-only" accept=".xlsx" onChange={handleFileChange} />
                                        </label>
                                        <p className="pl-1">or drag and drop</p>
                                    </div>
                                    <p className="text-xs text-gray-500">
                                        XLSX up to 10MB
                                    </p>
                                </div>
                            </div>
                            {selectedFile && (
                                <p className="mt-2 text-sm text-gray-600 text-center">Selected: {selectedFile.name}</p>
                            )}
                        </div>

                        <button
                            onClick={handleUpload}
                            disabled={!selectedFile || uploading || isProcessing}
                            className={`w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white ${!selectedFile || uploading || isProcessing ? 'bg-gray-400 cursor-not-allowed' : 'bg-primary-600 hover:bg-primary-700'} focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500`}
                        >
                            {uploading ? 'Uploading...' : 'Upload File'}
                        </button>

                        {/* Progress Tracking UI */}
                        {isProcessing && (
                            <div className="mt-6 p-4 bg-blue-50 rounded-lg border border-blue-200">
                                <div className="mb-3">
                                    <div className="flex justify-between items-center mb-2">
                                        <span className="text-sm font-medium text-gray-900">{processingStatus}</span>
                                        <span className="text-sm font-semibold text-primary-600">{Math.round(progressPercent)}%</span>
                                    </div>
                                    {timeRemaining && progressPercent < 100 && (
                                        <p className="text-xs text-gray-600 mb-2">{timeRemaining}</p>
                                    )}
                                    <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                                        <div
                                            className="h-full bg-gradient-to-r from-primary-500 to-primary-600 transition-all duration-500 ease-out"
                                            style={{ width: `${progressPercent}%` }}
                                        ></div>
                                    </div>
                                </div>

                                {estimateData && progressPercent < 100 && (
                                    <p className="text-xs text-gray-500">
                                        Processing {estimateData.total_items} items
                                    </p>
                                )}

                                {completedFilePath && progressPercent === 100 && (
                                    <div className="mt-3 pt-3 border-t border-blue-300">
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center text-green-700">
                                                <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                                </svg>
                                                <span className="text-sm font-medium">Processing complete!</span>
                                            </div>
                                            <button
                                                onClick={resetProcessing}
                                                className="text-sm text-primary-600 hover:text-primary-800 font-medium"
                                            >
                                                Process Another
                                            </button>
                                        </div>
                                        {estimateData && (
                                            <p className="text-xs text-gray-600 mt-2">
                                                Processed {estimateData.total_items} items
                                            </p>
                                        )}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>

                {/* Output List Section */}
                <div className="lg:col-span-2">
                    <div className="bg-white rounded-lg shadow overflow-hidden">
                        <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
                            <h2 className="text-lg font-semibold text-gray-900">
                                {currentView === 'fill' ? 'Processed Files' : 'Available Sheets'}
                            </h2>
                            <button
                                onClick={currentView === 'fill' ? fetchFiles : () => {
                                    setLoadingSheets(true);
                                    listAvailableSheets()
                                        .then(sheets => setAvailableSheets(sheets))
                                        .catch(err => console.error(err))
                                        .finally(() => setLoadingSheets(false));
                                }}
                                className="text-primary-600 hover:text-primary-800 text-sm font-medium"
                            >
                                Refresh
                            </button>
                        </div>

                        {currentView === 'fill' ? (
                            // Show processed fill files
                            loadingFiles ? (
                                <div className="p-6 text-center text-gray-500">Loading...</div>
                            ) : files.length === 0 ? (
                                <div className="p-6 text-center text-gray-500">No output files found.</div>
                            ) : (
                                <ul className="divide-y divide-gray-200">
                                    {files.map((file) => (
                                        <li key={file.key} className="px-6 py-4 flex items-center justify-between hover:bg-gray-50">
                                            <div className="flex-1 min-w-0">
                                                <p className="text-sm font-medium text-gray-900 truncate">{file.filename}</p>
                                                <p className="text-xs text-gray-500">
                                                    {new Date(file.lastModified).toLocaleString()} &bull; {formatBytes(file.size)}
                                                </p>
                                            </div>
                                            <div className="ml-4 flex-shrink-0 flex space-x-4">
                                                {file.filename.endsWith('.txt') && (
                                                    <button
                                                        onClick={() => handleViewSummary(file)}
                                                        className="font-medium text-indigo-600 hover:text-indigo-500"
                                                    >
                                                        View
                                                    </button>
                                                )}
                                                <a
                                                    href={file.downloadUrl}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="font-medium text-primary-600 hover:text-primary-500"
                                                >
                                                    Download
                                                </a>
                                            </div>
                                        </li>
                                    ))}
                                </ul>
                            )
                        ) : (
                            // Show available sheets for parse mode
                            loadingSheets ? (
                                <div className="p-6 text-center text-gray-500">Loading...</div>
                            ) : availableSheets.length === 0 ? (
                                <div className="p-6 text-center text-gray-500">
                                    <svg className="mx-auto h-12 w-12 text-gray-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                    </svg>
                                    <p>No sheets in the library yet.</p>
                                    <p className="text-xs mt-1">Upload an Excel file to get started.</p>
                                </div>
                            ) : (
                                <ul className="divide-y divide-gray-200">
                                    {availableSheets.map((sheetName) => (
                                        <li key={sheetName} className="px-6 py-4 flex items-center hover:bg-gray-50">
                                            <div className="flex items-center flex-1">
                                                <div className="flex-shrink-0 h-10 w-10 bg-green-100 rounded-lg flex items-center justify-center">
                                                    <svg className="h-6 w-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                                    </svg>
                                                </div>
                                                <div className="ml-4">
                                                    <p className="text-sm font-medium text-gray-900">{sheetName}</p>
                                                    <p className="text-xs text-gray-500">Available for matching</p>
                                                </div>
                                            </div>
                                        </li>
                                    ))}
                                </ul>
                            )
                        )}
                    </div>
                </div>
            </div>

            {/* Summary Modal */}
            {isModalOpen && (
                <div className="fixed inset-0 z-50 overflow-y-auto" aria-labelledby="modal-title" role="dialog" aria-modal="true">
                    <div className="flex items-end justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
                        <div className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity" aria-hidden="true" onClick={() => setIsModalOpen(false)}></div>
                        <span className="hidden sm:inline-block sm:align-middle sm:h-screen" aria-hidden="true">&#8203;</span>
                        <div className="inline-block align-bottom bg-white rounded-lg px-4 pt-5 pb-4 text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-2xl sm:w-full sm:p-6">

                            {loadingSummary || !summaryData ? (
                                <div className="text-center py-4">Loading summary...</div>
                            ) : (
                                <div>
                                    <div className="mb-4 pb-4 border-b border-gray-200">
                                        <h3 className="text-lg leading-6 font-medium text-gray-900" id="modal-title">Processing Summary</h3>
                                        <p className="mt-1 text-sm text-gray-500">Generated on {summaryData.generated}</p>
                                    </div>

                                    <div className="grid grid-cols-2 gap-4 mb-6">
                                        <div>
                                            <p className="text-xs text-gray-500 uppercase">Input File</p>
                                            <p className="font-medium">{summaryData.input}</p>
                                        </div>
                                        <div>
                                            <p className="text-xs text-gray-500 uppercase">Sheet</p>
                                            <p className="font-medium">{summaryData.sheet}</p>
                                        </div>
                                        <div>
                                            <p className="text-xs text-gray-500 uppercase">Processing Time</p>
                                            <p className="font-medium">{summaryData.processingTime}</p>
                                        </div>
                                        <div>
                                            <p className="text-xs text-gray-500 uppercase">Fill Rate</p>
                                            <p className="text-xl font-bold text-green-600">{summaryData.stats.fillRate}</p>
                                        </div>
                                    </div>

                                    <div className="mb-6">
                                        <h4 className="text-sm font-medium text-gray-900 mb-3">Statistics</h4>
                                        <div className="grid grid-cols-4 gap-4 bg-gray-50 p-4 rounded-lg">
                                            <div>
                                                <p className="text-xs text-gray-500">Total</p>
                                                <p className="text-lg font-semibold">{summaryData.stats.totalItems}</p>
                                            </div>
                                            <div>
                                                <p className="text-xs text-gray-500">Processed</p>
                                                <p className="text-lg font-semibold">{summaryData.stats.processed}</p>
                                            </div>
                                            <div>
                                                <p className="text-xs text-gray-500">Errors</p>
                                                <p className="text-lg font-semibold text-red-600">{summaryData.stats.errors}</p>
                                            </div>
                                        </div>
                                    </div>

                                    <div>
                                        <h4 className="text-sm font-medium text-gray-900 mb-3">Matching Breakdown</h4>
                                        <div className="space-y-3">
                                            {/* Exact Matches - Green */}
                                            <div>
                                                <div className="flex items-center justify-between mb-1">
                                                    <span className="text-sm font-medium text-gray-700">Exact Matches</span>
                                                    <div className="flex items-center">
                                                        <span className="text-sm font-semibold text-green-700 mr-2">{summaryData.stats.exactMatches}</span>
                                                        <span className="text-xs text-gray-500">({summaryData.ratios.exact})</span>
                                                    </div>
                                                </div>
                                                <div className="w-full bg-gray-200 rounded-full h-3">
                                                    <div className="bg-green-500 h-3 rounded-full transition-all" style={{ width: summaryData.ratios.exact }}></div>
                                                </div>
                                            </div>

                                            {/* Expert Matches - Yellow */}
                                            <div>
                                                <div className="flex items-center justify-between mb-1">
                                                    <span className="text-sm font-medium text-gray-700">Expert Matches</span>
                                                    <div className="flex items-center">
                                                        <span className="text-sm font-semibold text-yellow-700 mr-2">{summaryData.stats.expertMatches}</span>
                                                        <span className="text-xs text-gray-500">({summaryData.ratios.expert})</span>
                                                    </div>
                                                </div>
                                                <div className="w-full bg-gray-200 rounded-full h-3">
                                                    <div className="bg-yellow-500 h-3 rounded-full transition-all" style={{ width: summaryData.ratios.expert }}></div>
                                                </div>
                                            </div>

                                            {/* Estimates - Orange */}
                                            <div>
                                                <div className="flex items-center justify-between mb-1">
                                                    <span className="text-sm font-medium text-gray-700">Estimates</span>
                                                    <div className="flex items-center">
                                                        <span className="text-sm font-semibold text-orange-700 mr-2">{summaryData.stats.estimates}</span>
                                                        <span className="text-xs text-gray-500">({summaryData.ratios.estimates})</span>
                                                    </div>
                                                </div>
                                                <div className="w-full bg-gray-200 rounded-full h-3">
                                                    <div className="bg-orange-500 h-3 rounded-full transition-all" style={{ width: summaryData.ratios.estimates }}></div>
                                                </div>
                                            </div>

                                            {/* No Matches - Red */}
                                            <div>
                                                <div className="flex items-center justify-between mb-1">
                                                    <span className="text-sm font-medium text-gray-700">No Matches (Unfilled)</span>
                                                    <div className="flex items-center">
                                                        <span className="text-sm font-semibold text-red-700 mr-2">{summaryData.stats.noMatches}</span>
                                                        <span className="text-xs text-gray-500">({summaryData.ratios.noMatch})</span>
                                                    </div>
                                                </div>
                                                <div className="w-full bg-gray-200 rounded-full h-3">
                                                    <div className="bg-red-500 h-3 rounded-full transition-all" style={{ width: summaryData.ratios.noMatch }}></div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="mt-6 flex justify-end">
                                        <button
                                            type="button"
                                            className="bg-white py-2 px-4 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none"
                                            onClick={() => setIsModalOpen(false)}
                                        >
                                            Close
                                        </button>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default FileProcessing;
