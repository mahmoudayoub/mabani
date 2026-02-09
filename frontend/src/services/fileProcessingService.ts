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

export const deleteSheet = async (sheetName: string): Promise<void> => {
    // HARDCODED External API URL for Datasheet Deletion
    const deletionApiUrl = "https://auwdkyf4ka.execute-api.eu-west-1.amazonaws.com/prod/";

    // If using external API directly, it might not need auth headers if public?
    // User said "backend is configured to accept it... but currently does not validate it (Public endpoint)"
    // So sending headers is safe.
    const headers = await getAuthHeaders();

    // Use encodeURIComponent for the sheet name in the path
    const encodedName = encodeURIComponent(sheetName);

    // Construct URL. If External, path is /files/sheets/{name} appended to Base.
    // Ensure slash handling.
    const baseUrl = deletionApiUrl.endsWith('/') ? deletionApiUrl.slice(0, -1) : deletionApiUrl;

    const response = await fetch(`${baseUrl}/files/sheets/${encodedName}`, {
        method: 'DELETE',
        headers: headers,
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `Failed to delete sheet: ${response.statusText}`);
    }
};



