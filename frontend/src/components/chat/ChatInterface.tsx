import React, { useState, useRef, useEffect } from 'react';
import { sendChatMessage, ChatMessage, ChatMatch } from '../../services/chatService';

interface ChatInterfaceProps {
    type: 'pricecode' | 'unitrate';
    title: string;
    placeholder?: string;
    welcomeMessage?: string;
}

const ChatInterface: React.FC<ChatInterfaceProps> = ({
    type,
    title,
    placeholder = "Type your question...",
    welcomeMessage = "Hello! How can I help you today?"
}) => {
    const [messages, setMessages] = useState<ChatMessage[]>([
        { role: 'assistant', content: welcomeMessage, timestamp: Date.now() }
    ]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || isLoading) return;

        const userMessage: ChatMessage = {
            role: 'user',
            content: input.trim(),
            timestamp: Date.now()
        };

        setMessages(prev => [...prev, userMessage]);
        setInput('');
        setIsLoading(true);
        setError(null);

        try {
            const response = await sendChatMessage(type, userMessage.content, messages);

            const assistantMessage: ChatMessage = {
                role: 'assistant',
                content: response.message,
                timestamp: Date.now()
            };

            setMessages(prev => [...prev, assistantMessage]);

            // If there are matches, display them
            if (response.matches && response.matches.length > 0) {
                const matchesContent = formatMatches(response.matches);
                const matchesMessage: ChatMessage = {
                    role: 'assistant',
                    content: matchesContent,
                    timestamp: Date.now()
                };
                setMessages(prev => [...prev, matchesMessage]);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to send message');
            // Add error message to chat
            setMessages(prev => [...prev, {
                role: 'assistant',
                content: '⚠️ Sorry, I encountered an error. Please try again.',
                timestamp: Date.now()
            }]);
        } finally {
            setIsLoading(false);
        }
    };

    const formatMatches = (matches: ChatMatch[]): string => {
        return matches.map((match, index) => {
            let details = `**Match ${index + 1}**: ${match.code}\n`;
            details += `📝 ${match.description}\n`;

            // Type-specific fields
            if ('unit' in match && match.unit) {
                details += `📏 Unit: ${match.unit}\n`;
            }
            if ('rate' in match && match.rate) {
                details += `💰 Rate: ${match.rate}\n`;
            }
            if ('category' in match && match.category) {
                details += `📁 Category: ${match.category}\n`;
            }

            details += `📚 Source: ${match.source}\n`;
            details += `✅ Confidence: ${(match.score * 100).toFixed(1)}%`;

            return details;
        }).join('\n\n---\n\n');
    };

    return (
        <div className="flex flex-col h-[calc(100vh-200px)] bg-white rounded-lg shadow-lg">
            {/* Header */}
            <div className="px-6 py-4 border-b border-gray-200 bg-gradient-to-r from-primary-500 to-primary-600">
                <h2 className="text-xl font-semibold text-white">{title}</h2>
            </div>

            {/* Messages Area */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {messages.map((message, index) => (
                    <div
                        key={index}
                        className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                    >
                        <div
                            className={`max-w-[80%] rounded-lg px-4 py-3 ${message.role === 'user'
                                ? 'bg-primary-500 text-white'
                                : 'bg-gray-100 text-gray-800'
                                }`}
                        >
                            <p className="whitespace-pre-wrap text-sm">{message.content}</p>
                        </div>
                    </div>
                ))}

                {isLoading && (
                    <div className="flex justify-start">
                        <div className="bg-gray-100 rounded-lg px-4 py-3">
                            <div className="flex space-x-2">
                                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                            </div>
                        </div>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {/* Error Display */}
            {error && (
                <div className="px-4 py-2 bg-red-50 border-t border-red-200">
                    <p className="text-sm text-red-600">{error}</p>
                </div>
            )}

            {/* Input Area */}
            <form onSubmit={handleSubmit} className="p-4 border-t border-gray-200">
                <div className="flex space-x-4">
                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder={placeholder}
                        disabled={isLoading}
                        className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent disabled:bg-gray-100"
                    />
                    <button
                        type="submit"
                        disabled={isLoading || !input.trim()}
                        className="px-6 py-3 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
                    >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                        </svg>
                    </button>
                </div>
            </form>
        </div>
    );
};

export default ChatInterface;
