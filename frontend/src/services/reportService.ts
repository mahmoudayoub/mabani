
import { API_BASE_URL, getAuthHeaders } from '../utils/api';

export interface Report {
    PK: string; // REPORT#{uuid}
    SK: string; // METADATA
    reportNumber?: number;
    timestamp?: string;
    completedAt?: string;
    sender?: string;
    description?: string;
    originalDescription?: string;
    severity?: string;
    hazardTypes?: string[];
    classification?: string; // from workflow
    s3Url?: string;
    status?: string;
    [key: string]: any;
}

export const listReports = async (): Promise<Report[]> => {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE_URL}/reports`, {
        method: 'GET',
        headers: headers,
    });

    if (!response.ok) {
        throw new Error(`Failed to fetch reports: ${response.statusText}`);
    }

    const data = await response.json();
    // Sort client-side just in case
    return data;
};

export const getReport = async (reportId: string): Promise<Report> => {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE_URL}/reports/${reportId}`, {
        method: 'GET',
        headers: headers,
    });

    if (!response.ok) {
        throw new Error(`Failed to fetch report: ${response.statusText}`);
    }

    return await response.json();
};
