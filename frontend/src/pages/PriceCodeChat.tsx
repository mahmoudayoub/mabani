import React from 'react';
import ChatInterface from '../components/chat/ChatInterface';

const PriceCodeChat: React.FC = () => {
    return (
        <ChatInterface
            type="pricecode"
            title="Price Code Assistant"
            placeholder="Describe the work item to find its price code..."
            welcomeMessage="Hello! I can help you find price codes from the database. What work item are you looking for?"
        />
    );
};

export default PriceCodeChat;
