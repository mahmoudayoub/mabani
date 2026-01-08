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
export const getPriceCodeUploadUrl = async (filename: string, mode: 'index' | 'allocate'): Promise<{ url: string; key: string }> => {
    const headers = await getAuthHeaders();
    const params = new URLSearchParams({
        filename: filename,
        mode: mode
    });

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

    const response = await fetch(`${API_BASE_URL}/pricecode/status/${encodeURIComponent(filenameBase)}`, {
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

    const response = await fetch(`${API_BASE_URL}/pricecode/download/${encodeURIComponent(filenameBase)}`, {
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

/**
 * Delete estimate file for a price code job
 */
export const deletePriceCodeEstimate = async (filename: string): Promise<void> => {
    const headers = await getAuthHeaders();
    const filenameBase = filename.replace('.xlsx', '').replace('_pricecode', '');

    const response = await fetch(`${API_BASE_URL}/pricecode/estimate/${encodeURIComponent(filenameBase)}`, {
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
export const uploadPriceCodeFile = async (file: File, mode: 'index' | 'allocate'): Promise<string> => {
    // Get presigned URL
    const { url, key } = await getPriceCodeUploadUrl(file.name, mode);

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
