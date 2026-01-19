import { fetchAuthSession } from 'aws-amplify/auth';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

const getAuthHeaders = async (): Promise<Record<string, string>> => {
    try {
        const session = await fetchAuthSession();
        const token = session.tokens?.idToken?.toString();
        return {
            'Authorization': token ? `Bearer ${token}` : '',
            'Content-Type': 'application/json',
        };
    } catch (error) {
        console.error('Failed to get auth session:', error);
        return {
            'Authorization': '',
            'Content-Type': 'application/json',
        };
    }
};

// ============================================================
// PRICE CODE API FUNCTIONS
// ============================================================

export interface PriceCodeEstimate {
    total_items: number;
    estimated_seconds: number;
    estimated_minutes?: number;
    started_at: string;
    filename: string;
    // Completion fields (added by worker before exit)
    complete?: boolean;
    success?: boolean;
    error?: string;
    result?: {
        matched: number;
        not_matched: number;
        match_rate: number;
    };
}

/**
 * Get presigned upload URL for price code file
 */
export const getPriceCodeUploadUrl = async (
    filename: string,
    mode: 'index' | 'allocate',
    sourceFiles?: string[]
): Promise<{ url: string; key: string }> => {
    const headers = await getAuthHeaders();
    const params = new URLSearchParams({
        filename: filename,
        mode: mode
    });

    // Add source files as comma-separated string for allocate mode
    if (sourceFiles && sourceFiles.length > 0) {
        params.append('sourceFiles', sourceFiles.join(','));
    }

    const response = await fetch(`${API_BASE_URL}/pricecode/upload-url?${params}`, {
        method: 'POST',
        headers: headers,
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `Failed to get upload URL: ${response.statusText}`);
    }

    return await response.json();
};

/**
 * Get status/estimate for a price code job
 */
export const getPriceCodeStatus = async (filename: string): Promise<PriceCodeEstimate> => {
    const headers = await getAuthHeaders();
    const filenameBase = filename.replace('.xlsx', '').replace('_pricecode', '');

    const response = await fetch(`${API_BASE_URL}/pricecode/status/${encodeURI(filenameBase)}`, {
        method: 'GET',
        headers: headers,
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `Failed to get status: ${response.statusText}`);
    }

    return await response.json();
};

/**
 * Get presigned download URL for completed price code file
 */
export const getPriceCodeDownloadUrl = async (filename: string): Promise<{ url: string; key: string; filename: string }> => {
    const headers = await getAuthHeaders();
    const filenameBase = filename.replace('.xlsx', '').replace('_pricecode', '');

    const response = await fetch(`${API_BASE_URL}/pricecode/download/${encodeURI(filenameBase)}`, {
        method: 'GET',
        headers: headers,
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `Failed to get download URL: ${response.statusText}`);
    }

    return await response.json();
};

/**
 * List available price code sets from metadata
 */
export const listAvailablePriceCodes = async (): Promise<string[]> => {
    const headers = await getAuthHeaders();

    const response = await fetch(`${API_BASE_URL}/pricecode/codes`, {
        method: 'GET',
        headers: headers,
    });

    if (!response.ok) {
        throw new Error(`Failed to list price codes: ${response.statusText}`);
    }

    const data = await response.json();
    return data.price_codes || [];
};

export interface PriceCodeOutputFile {
    key: string;
    filename: string;
    size: number;
    lastModified: string;
    downloadUrl: string;
}

/**
 * List completed price code output files
 */
export const listPriceCodeOutputFiles = async (): Promise<PriceCodeOutputFile[]> => {
    const headers = await getAuthHeaders();

    const response = await fetch(`${API_BASE_URL}/pricecode/files`, {
        method: 'GET',
        headers: headers,
    });

    if (!response.ok) {
        throw new Error(`Failed to list output files: ${response.statusText}`);
    }

    const data = await response.json();
    return data.files || [];
};

/**
 * List active price code jobs (for resuming state)
 */
export const listActivePriceCodeJobs = async (): Promise<PriceCodeEstimate[]> => {
    const headers = await getAuthHeaders();

    const response = await fetch(`${API_BASE_URL}/pricecode/active-jobs`, {
        method: 'GET',
        headers: headers,
    });

    if (!response.ok) {
        throw new Error(`Failed to list active jobs: ${response.statusText}`);
    }

    const data = await response.json();
    return data.active_jobs || [];
};

/**
 * Delete estimate file for a price code job
 */
export const deletePriceCodeEstimate = async (filename: string): Promise<void> => {
    const headers = await getAuthHeaders();
    const filenameBase = filename.replace('.xlsx', '').replace('_pricecode', '');

    const response = await fetch(`${API_BASE_URL}/pricecode/estimate/${encodeURI(filenameBase)}`, {
        method: 'DELETE',
        headers: headers,
    });

    if (!response.ok) {
        throw new Error(`Failed to delete estimate: ${response.statusText}`);
    }
};

/**
 * Upload file to S3 using presigned URL
 */
export const uploadPriceCodeFile = async (
    file: File,
    mode: 'index' | 'allocate',
    sourceFiles?: string[]
): Promise<string> => {
    // Get presigned URL with source files metadata
    const { url, key } = await getPriceCodeUploadUrl(file.name, mode, sourceFiles);

    // Upload to S3
    const uploadResponse = await fetch(url, {
        method: 'PUT',
        body: file,
        headers: {
            'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        },
    });

    if (!uploadResponse.ok) {
        throw new Error(`Failed to upload file: ${uploadResponse.statusText}`);
    }

    return key;
};

export const fetchTextContent = async (url: string): Promise<string> => {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`Failed to fetch text content: ${response.statusText}`);
    }
    return await response.text();
};

/**
 * Delete a price code set (External API)
 */
export const deletePriceCodeSet = async (setName: string): Promise<void> => {
    // HARDCODED External API URL
    const deletionApiUrl = "https://auwdkyf4ka.execute-api.eu-west-1.amazonaws.com/prod/";

    // Note: External endpoint might not need headers if public, but sending them is safe
    const headers = await getAuthHeaders();
    const encodedName = encodeURIComponent(setName);

    const baseUrl = deletionApiUrl.endsWith('/') ? deletionApiUrl.slice(0, -1) : deletionApiUrl;

    const response = await fetch(`${baseUrl}/pricecode/sets/${encodedName}`, {
        method: 'DELETE',
        headers: headers,
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `Failed to delete price code set: ${response.statusText}`);
    }
};
