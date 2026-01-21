import React from 'react';
import ChatInterface from '../components/chat/ChatInterface';

const PriceCodeChat: React.FC = () => {
    return (
        <div className="px-4 py-6 sm:px-6 lg:px-8">
            <div className="mb-6">
                <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 mb-2">
                    Price Code Assistant
                </h1>
                <p className="text-sm sm:text-base text-gray-600">
                    Ask questions about price codes for construction materials
                </p>
            </div>

            <ChatInterface
                type="pricecode"
                title="Price Code Lookup"
                placeholder="e.g., What is the price code for 25mm copper pipe?"
                welcomeMessage="Hello! I can help you find price codes for construction materials. Describe the item you're looking for, including details like material, dimensions, and specifications."
            />
        </div>
    );
};

export default PriceCodeChat;
