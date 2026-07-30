import React, { useState, useRef, useEffect } from 'react';
import api from '../lib/api';

interface Message {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  timestamp: string;
}

interface ChatbotWidgetProps {
  currentAppId?: number;
}

export const ChatbotWidget: React.FC<ChatbotWidgetProps> = ({ currentAppId }) => {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [inputMessage, setInputMessage] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      sender: 'assistant',
      text: "👋 Hi! I'm your **QA AI Assistant**. Ask me anything about your registered applications, test suites, bug reports, or platform usage!",
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
  ]);
  const [suggestions, setSuggestions] = useState<string[]>([
    "Summary of my apps",
    "Show my notifications",
    "What is my team access?",
    "What are my latest bugs?"
  ]);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
    }
  }, [messages, isOpen, loading]);

  const handleSendMessage = async (textToSend?: string) => {
    const text = (textToSend || inputMessage).trim();
    if (!text || loading) return;

    const userMsg: Message = {
      id: `user-${Date.now()}`,
      sender: 'user',
      text: text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setMessages(prev => [...prev, userMsg]);
    if (!textToSend) setInputMessage('');
    setLoading(true);

    try {
      const response = await api.post('chatbot/query/', {
        message: text,
        app_id: currentAppId
      });

      const responseData = response.data as any;

      const assistantMsg: Message = {
        id: `assistant-${Date.now()}`,
        sender: 'assistant',
        text: responseData?.response || "I have analyzed your QA workspace data.",
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };

      setMessages(prev => [...prev, assistantMsg]);

      if (Array.isArray(responseData?.suggestions) && responseData.suggestions.length > 0) {
        setSuggestions(responseData.suggestions);
      }
    } catch (err: any) {
      console.error("Chatbot API Error:", err);
      const errorMsg: Message = {
        id: `err-${Date.now()}`,
        sender: 'assistant',
        text: err?.response?.data?.detail || "⚠️ Could not connect to the QA AI Assistant. Please check your connection and try again.",
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const clearChat = () => {
    setMessages([
      {
        id: 'welcome-reset',
        sender: 'assistant',
        text: "Conversation cleared. How can I help you with your QA testing today?",
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }
    ]);
  };

  // Basic markdown text renderer helper (supports **bold**, *italic*, `code`, and newlines)
  const renderFormattedText = (rawText: string) => {
    const lines = rawText.split('\n');
    return lines.map((line, idx) => {
      let formattedLine = line
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`(.*?)`/g, '<code class="chat-code">$1</code>');

      if (line.startsWith('- ')) {
        return (
          <li key={idx} dangerouslySetInnerHTML={{ __html: formattedLine.substring(2) }} className="chat-list-item" />
        );
      }
      if (line.startsWith('### ')) {
        return <h4 key={idx} dangerouslySetInnerHTML={{ __html: formattedLine.substring(4) }} className="chat-heading" />;
      }
      return <p key={idx} dangerouslySetInnerHTML={{ __html: formattedLine }} className="chat-p" />;
    });
  };

  return (
    <div className="chatbot-widget-container">
      {/* Floating Toggle Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="chatbot-trigger-btn"
          title="Open QA AI Assistant"
        >
          <div className="chatbot-trigger-icon">💬</div>
          <span className="chatbot-trigger-label">QA AI Assistant</span>
          <span className="chatbot-pulse-dot" />
        </button>
      )}

      {/* Chatbot Window */}
      {isOpen && (
        <div className="chatbot-window">
          {/* Header */}
          <div className="chatbot-header">
            <div className="chatbot-header-title">
              <div className="chatbot-avatar">🤖</div>
              <div>
                <div className="chatbot-name">QA AI Assistant</div>
                <div className="chatbot-status">
                  <span className="status-dot-green" /> Application Scoped Context
                </div>
              </div>
            </div>
            <div className="chatbot-header-actions">
              <button onClick={clearChat} className="chatbot-icon-btn" title="Clear Chat">
                🗑️
              </button>
              <button onClick={() => setIsOpen(false)} className="chatbot-icon-btn" title="Close Chat">
                ✖
              </button>
            </div>
          </div>

          {/* Messages Area */}
          <div className="chatbot-messages">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`chat-bubble-container ${msg.sender === 'user' ? 'user-align' : 'assistant-align'}`}
              >
                {msg.sender === 'assistant' && <div className="bubble-avatar">🤖</div>}
                <div className={`chat-bubble ${msg.sender}`}>
                  <div className="chat-bubble-content">
                    {renderFormattedText(msg.text)}
                  </div>
                  <div className="chat-timestamp">{msg.timestamp}</div>
                </div>
              </div>
            ))}

            {loading && (
              <div className="chat-bubble-container assistant-align">
                <div className="bubble-avatar">🤖</div>
                <div className="chat-bubble assistant loading-bubble">
                  <div className="typing-indicator">
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Quick Suggestions Chips */}
          {suggestions.length > 0 && !loading && (
            <div className="chatbot-suggestions">
              {suggestions.map((chip, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSendMessage(chip)}
                  className="suggestion-chip"
                >
                  {chip}
                </button>
              ))}
            </div>
          )}

          {/* Input Area */}
          <div className="chatbot-input-container">
            <input
              type="text"
              className="chatbot-input"
              placeholder="Ask about apps, test cases, bugs..."
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
            />
            <button
              onClick={() => handleSendMessage()}
              className="chatbot-send-btn"
              disabled={!inputMessage.trim() || loading}
            >
              ➔
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
