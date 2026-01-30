import React from 'react';
import ChatInterface from '../components/chat/ChatInterface';

const UnitRateChat: React.FC = () => {
    return (
        <ChatInterface
            type="unitrate"
            title="Unit Rate Assistant"
            placeholder="Ask about unit rates for specific items..."
            welcomeMessage="Hello! I can help you look up unit rates. Which item do you need a rate for?"
        />
    );
};

export default UnitRateChat;
