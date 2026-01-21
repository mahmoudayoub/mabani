import React from 'react';
import ChatInterface from '../components/chat/ChatInterface';

const UnitRateChat: React.FC = () => {
    return (
        <div className="px-4 py-6 sm:px-6 lg:px-8">
            <div className="mb-6">
                <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 mb-2">
                    Unit Rate Assistant
                </h1>
                <p className="text-sm sm:text-base text-gray-600">
                    Ask questions about unit rate codes for construction work items
                </p>
            </div>

            <ChatInterface
                type="unitrate"
                title="Unit Rate Lookup"
                placeholder="e.g., What is the unit rate for plastering an internal wall?"
                welcomeMessage="Hello! I can help you find unit rate codes for construction work items. Describe the work you're looking for, including the trade, type of work, and any relevant details."
            />
        </div>
    );
};

export default UnitRateChat;
