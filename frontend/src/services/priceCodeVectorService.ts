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
// PRICE CODE VECTOR API FUNCTIONS
// ============================================================

export interface PriceCodeVectorEstimate {
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
 * Get presigned upload URL for price code vector file
 */
export const getPriceCodeVectorUploadUrl = async (
    filename: string,
    mode: 'index' | 'allocate',
    sourceFiles?: string[]
): Promise<{ url: string; key: string }> => {
    const headers = await getAuthHeaders();
    const params = new URLSearchParams({
        filename: filename,
        mode: mode
    });

    // Add source files as comma-separated string for allocate mode (optional)
    if (sourceFiles && sourceFiles.length > 0) {
        params.append('sourceFiles', sourceFiles.join(','));
    }

    const response = await fetch(`${API_BASE_URL}/pricecode-vector/upload-url?${params}`, {
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
 * Get status/estimate for a price code vector job
 */
export const getPriceCodeVectorStatus = async (filename: string): Promise<PriceCodeVectorEstimate> => {
    const headers = await getAuthHeaders();
    const filenameBase = filename.replace('.xlsx', '').replace('_pricecode_vector', '');

    const response = await fetch(`${API_BASE_URL}/pricecode-vector/status/${encodeURI(filenameBase)}`, {
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
 * Get presigned download URL for completed price code vector file
 */
export const getPriceCodeVectorDownloadUrl = async (filename: string): Promise<{ url: string; key: string; filename: string }> => {
    const headers = await getAuthHeaders();
    const filenameBase = filename.replace('.xlsx', '').replace('_pricecode_vector', '');

    const response = await fetch(`${API_BASE_URL}/pricecode-vector/download/${encodeURI(filenameBase)}`, {
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
 * List available price code vector sets from metadata
 */
export const listAvailablePriceCodeVectors = async (): Promise<string[]> => {
    const headers = await getAuthHeaders();

    const response = await fetch(`${API_BASE_URL}/pricecode-vector/codes`, {
        method: 'GET',
        headers: headers,
    });

    if (!response.ok) {
        throw new Error(`Failed to list price code vector sets: ${response.statusText}`);
    }

    const data = await response.json();
    return data.sets || [];
};

export interface PriceCodeVectorOutputFile {
    key: string;
    filename: string;
    size: number;
    lastModified: string;
    downloadUrl: string;
}

/**
 * List completed price code vector output files
 */
export const listPriceCodeVectorOutputFiles = async (): Promise<PriceCodeVectorOutputFile[]> => {
    const headers = await getAuthHeaders();

    const response = await fetch(`${API_BASE_URL}/pricecode-vector/files`, {
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
 * List active price code vector jobs (for resuming state)
 */
export const listActivePriceCodeVectorJobs = async (): Promise<PriceCodeVectorEstimate[]> => {
    const headers = await getAuthHeaders();

    const response = await fetch(`${API_BASE_URL}/pricecode-vector/active-jobs`, {
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
 * Delete estimate file for a price code vector job
 */
export const deletePriceCodeVectorEstimate = async (filename: string): Promise<void> => {
    const headers = await getAuthHeaders();
    const filenameBase = filename.replace('.xlsx', '').replace('_pricecode_vector', '');

    const response = await fetch(`${API_BASE_URL}/pricecode-vector/estimate/${encodeURI(filenameBase)}`, {
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
export const uploadPriceCodeVectorFile = async (
    file: File,
    mode: 'index' | 'allocate',
    sourceFiles?: string[]
): Promise<string> => {
    // Get presigned URL with source files metadata
    const { url, key } = await getPriceCodeVectorUploadUrl(file.name, mode, sourceFiles);

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
 * Delete a price code vector set (External API — async with polling)
 */
export const deletePriceCodeVectorSet = async (setName: string): Promise<void> => {
    const deletionApiUrl = "https://auwdkyf4ka.execute-api.eu-west-1.amazonaws.com/prod";

    const headers = await getAuthHeaders();
    const encodedName = encodeURIComponent(setName);

    // 1. Fire DELETE → dispatcher returns 202 with deletion_id
    const response = await fetch(`${deletionApiUrl}/pricecode-vector/sets/${encodedName}`, {
        method: 'DELETE',
        headers: headers,
    });

    if (!response.ok && response.status !== 202) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `Failed to delete price code vector set: ${response.statusText}`);
    }

    const data = await response.json();
    const deletionId = data.deletion_id;
    const bucketType = data.bucket_type || 'pricecode-vector';

    if (!deletionId) return;

    // 2. Poll deletion status until complete or error
    const maxAttempts = 120;
    for (let i = 0; i < maxAttempts; i++) {
        await new Promise(resolve => setTimeout(resolve, 5000));

        try {
            const statusResp = await fetch(
                `${deletionApiUrl}/deletion-status/${encodeURIComponent(deletionId)}?bucket_type=${bucketType}`,
                { method: 'GET', headers: headers }
            );

            if (statusResp.status === 404) continue;

            if (statusResp.ok) {
                const statusData = await statusResp.json();
                if (statusData.status === 'complete') return;
                if (statusData.status === 'error') {
                    throw new Error(statusData.error || 'Deletion failed');
                }
            }
        } catch (error) {
            if (error instanceof Error && error.message.includes('Deletion failed')) throw error;
            console.log('Polling deletion status...', error);
        }
    }

    throw new Error('Deletion timed out — it may still complete in the background');
};

