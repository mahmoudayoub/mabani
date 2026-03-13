const NON_JSON_PREVIEW_LENGTH = 160;

const formatBodyPreview = (body: string): string => {
    const flattened = body.replace(/\s+/g, " ").trim();
    if (!flattened) return "empty response body";
    if (flattened.length <= NON_JSON_PREVIEW_LENGTH) return flattened;
    return `${flattened.slice(0, NON_JSON_PREVIEW_LENGTH)}...`;
};

export const getDeletionApiBaseUrl = (): string => {
    const configuredUrl = import.meta.env.VITE_BOQ_DELETION_API_URL?.trim();

    if (!configuredUrl) {
        throw new Error(
            "BOQ deletion API URL is missing in this frontend build. Set VITE_BOQ_DELETION_API_URL and restart or rebuild the frontend."
        );
    }

    return configuredUrl.replace(/\/+$/, "");
};

export const readJsonResponse = async <T>(response: Response, context: string): Promise<T> => {
    const body = await response.text();

    if (!body) {
        return {} as T;
    }

    try {
        return JSON.parse(body) as T;
    } catch {
        throw new Error(
            `${context} returned non-JSON response (${response.status} ${response.statusText}) from ${response.url}: ${formatBodyPreview(body)}`
        );
    }
};
