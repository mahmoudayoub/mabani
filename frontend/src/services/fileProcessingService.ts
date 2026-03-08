import { API_BASE_URL, getAuthHeaders } from '../utils/api';

export interface OutputFile {
    key: string;
    filename: string;
    lastModified: string;
    size: number;
    downloadUrl: string;
}

export const getUploadUrl = async (
    filename: string,
    mode: 'fill' | 'parse',
    sheetNames?: string[]
): Promise<{ uploadUrl: string; key: string; bucket: string }> => {
    const headers = await getAuthHeaders();
    const params: Record<string, string> = { filename, mode };

    if (sheetNames && sheetNames.length > 0) {
        params.sheetNames = sheetNames.join(',');
    }

    const queryParams = new URLSearchParams(params);

    const response = await fetch(`${API_BASE_URL}/files/upload-url?${queryParams}`, {
        method: 'GET',
        headers: headers,
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `Failed to get upload URL: ${response.statusText}`);
    }

    return await response.json();
};

export const listAvailableSheets = async (): Promise<string[]> => {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE_URL}/files/sheets`, {
        method: 'GET',
        headers: headers,
    });

    if (!response.ok) {
        throw new Error(`Failed to list sheets: ${response.statusText}`);
    }

    const data = await response.json();
    return data.sheets || [];
};

// Sheet Groups Types and Functions
export interface SheetGroup {
    name: string;
    sheets: string[];
}

export interface SheetConfig {
    sheets: string[];
    groups: SheetGroup[];
}

export const getSheetConfig = async (): Promise<SheetConfig> => {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE_URL}/files/sheet-config`, {
        method: 'GET',
        headers: headers,
    });

    if (!response.ok) {
        throw new Error(`Failed to get sheet config: ${response.statusText}`);
    }

    const data = await response.json();
    return {
        sheets: data.sheets || [],
        groups: data.groups || []
    };
};

export const updateSheetConfig = async (groups: SheetGroup[]): Promise<void> => {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE_URL}/files/sheet-config`, {
        method: 'PUT',
        headers: headers,
        body: JSON.stringify({ groups })
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `Failed to update sheet config: ${response.statusText}`);
    }
};

export const uploadFileToS3 = async (uploadUrl: string, file: File) => {
    const response = await fetch(uploadUrl, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        },
        body: file
    });

    if (!response.ok) {
        throw new Error(`Failed to upload file to S3: ${response.statusText}`);
    }
};

export const listOutputFiles = async (): Promise<OutputFile[]> => {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE_URL}/files/outputs`, {
        method: 'GET',
        headers: headers,
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `Failed to list output files: ${response.statusText}`);
    }

    const data = await response.json();
    return data.files || [];
};

export const fetchTextContent = async (url: string): Promise<string> => {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`Failed to fetch text content: ${response.statusText}`);
    }
    return await response.text();
};

export interface EstimateData {
    total_items: number;
    estimated_seconds: number;
    estimated_minutes: number;
    started_at: string;
    filename: string;
    task_arn?: string;
    cluster_name?: string;
    // Completion fields (added by worker before exit)
    complete?: boolean;
    success?: boolean;
    error?: string;
}

export const getEstimate = async (filename: string): Promise<EstimateData> => {
    const headers = await getAuthHeaders();
    // Remove extension if present
    const filenameBase = filename.replace('.xlsx', '').replace('_filled', '');

    const response = await fetch(`${API_BASE_URL}/files/estimate/${encodeURIComponent(filenameBase)}`, {
        method: 'GET',
        headers: headers,
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `Failed to get estimate: ${response.statusText}`);
    }

    return await response.json();
};

export const checkFileExists = async (filepath: string): Promise<boolean> => {
    const headers = await getAuthHeaders();

    // Use encodeURI to preserve slashes but encode spaces
    // encodeURIComponent would encode slashes as %2F which breaks the path
    const response = await fetch(`${API_BASE_URL}/files/check/${encodeURI(filepath)}`, {
        method: 'GET',
        headers: headers,
    });

    if (!response.ok) {
        throw new Error(`Failed to check file: ${response.statusText}`);
    }

    const data = await response.json();
    return data.exists || false;
};

export interface ActiveJob {
    total_items: number;
    estimated_seconds: number;
    estimated_minutes: number;
    started_at: string;
    filename: string;
    task_arn?: string;
    cluster_name?: string;
    // Completion fields (added by worker before exit)
    complete?: boolean;
    success?: boolean;
    error?: string;
}

export const listActiveJobs = async (): Promise<ActiveJob[]> => {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE_URL}/files/active-jobs`, {
        method: 'GET',
        headers: headers,
    });

    if (!response.ok) {
        throw new Error(`Failed to list active jobs: ${response.statusText}`);
    }

    const data = await response.json();
    return data.active_jobs || [];
};

export const deleteEstimate = async (filename: string): Promise<void> => {
    const headers = await getAuthHeaders();
    const filenameBase = filename.replace('.xlsx', '').replace('_filled', '');

    const response = await fetch(`${API_BASE_URL}/files/estimate/${encodeURIComponent(filenameBase)}`, {
        method: 'DELETE',
        headers: headers,
    });

    if (!response.ok) {
        throw new Error(`Failed to delete estimate: ${response.statusText}`);
    }
};

/**
 * Delete a sheet (External API — async with polling)
 */
export const deleteSheet = async (sheetName: string): Promise<void> => {
    const deletionApiUrl = "https://auwdkyf4ka.execute-api.eu-west-1.amazonaws.com/prod";

    const headers = await getAuthHeaders();
    const encodedName = encodeURIComponent(sheetName);

    // 1. Fire DELETE → dispatcher returns 202 with deletion_id
    const response = await fetch(`${deletionApiUrl}/files/sheets/${encodedName}`, {
        method: 'DELETE',
        headers: headers,
    });

    if (!response.ok && response.status !== 202) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `Failed to delete sheet: ${response.statusText}`);
    }

    const data = await response.json();
    const deletionId = data.deletion_id;
    const bucketType = data.bucket_type || 'files';

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
