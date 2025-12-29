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
