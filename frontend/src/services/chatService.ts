import { fetchAuthSession } from 'aws-amplify/auth';

// External allocation chatbot API URL
const CHAT_API_URL = 'https://zyt0q89ozg.execute-api.eu-west-1.amazonaws.com/prod';

export interface ChatMessage {
    role: 'user' | 'assistant';
    content: string;
    timestamp?: number;
}

// Price Code match object
export interface PriceCodeMatch {
    code: string;
    description: string;
    match_type: 'exact' | 'high';
}

// Price Code reference object
export interface PriceCodeReference {
    source_file: string;
    sheet_name: string;
    category: string;
    row_number: number;
}

// Unit Rate match object
export interface UnitRateMatch {
    item_code: string;
    description: string;
    rate: number | string;
    unit: string;
    match_type: 'exact' | 'close';
}

// Unit Rate reference object
export interface UnitRateReference {
    sheet_name: string;
    row_number: number;
    category_path: string;
    parent: string;
    grandparent: string;
}

// Extended types for the matches array (self-contained items)
export interface ExtendedPriceCodeMatch extends PriceCodeMatch {
    reference: PriceCodeReference;
    reasoning: string;
}

export interface ExtendedUnitRateMatch extends UnitRateMatch {
    reference: UnitRateReference;
    reasoning: string;
}

// Union types for match and reference
export type ChatMatch = PriceCodeMatch | UnitRateMatch;
export type ChatReference = PriceCodeReference | UnitRateReference;
export type ExtendedChatMatch = ExtendedPriceCodeMatch | ExtendedUnitRateMatch;

export interface ChatResponse {
    status: 'success' | 'no_match' | 'clarification' | 'error';
    message: string;
    match?: ChatMatch;        // Backward compatibility
    reference?: ChatReference;// Backward compatibility
    reasoning?: string;       // Backward compatibility
    matches?: ExtendedChatMatch[]; // New field for multiple matches
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
