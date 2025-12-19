
import { API_BASE_URL, getAuthHeaders } from '../utils/api';

export const configService = {
    // Get configuration options
    getConfig: async (type: string): Promise<string[]> => {
        try {
            const headers = await getAuthHeaders();
            const response = await fetch(`${API_BASE_URL}/config/${type}`, {
                method: "GET",
                headers
            });

            if (!response.ok) {
                throw new Error("Failed to fetch config");
            }

            const data = await response.json();
            return data.options || [];
        } catch (error) {
            console.error(`Error fetching config for ${type}:`, error);
            return [];
        }
    },

    // Update configuration options
    updateConfig: async (type: string, options: string[]): Promise<void> => {
        try {
            const headers = await getAuthHeaders();
            const response = await fetch(`${API_BASE_URL}/config/${type}`, {
                method: "PUT",
                headers,
                body: JSON.stringify({ options })
            });

            if (!response.ok) {
                throw new Error("Failed to update config");
            }
        } catch (error) {
            console.error(`Error updating config for ${type}:`, error);
            throw error;
        }
    }
};
