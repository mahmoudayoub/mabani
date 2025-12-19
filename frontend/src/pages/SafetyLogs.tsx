
import React, { useState, useEffect } from "react";
import { listReports, Report } from "../services/reportService";

const SafetyLogs: React.FC = () => {
    const [reports, setReports] = useState<Report[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [selectedReport, setSelectedReport] = useState<Report | null>(null);

    useEffect(() => {
        fetchReports();
    }, []);

    const fetchReports = async () => {
        setLoading(true);
        try {
            const data = await listReports();
            setReports(data);
            setError(null);
        } catch (err) {
            setError("Failed to load reports.");
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="space-y-6">
            <div className="border-b border-gray-200 pb-5">
                <h3 className="text-2xl font-bold leading-6 text-gray-900">
                    Safety Logs
                </h3>
                <p className="mt-2 text-sm text-gray-500">
                    View recent safety observations and reports.
                </p>
            </div>

            <div className="bg-white shadow rounded-lg overflow-hidden">
                {error && (
                    <div className="m-4 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
                        {error}
                    </div>
                )}

                {loading ? (
                    <div className="flex justify-center py-10">
                        <svg className="animate-spin h-8 w-8 text-primary-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gray-50">
                                <tr>
                                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                        ID
                                    </th>
                                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                        Date
                                    </th>
                                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                        Type
                                    </th>
                                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                        Description
                                    </th>
                                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                        Severity
                                    </th>
                                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                        Status
                                    </th>
                                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                        Actions
                                    </th>
                                </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-200">
                                {reports.length === 0 ? (
                                    <tr>
                                        <td colSpan={7} className="px-6 py-4 text-center text-sm text-gray-500">
                                            No reports found.
                                        </td>
                                    </tr>
                                ) : (
                                    reports.map((report) => (
                                        <tr key={report.requestId || report.PK} className="hover:bg-gray-50 transition-colors">
                                            <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                                                #{report.reportNumber || "N/A"}
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                                {report.timestamp ? new Date(report.timestamp).toLocaleDateString() : (report.completedAt ? new Date(report.completedAt).toLocaleDateString() : "-")}
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                                {(() => {
                                                    const val = report.classification || report.observationType || "General";
                                                    if (typeof val === 'object' && val !== null) {
                                                        // Handle case where AI returned an object (e.g. {code, name})
                                                        // casting to any to access potential keys without strict typing issues for now
                                                        const v = val as any;
                                                        return v.code && v.name ? `${v.code} ${v.name}` : JSON.stringify(v);
                                                    }
                                                    return val;
                                                })()}
                                            </td>
                                            <td className="px-6 py-4 text-sm text-gray-500 max-w-xs truncate" title={report.originalDescription}>
                                                {report.originalDescription || report.description || "-"}
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-sm">
                                                <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full 
                                                    ${(report.severity?.toUpperCase() === 'HIGH') ? 'bg-red-100 text-red-800' :
                                                        (report.severity?.toUpperCase() === 'MEDIUM') ? 'bg-yellow-100 text-yellow-800' :
                                                            'bg-green-100 text-green-800'}`}>
                                                    {report.severity || "Unknown"}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                                {report.status}
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-blue-600 hover:text-blue-900">
                                                <button onClick={() => setSelectedReport(report)} className="font-medium text-primary-600 hover:text-primary-900">
                                                    View Details
                                                </button>
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* Details Modal */}
            {selectedReport && (
                <div className="fixed inset-0 z-50 overflow-y-auto" aria-labelledby="modal-title" role="dialog" aria-modal="true">
                    <div className="flex items-end justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
                        <div className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity" aria-hidden="true" onClick={() => setSelectedReport(null)}></div>
                        <span className="hidden sm:inline-block sm:align-middle sm:h-screen" aria-hidden="true">&#8203;</span>
                        <div className="inline-block align-bottom bg-white rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-3xl sm:w-full">
                            <div className="bg-white px-4 pt-5 pb-4 sm:p-6 sm:pb-4">
                                <div className="sm:flex sm:items-start">
                                    <div className="mt-3 text-center sm:mt-0 sm:ml-4 sm:text-left w-full">
                                        <div className="flex justify-between items-center mb-4">
                                            <h3 className="text-lg leading-6 font-medium text-gray-900" id="modal-title">
                                                Report #{selectedReport.reportNumber} Details
                                            </h3>
                                            <button onClick={() => setSelectedReport(null)} className="text-gray-400 hover:text-gray-500">
                                                <span className="sr-only">Close</span>
                                                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                                                </svg>
                                            </button>
                                        </div>

                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                            {/* Left Column: Image & Basic Info */}
                                            <div className="space-y-4">
                                                <div className="aspect-w-16 aspect-h-9 bg-gray-100 rounded-lg overflow-hidden border border-gray-200">
                                                    {(selectedReport.imageUrl || selectedReport.s3Url) ? (
                                                        <img
                                                            src={selectedReport.imageUrl || (selectedReport.s3Url ? selectedReport.s3Url.replace("s3://", "https://").replace("taskflow-backend-dev-reports", "taskflow-backend-dev-reports.s3.eu-west-1.amazonaws.com") : "")}
                                                            alt="Report Evidence"
                                                            className="object-cover w-full h-full"
                                                        />
                                                    ) : (
                                                        <div className="flex items-center justify-center h-48 text-gray-400">
                                                            No Image Available
                                                        </div>
                                                    )}
                                                </div>
                                                <div className="grid grid-cols-2 gap-4 text-sm">
                                                    <div>
                                                        <p className="text-gray-500">Responsible Person</p>
                                                        <p className="font-medium text-gray-900">{selectedReport.responsiblePerson || "N/A"}</p>
                                                    </div>
                                                    <div>
                                                        <p className="text-gray-500">Reporter</p>
                                                        <p className="font-medium text-gray-900">{selectedReport.reporter || selectedReport.sender || "N/A"}</p>
                                                    </div>
                                                    <div>
                                                        <p className="text-gray-500">Location</p>
                                                        <p className="font-medium text-gray-900">{selectedReport.location || "Default Project"}</p>
                                                    </div>
                                                    <div>
                                                        <p className="text-gray-500">Date & Time</p>
                                                        <p className="font-medium text-gray-900">
                                                            {(() => {
                                                                const dateStr = selectedReport.timestamp || selectedReport.completedAt || selectedReport.updatedAt;
                                                                if (!dateStr) return "Unknown";
                                                                return new Date(dateStr).toLocaleString(undefined, {
                                                                    dateStyle: 'medium',
                                                                    timeStyle: 'short'
                                                                });
                                                            })()}
                                                        </p>
                                                    </div>
                                                </div>
                                            </div>

                                            {/* Right Column: AI Analysis & Details */}
                                            <div className="space-y-4">
                                                <div>
                                                    <h4 className="text-sm font-medium text-gray-500 uppercase tracking-wider">Description</h4>
                                                    <p className="mt-1 text-sm text-gray-900 bg-gray-50 p-3 rounded-md">
                                                        {selectedReport.originalDescription}
                                                    </p>
                                                </div>

                                                <div>
                                                    <h4 className="text-sm font-medium text-gray-500 uppercase tracking-wider flex items-center gap-2">
                                                        AI Analysis
                                                        <span className={`px-2 py-0.5 rounded-full text-xs ${(selectedReport.severity?.toUpperCase() === 'HIGH') ? 'bg-red-100 text-red-800' :
                                                            (selectedReport.severity?.toUpperCase() === 'MEDIUM') ? 'bg-yellow-100 text-yellow-800' :
                                                                'bg-green-100 text-green-800'
                                                            }`}>
                                                            {selectedReport.severity}
                                                        </span>
                                                    </h4>
                                                    <p className="mt-1 text-sm text-gray-700">
                                                        <span className="font-medium">Observation Type:</span> {(() => {
                                                            const val = selectedReport.classification;
                                                            if (typeof val === 'object' && val !== null) {
                                                                const v = val as any;
                                                                return v.code && v.name ? `${v.code} ${v.name}` : JSON.stringify(v);
                                                            }
                                                            return val;
                                                        })()}
                                                    </p>
                                                    {selectedReport.severityReason && (
                                                        <p className="mt-2 text-sm text-gray-600 italic border-l-2 border-gray-300 pl-3">
                                                            "{selectedReport.severityReason}"
                                                        </p>
                                                    )}
                                                </div>

                                                {selectedReport.controlMeasure && (
                                                    <div>
                                                        <h4 className="text-sm font-medium text-primary-700 uppercase tracking-wider">Recommended Action (Control Measure)</h4>
                                                        <div className="mt-1 p-3 bg-primary-50 rounded-md border border-primary-100">
                                                            <p className="text-sm text-primary-900 font-medium">{selectedReport.controlMeasure}</p>
                                                        </div>
                                                    </div>
                                                )}

                                                {selectedReport.reference && (
                                                    <div>
                                                        <h4 className="text-sm font-medium text-gray-500 uppercase tracking-wider">Safety Reference</h4>
                                                        <p className="mt-1 text-xs text-gray-500 font-mono bg-gray-50 p-2 rounded border truncate">
                                                            {selectedReport.reference}
                                                        </p>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div className="bg-gray-50 px-4 py-3 sm:px-6 sm:flex sm:flex-row-reverse">
                                <button type="button" className="w-full inline-flex justify-center rounded-md border border-transparent shadow-sm px-4 py-2 bg-primary-600 text-base font-medium text-white hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 sm:ml-3 sm:w-auto sm:text-sm" onClick={() => setSelectedReport(null)}>
                                    Close
                                </button>
                                {selectedReport.imageUrl && (
                                    <a href={selectedReport.imageUrl} target="_blank" rel="noopener noreferrer" className="mt-3 w-full inline-flex justify-center rounded-md border border-gray-300 shadow-sm px-4 py-2 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 sm:mt-0 sm:ml-3 sm:w-auto sm:text-sm">
                                        Open Full Image
                                    </a>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default SafetyLogs;
