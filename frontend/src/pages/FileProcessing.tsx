import React, { useState, useEffect, useRef } from 'react';
import {
    getUploadUrl,
    uploadFileToS3,
    listOutputFiles,
    fetchTextContent,
    listAvailableSheets,
    getEstimate,
    listActiveJobs,
    deleteEstimate,
    OutputFile,
    EstimateData,
    deleteSheet,
    getSheetConfig,
    updateSheetConfig,
    SheetGroup
} from '../services/fileProcessingService';
import ChatInterface from '../components/chat/ChatInterface';





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
    filters?: string[];
}

const FileProcessing: React.FC = () => {
    // View State
    const [currentView, setCurrentView] = useState<'landing' | 'fill' | 'parse' | 'chat'>('landing');

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
    const [sheetGroups, setSheetGroups] = useState<SheetGroup[]>([]);
    const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
    const configFileInputRef = useRef<HTMLInputElement>(null);

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

    // Check for active jobs on mount (S3-based)
    useEffect(() => {
        const checkActiveJobs = async () => {
            try {
                const activeJobs = await listActiveJobs();

                if (activeJobs.length > 0) {
                    const job = activeJobs[0];
                    console.log('Found active job:', job);

                    // Calculate elapsed time
                    // IMPORTANT: started_at is UTC, append 'Z' to parse correctly
                    const startTime = new Date(job.started_at + 'Z').getTime();
                    const elapsed = (Date.now() - startTime) / 1000;

                    // Restore progress tracking
                    setIsProcessing(true);
                    setEstimateData(job);

                    // Calculate initial progress
                    const initialProgress = Math.min((elapsed / job.estimated_seconds) * 100, 95);
                    setProgressPercent(initialProgress);
                    setProcessingStatus(initialProgress >= 95 ? 'Finalizing...' : 'Processing...');

                    // Continue animating progress from current point
                    let currentProgress = initialProgress;
                    const updateIntervalMs = 500;
                    const progressIncrement = (100 / job.estimated_seconds) * (updateIntervalMs / 1000);

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
                        const minutes = Math.floor(remaining / 60);
                        const seconds = Math.floor(remaining % 60);
                        setTimeRemaining(`${minutes}:${seconds.toString().padStart(2, '0')} remaining`);
                    }, updateIntervalMs);

                    // Start polling for completion
                    const filenameBase = job.filename.replace('.xlsx', '');
                    const outputPath = `output/fills/${filenameBase}_filled.xlsx`;

                    pollIntervalRef.current = setInterval(async () => {
                        try {
                            // Poll estimate file for completion status
                            const currentEstimate = await getEstimate(job.filename);

                            if (currentEstimate.complete) {
                                console.log('[Resume] Completion signal received:', currentEstimate);
                                if (progressIntervalRef.current) clearInterval(progressIntervalRef.current);
                                if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);

                                if (currentEstimate.success) {
                                    setProgressPercent(100);
                                    setProcessingStatus('Complete!');
                                    setCompletedFilePath(outputPath);
                                    setTimeRemaining('');

                                    // Delete estimate file
                                    try {
                                        await deleteEstimate(job.filename);
                                        console.log('Estimate deleted');
                                    } catch (err) {
                                        console.error('Failed to delete estimate:', err);
                                    }

                                    setTimeout(() => fetchFiles(), 1000);
                                } else {
                                    setIsProcessing(false);
                                    setProcessingStatus(`Failed: ${currentEstimate.error || 'Unknown error'}`);
                                    setProgressPercent(0);
                                    setTimeRemaining('');

                                    try {
                                        await deleteEstimate(job.filename);
                                    } catch (err) {
                                        console.error('Failed to delete estimate:', err);
                                    }
                                }
                            } else {
                                console.log('[Resume] Task still running...');
                            }
                        } catch (err) {
                            console.error('Poll error:', err);
                        }
                    }, 3000);
                }
            } catch (error) {
                console.error('Failed to check active jobs:', error);
            }
        };

        checkActiveJobs();
        // eslint-disable-next-line react-hooks/exhaustive-deps
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
                const config = await getSheetConfig();
                setAvailableSheets(config.sheets);
                setSheetGroups(config.groups);
                // Select all sheets by default
                setSelectedSheets(config.sheets);
            } catch (error) {
                console.error("Failed to fetch sheet config", error);
                // Fallback to simple sheets list
                try {
                    const sheets = await listAvailableSheets();
                    setAvailableSheets(sheets);
                    setSelectedSheets(sheets);
                } catch (e) {
                    console.error("Failed to fetch sheets", e);
                }
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

    const handleGroupToggle = (group: SheetGroup, checked: boolean) => {
        if (checked) {
            // Add all sheets from this group that aren't already selected
            setSelectedSheets(prev => {
                const newSheets = group.sheets.filter(s => !prev.includes(s));
                return [...prev, ...newSheets];
            });
        } else {
            // Remove all sheets from this group
            setSelectedSheets(prev => prev.filter(s => !group.sheets.includes(s)));
        }
    };

    const toggleGroupExpanded = (groupName: string) => {
        setExpandedGroups(prev => {
            const newSet = new Set(prev);
            if (newSet.has(groupName)) {
                newSet.delete(groupName);
            } else {
                newSet.add(groupName);
            }
            return newSet;
        });
    };

    const isGroupFullySelected = (group: SheetGroup): boolean => {
        return group.sheets.every(s => selectedSheets.includes(s));
    };

    const isGroupPartiallySelected = (group: SheetGroup): boolean => {
        const selectedCount = group.sheets.filter(s => selectedSheets.includes(s)).length;
        return selectedCount > 0 && selectedCount < group.sheets.length;
    };

    // Get sheets that are not in any group
    const ungroupedSheets = availableSheets.filter(sheet =>
        !sheetGroups.some(group => group.sheets.includes(sheet))
    );

    const handleDownloadConfig = async () => {
        try {
            const config = await getSheetConfig();
            const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'sheet_config.json';
            a.click();
            URL.revokeObjectURL(url);
        } catch (error) {
            console.error('Failed to download config:', error);
            alert('Failed to download configuration');
        }
    };

    const handleUploadConfig = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) return;

        try {
            const text = await file.text();
            const config = JSON.parse(text);

            if (!config.groups || !Array.isArray(config.groups)) {
                throw new Error('Invalid config: missing groups array');
            }

            await updateSheetConfig(config.groups);
            setSheetGroups(config.groups);
            alert('Configuration updated successfully!');
        } catch (error) {
            console.error('Failed to upload config:', error);
            alert(`Failed to upload configuration: ${error instanceof Error ? error.message : 'Unknown error'}`);
        }

        // Reset file input
        if (configFileInputRef.current) {
            configFileInputRef.current.value = '';
        }
    };

    const handleSheetDelete = async (sheetName: string) => {
        if (!confirm(`Are you sure you want to delete "${sheetName}"? This will remove it from the available list and delete its associated vectors.`)) {
            return;
        }

        try {
            await deleteSheet(sheetName);
            // Remove from available sheets
            setAvailableSheets(prev => prev.filter(name => name !== sheetName));
            // Remove from selected sheets if present
            setSelectedSheets(prev => prev.filter(name => name !== sheetName));
        } catch (error) {
            console.error('Failed to delete sheet:', error);
            alert(`Failed to delete sheet: ${error instanceof Error ? error.message : 'Unknown error'}`);
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
        setProcessingStatus('Waiting for processing to start...');
        setCompletedFilePath(null);

        // Poll for estimate to appear in S3 (worker will create it)
        let estimate: EstimateData | null = null;

        // Wait up to 60 seconds for worker to create estimate
        for (let i = 0; i < 30; i++) {
            await new Promise(resolve => setTimeout(resolve, 2000));

            try {
                const activeJobs = await listActiveJobs();
                if (activeJobs.length > 0) {
                    estimate = activeJobs[0];
                    console.log('Estimate found:', estimate);
                    break;
                }
            } catch (error) {
                console.warn(`Waiting for estimate (attempt ${i + 1}/30)...`, error);
            }
        }

        if (estimate) {
            setEstimateData(estimate);
            setProcessingStatus('Processing...');

            console.log('Starting progress animation:', {
                total_items: estimate.total_items,
                estimated_seconds: estimate.estimated_seconds,
                started_at: estimate.started_at
            });

            // Calculate REAL progress based on elapsed time since worker started
            // IMPORTANT: started_at is UTC, append 'Z' to parse correctly
            const startTime = new Date(estimate.started_at + 'Z').getTime();
            const elapsed = (Date.now() - startTime) / 1000;
            let currentProgress = Math.min((elapsed / estimate.estimated_seconds) * 100, 95);

            console.log('Initial progress calculation:', {
                elapsed_seconds: elapsed,
                estimated_seconds: estimate.estimated_seconds,
                calculated_progress: currentProgress
            });

            setProgressPercent(currentProgress);

            // Continue animating progress from current point
            const updateIntervalMs = 500;
            const progressIncrement = (100 / estimate.estimated_seconds) * (updateIntervalMs / 1000);

            console.log('Progress increment per 500ms:', progressIncrement);

            progressIntervalRef.current = setInterval(() => {
                currentProgress += progressIncrement;

                // Cap at 95% until file is ready
                if (currentProgress >= 95) {
                    currentProgress = 95;
                    setProcessingStatus('Finalizing...');
                }

                setProgressPercent(Math.min(currentProgress, 95));

                // Update time remaining
                const newElapsed = (Date.now() - startTime) / 1000;
                const remaining = Math.max(0, estimate.estimated_seconds - newElapsed);
                const minutes = Math.floor(remaining / 60);
                const seconds = Math.floor(remaining % 60);
                setTimeRemaining(`${minutes}:${seconds.toString().padStart(2, '0')} remaining`);
            }, updateIntervalMs);

            // Start polling for completion
            pollForCompletion(filename, estimate);
        } else {
            // Estimate not found after 60 seconds - show error
            console.error('No estimate available after 60 seconds');
            setProcessingStatus('Processing started but estimate unavailable');
            setIsProcessing(false);
        }
    };

    const pollForCompletion = (filename: string, _estimate: EstimateData | null) => {
        const filenameBase = filename.replace('.xlsx', '');
        const outputPath = `output/fills/${filenameBase}_filled.xlsx`;

        console.log('Starting polling for completion:', {
            filename,
            filenameBase,
            outputPath
        });

        pollIntervalRef.current = setInterval(async () => {
            try {
                // Poll estimate file for completion status (worker updates it before exit)
                const currentEstimate = await getEstimate(filename);
                console.log('[DEBUG] Estimate data:', JSON.stringify(currentEstimate));
                console.log('[DEBUG] complete:', currentEstimate.complete, typeof currentEstimate.complete);

                if (currentEstimate.complete) {
                    console.log('[Worker] Completion signal received:', currentEstimate);
                    cleanupProgressTracking();

                    if (currentEstimate.success) {
                        // Success!
                        console.log('[Worker] Task completed successfully');
                        setProgressPercent(100);
                        setProcessingStatus('Complete!');
                        setCompletedFilePath(outputPath);
                        setTimeRemaining('');

                        // Delete estimate file (worker leaves it, frontend deletes)
                        try {
                            await deleteEstimate(filename);
                            console.log('Estimate file deleted');
                        } catch (err) {
                            console.error('Failed to delete estimate:', err);
                        }

                        // Refresh file list
                        setTimeout(() => fetchFiles(), 1000);
                    } else {
                        // Failed
                        console.error('[Worker] Task failed:', currentEstimate.error);
                        setIsProcessing(false);
                        setProcessingStatus(`Failed: ${currentEstimate.error || 'Unknown error'}`);
                        setProgressPercent(0);
                        setTimeRemaining('');

                        // Delete estimate file
                        try {
                            await deleteEstimate(filename);
                        } catch (err) {
                            console.error('Failed to delete estimate:', err);
                        }
                    }

                    return; // Stop polling
                } else {
                    console.log('[Worker] Task still running, waiting for completion signal...');
                }
            } catch (error) {
                console.error('[Polling] Error checking estimate:', error);
            }
        }, 3000); // Check every 3 seconds
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
            else if (line.includes('FILTERS USED')) section = 'filters';
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
                } else if (section === 'filters') {
                    if (!data.filters) data.filters = [];
                    if (key && val) data.filters.push(`${key}: ${val}`);
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
            <div className="min-h-screen bg-gray-100 py-8">
                <div className="max-w-5xl mx-auto px-4">
                    {/* Header */}
                    <div className="mb-8">
                        <h1 className="text-3xl font-bold text-gray-900">Unit Rate Allocation</h1>
                        <p className="text-gray-600 mt-2">
                            Fill Bill of Quantities or add data to Smart Library
                        </p>
                    </div>

                    {/* Mode Selection Cards */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        {/* AI Assistant Option */}
                        <button
                            onClick={() => setCurrentView('chat')}
                            className="bg-white rounded-xl shadow-sm hover:shadow-lg transition-all duration-200 p-8 text-left border-2 border-transparent hover:border-purple-500 group"
                        >
                            <div className="text-5xl mb-4">🤖</div>
                            <h2 className="text-xl font-semibold text-gray-900 mb-2">AI Assistant</h2>
                            <p className="text-gray-600">
                                Ask questions to find the right unit rate for any work item.
                            </p>
                        </button>

                        {/* Fill BOQ Option */}
                        <button
                            onClick={() => {
                                setMode('fill');
                                setCurrentView('fill');
                            }}
                            className="bg-white rounded-xl shadow-sm hover:shadow-lg transition-all duration-200 p-8 text-left border-2 border-transparent hover:border-blue-500 group"
                        >
                            <div className="text-5xl mb-4">📊</div>
                            <h2 className="text-xl font-semibold text-gray-900 mb-2">Fill BOQ</h2>
                            <p className="text-gray-600">
                                Extract data and fill Bill of Quantities using AI-powered matching from your smart library.
                            </p>
                        </button>

                        {/* Upload to Smart Library Option */}
                        <button
                            onClick={() => {
                                setMode('parse');
                                setCurrentView('parse');
                            }}
                            className="bg-white rounded-xl shadow-sm hover:shadow-lg transition-all duration-200 p-8 text-left border-2 border-transparent hover:border-green-500 group"
                        >
                            <div className="text-5xl mb-4">📁</div>
                            <h2 className="text-xl font-semibold text-gray-900 mb-2">Upload to Smart Library</h2>
                            <p className="text-gray-600">
                                Parse and index Excel files to expand your searchable knowledge base.
                            </p>
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    // Chat View
    if (currentView === 'chat') {
        return (
            <div className="min-h-screen bg-gray-100 py-8">
                <div className="max-w-4xl mx-auto px-4">
                    <div className="mb-6 flex items-center justify-between">
                        <div>
                            <h1 className="text-2xl font-bold text-gray-900">Unit Rate Assistant</h1>
                            <p className="text-sm text-gray-600">
                                Ask questions to find the right unit rate for any work item
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

                    <ChatInterface
                        type="unitrate"
                        title="Unit Rate Lookup"
                        placeholder="e.g., What is the unit rate for plastering an internal wall?"
                        welcomeMessage="Hello! I can help you find unit rates for construction work items. Describe the work you're looking for, including the trade, type of work, and any relevant details."
                    />
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
                                        {/* Download/Upload Config Buttons */}
                                        <div className="flex gap-2 mb-3 pb-3 border-b border-gray-200">
                                            <button
                                                onClick={handleDownloadConfig}
                                                className="flex-1 flex items-center justify-center gap-1 px-3 py-2 text-xs font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
                                            >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                                </svg>
                                                Download Config
                                            </button>
                                            <label className="flex-1 flex items-center justify-center gap-1 px-3 py-2 text-xs font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors cursor-pointer">
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                                                </svg>
                                                Upload Config
                                                <input
                                                    ref={configFileInputRef}
                                                    type="file"
                                                    accept=".json"
                                                    className="hidden"
                                                    onChange={handleUploadConfig}
                                                />
                                            </label>
                                        </div>

                                        {loadingSheets ? (
                                            <p className="text-xs text-gray-400">Loading sheets...</p>
                                        ) : availableSheets.length === 0 ? (
                                            <p className="text-xs text-gray-400">No available sheets found.</p>
                                        ) : (
                                            <div className="max-h-80 overflow-y-auto space-y-2">
                                                {/* Groups Section */}
                                                {sheetGroups.map(group => (
                                                    <div key={group.name} className="border border-gray-200 rounded-lg bg-white">
                                                        {/* Group Header */}
                                                        <div className="flex items-center justify-between p-2 bg-gray-100 rounded-t-lg">
                                                            <div className="flex items-center gap-2">
                                                                <input
                                                                    type="checkbox"
                                                                    className="h-4 w-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                                                                    checked={isGroupFullySelected(group)}
                                                                    ref={(el) => {
                                                                        if (el) el.indeterminate = isGroupPartiallySelected(group);
                                                                    }}
                                                                    onChange={(e) => handleGroupToggle(group, e.target.checked)}
                                                                />
                                                                <button
                                                                    onClick={() => toggleGroupExpanded(group.name)}
                                                                    className="flex items-center gap-1 text-sm font-medium text-gray-800 hover:text-primary-600"
                                                                >
                                                                    <svg
                                                                        className={`w-4 h-4 transition-transform ${expandedGroups.has(group.name) ? 'rotate-90' : ''}`}
                                                                        fill="none"
                                                                        stroke="currentColor"
                                                                        viewBox="0 0 24 24"
                                                                    >
                                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                                                    </svg>
                                                                    📂 {group.name}
                                                                </button>
                                                            </div>
                                                            <span className="text-xs text-gray-500">
                                                                {group.sheets.filter(s => selectedSheets.includes(s)).length}/{group.sheets.length}
                                                            </span>
                                                        </div>
                                                        {/* Group Sheets (Collapsible) */}
                                                        {expandedGroups.has(group.name) && (
                                                            <div className="p-2 pl-8 space-y-1">
                                                                {group.sheets.map(sheetName => (
                                                                    <label key={sheetName} className="flex items-center gap-2 p-1 hover:bg-gray-50 rounded cursor-pointer">
                                                                        <input
                                                                            type="checkbox"
                                                                            className="h-4 w-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                                                                            checked={selectedSheets.includes(sheetName)}
                                                                            onChange={(e) => handleSheetToggle(sheetName, e.target.checked)}
                                                                        />
                                                                        <span className="text-xs text-gray-700">{sheetName}</span>
                                                                    </label>
                                                                ))}
                                                            </div>
                                                        )}
                                                    </div>
                                                ))}

                                                {/* Ungrouped Sheets Section */}
                                                {ungroupedSheets.length > 0 && (
                                                    <div className="border border-gray-200 rounded-lg bg-white">
                                                        <div className="p-2 bg-gray-50 rounded-t-lg">
                                                            <span className="text-sm font-medium text-gray-600">📄 Ungrouped Sheets</span>
                                                        </div>
                                                        <div className="p-2 space-y-1">
                                                            {ungroupedSheets.map(sheetName => (
                                                                <label key={sheetName} className="flex items-center gap-2 p-1 hover:bg-gray-50 rounded cursor-pointer">
                                                                    <input
                                                                        type="checkbox"
                                                                        className="h-4 w-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                                                                        checked={selectedSheets.includes(sheetName)}
                                                                        onChange={(e) => handleSheetToggle(sheetName, e.target.checked)}
                                                                    />
                                                                    <span className="text-xs text-gray-700">{sheetName}</span>
                                                                </label>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}
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
                                        <li key={sheetName} className="px-6 py-4 flex items-center justify-between hover:bg-gray-50 group">
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
                                            <button
                                                onClick={() => handleSheetDelete(sheetName)}
                                                className="text-gray-400 hover:text-red-600 p-2 transition-colors rounded-full hover:bg-red-50"
                                                title="Delete Datasheet"
                                            >
                                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                                </svg>
                                            </button>
                                        </li>
                                    ))}
                                </ul>
                            )
                        )}
                    </div>
                </div>
            </div>

            {/* Summary Modal */}
            {
                isModalOpen && (
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

                                        {summaryData.filters && summaryData.filters.length > 0 && (
                                            <div className="mb-6 bg-gray-50 p-4 rounded-lg">
                                                <h4 className="text-xs text-gray-500 uppercase mb-2">Filters Used</h4>
                                                <div className="space-y-1">
                                                    {summaryData.filters.map((filter, i) => (
                                                        <p key={i} className="text-sm font-medium text-gray-900 break-words">{filter}</p>
                                                    ))}
                                                </div>
                                            </div>
                                        )}

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
                )
            }
        </div >
    );
};

export default FileProcessing;
