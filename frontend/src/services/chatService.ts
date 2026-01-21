import { fetchAuthSession } from 'aws-amplify/auth';

// External allocation chatbot API URL
const CHAT_API_URL = 'https://zyt0q89ozg.execute-api.eu-west-1.amazonaws.com/prod';

export interface ChatMessage {
    role: 'user' | 'assistant';
    content: string;
    timestamp?: number;
}

// Price Code match
export interface PriceCodeMatch {
    code: string;
    description: string;
    category?: string;
    source: string;
    score: number;
}

// Unit Rate match
export interface UnitRateMatch {
    code: string;
    description: string;
    unit?: string;
    rate?: string;
    source: string;
    score: number;
}

export type ChatMatch = PriceCodeMatch | UnitRateMatch;

export interface ChatResponse {
    status: 'success' | 'clarification' | 'error';
    message: string;
    matches?: ChatMatch[];
}

/**
 * Get auth headers for API calls (optional - backend may not require auth)
 */
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
            'Content-Type': 'application/json',
        };
    }
};

/**
 * Send a message to the allocation chatbot
 * @param type - 'pricecode' or 'unitrate'
 * @param message - User's message
 * @param history - Conversation history
 */
export const sendChatMessage = async (
    type: 'pricecode' | 'unitrate',
    message: string,
    history: ChatMessage[] = []
): Promise<ChatResponse> => {
    const headers = await getAuthHeaders();

    const response = await fetch(`${CHAT_API_URL}/chat`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
            type,
            message,
            history: history.map(msg => ({
                role: msg.role,
                content: msg.content
            }))
        })
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.message || `Chat request failed: ${response.statusText}`);
    }

    return response.json();
};

/**
 * Health check for the chat API
 */
export const checkChatApiHealth = async (): Promise<boolean> => {
    try {
        const response = await fetch(`${CHAT_API_URL}/health`, {
            method: 'GET',
        });
        return response.ok;
    } catch {
        return false;
    }
};
