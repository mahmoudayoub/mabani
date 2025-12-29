import React, { useState, useEffect } from 'react';
import {
    getUploadUrl,
    uploadFileToS3,
    listOutputFiles,
    fetchTextContent,
    listAvailableSheets,
    OutputFile
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
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [mode, setMode] = useState<'fill' | 'parse'>('fill');
    const [uploading, setUploading] = useState(false);
    const [files, setFiles] = useState<OutputFile[]>([]);
    const [loadingFiles, setLoadingFiles] = useState(false);

    // Sheet Selection State
    const [availableSheets, setAvailableSheets] = useState<string[]>([]);
    const [selectedSheets, setSelectedSheets] = useState<string[]>([]);
    const [loadingSheets, setLoadingSheets] = useState(false);

    // Modal State
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [summaryData, setSummaryData] = useState<SummaryData | null>(null);
    const [loadingSummary, setLoadingSummary] = useState(false);

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

            alert('File uploaded successfully! Processing started.');
            setSelectedFile(null);
            setSelectedSheets([]); // Reset selection
        } catch (error) {
            console.error(error);
            alert('Failed to upload file.');
        } finally {
            setUploading(false);
        }
    };

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

    return (
        <div className="px-4 py-6 sm:px-6 lg:px-8">
            <div className="mb-6">
                <h1 className="text-2xl font-bold text-gray-900">File Processing</h1>
                <p className="text-sm text-gray-600">Upload Excel files for AI processing and retrieve results.</p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Upload Section */}
                <div className="lg:col-span-1">
                    <div className="bg-white rounded-lg shadow p-6">
                        <h2 className="text-lg font-semibold text-gray-900 mb-4">Upload New File</h2>

                        <div className="mb-4">
                            <label className="block text-sm font-medium text-gray-700 mb-2">Select Mode</label>
                            <div className="flex space-x-4">
                                <label className="inline-flex items-center">
                                    <input
                                        type="radio"
                                        className="form-radio text-primary-600"
                                        name="mode"
                                        value="fill"
                                        checked={mode === 'fill'}
                                        onChange={() => setMode('fill')}
                                    />
                                    <span className="ml-2">Fill</span>
                                </label>
                                <label className="inline-flex items-center">
                                    <input
                                        type="radio"
                                        className="form-radio text-primary-600"
                                        name="mode"
                                        value="parse"
                                        checked={mode === 'parse'}
                                        onChange={() => setMode('parse')}
                                    />
                                    <span className="ml-2">Parse</span>
                                </label>
                            </div>
                            <p className="text-xs text-gray-500 mt-1">
                                {mode === 'fill' ? 'Extracts data and fills BoQ using AI.' : 'Parses raw Excel file to structured format.'}
                            </p>
                        </div>

                        {mode === 'fill' && (
                            <div className="mb-6 border-t border-gray-200 pt-4">
                                <h3 className="text-sm font-medium text-gray-900 mb-3">Available Sheets</h3>

                                {loadingSheets ? (
                                    <p className="text-xs text-gray-400">Loading sheets...</p>
                                ) : availableSheets.length === 0 ? (
                                    <p className="text-xs text-gray-400">No available sheets found.</p>
                                ) : (
                                    <div className="max-h-60 overflow-y-auto border border-gray-200 rounded-md p-2 space-y-2">
                                        {availableSheets.map(sheetName => (
                                            <label key={sheetName} className="flex items-start space-x-2 cursor-pointer p-1 hover:bg-gray-50 rounded">
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
                                <p className="text-xs text-gray-500 mt-2">
                                    Selected: {selectedSheets.length}
                                </p>
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
                            disabled={!selectedFile || uploading}
                            className={`w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white ${!selectedFile || uploading ? 'bg-gray-400 cursor-not-allowed' : 'bg-primary-600 hover:bg-primary-700'} focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500`}
                        >
                            {uploading ? 'Uploading...' : 'Upload File'}
                        </button>
                    </div>
                </div>

                {/* Output List Section */}
                <div className="lg:col-span-2">
                    <div className="bg-white rounded-lg shadow overflow-hidden">
                        <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
                            <h2 className="text-lg font-semibold text-gray-900">Processed Files</h2>
                            <button onClick={fetchFiles} className="text-primary-600 hover:text-primary-800 text-sm font-medium">
                                Refresh
                            </button>
                        </div>

                        {loadingFiles ? (
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
                                        <div className="space-y-2">
                                            <div className="flex items-center justify-between">
                                                <span className="text-sm text-gray-600">Exact Matches</span>
                                                <div className="flex items-center">
                                                    <span className="text-sm font-medium mr-2">{summaryData.stats.exactMatches}</span>
                                                    <span className="text-xs text-gray-500">({summaryData.ratios.exact})</span>
                                                </div>
                                            </div>
                                            <div className="w-full bg-gray-200 rounded-full h-2">
                                                <div className="bg-green-500 h-2 rounded-full" style={{ width: summaryData.ratios.exact }}></div>
                                            </div>

                                            <div className="flex items-center justify-between mt-2">
                                                <span className="text-sm text-gray-600">Expert Matches</span>
                                                <div className="flex items-center">
                                                    <span className="text-sm font-medium mr-2">{summaryData.stats.expertMatches}</span>
                                                    <span className="text-xs text-gray-500">({summaryData.ratios.expert})</span>
                                                </div>
                                            </div>
                                            <div className="w-full bg-gray-200 rounded-full h-2">
                                                <div className="bg-blue-500 h-2 rounded-full" style={{ width: summaryData.ratios.expert }}></div>
                                            </div>

                                            <div className="flex items-center justify-between mt-2">
                                                <span className="text-sm text-gray-600">Estimates</span>
                                                <div className="flex items-center">
                                                    <span className="text-sm font-medium mr-2">{summaryData.stats.estimates}</span>
                                                    <span className="text-xs text-gray-500">({summaryData.ratios.estimates})</span>
                                                </div>
                                            </div>
                                            <div className="w-full bg-gray-200 rounded-full h-2">
                                                <div className="bg-yellow-500 h-2 rounded-full" style={{ width: summaryData.ratios.estimates }}></div>
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
