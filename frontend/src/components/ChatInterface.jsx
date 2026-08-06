import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import Markdown from './Markdown';
import Stage1 from './Stage1';
import Stage2 from './Stage2';
import Stage3 from './Stage3';
import { downloadConversationMarkdown } from '../utils/exportConversation';
import { shortModelName } from '../utils/modelDisplay';
import './ChatInterface.css';

const TEXTAREA_MIN_HEIGHT = 52;
const TEXTAREA_MAX_HEIGHT = 300;

// Below this many characters a question is too short to classify usefully -
// skip the recommendation call entirely rather than fire on every keystroke.
const RECOMMENDATION_MIN_LENGTH = 12;
const RECOMMENDATION_DEBOUNCE_MS = 600;

export default function ChatInterface({
  conversation,
  onSendMessage,
  onCancelMessage,
  onRetry,
  canRetry,
  isLoading,
  onApplyRecommendation,
}) {
  const [input, setInput] = useState('');
  const [recommendation, setRecommendation] = useState(null);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [conversation]);

  // Auto-grow the textarea to fit its content instead of a fixed row count.
  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    textarea.style.height = 'auto';
    const nextHeight = Math.min(
      Math.max(textarea.scrollHeight, TEXTAREA_MIN_HEIGHT),
      TEXTAREA_MAX_HEIGHT
    );
    textarea.style.height = `${nextHeight}px`;
  }, [input]);

  // As the question is typed, suggest council models based on how they've
  // actually performed on similar past questions (debounced; skipped for
  // short/empty input). Never fabricates a suggestion - only shows one
  // when the backend found real history to back it.
  useEffect(() => {
    const trimmed = input.trim();
    if (trimmed.length < RECOMMENDATION_MIN_LENGTH || isLoading) {
      return undefined;
    }

    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const result = await api.recommendModels(trimmed, controller.signal);
        setRecommendation(
          result.recommended && result.recommended.length > 0 ? result : null
        );
      } catch (error) {
        if (error.name !== 'AbortError') {
          console.error('Failed to get model recommendations:', error);
        }
      }
    }, RECOMMENDATION_DEBOUNCE_MS);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [input, isLoading]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (input.trim() && !isLoading) {
      onSendMessage(input);
      setInput('');
      setRecommendation(null);
    }
  };

  const handleKeyDown = (e) => {
    // Submit on Enter (without Shift)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  if (!conversation) {
    return (
      <div className="chat-interface">
        <div className="empty-state">
          <h2>Welcome to LLM Council</h2>
          <p>Create a new conversation to get started</p>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-interface">
      <div className="messages-container">
        {conversation.messages.length === 0 ? (
          <div className="empty-state">
            <h2>Start a conversation</h2>
            <p>Ask a question to consult the LLM Council</p>
          </div>
        ) : (
          <>
            <div className="conversation-toolbar">
              <button
                type="button"
                className="export-button"
                onClick={() => downloadConversationMarkdown(conversation)}
              >
                ⤓ Export as Markdown
              </button>
            </div>

            {conversation.messages.map((msg, index) => (
              <div key={index} className="message-group">
                {msg.role === 'user' ? (
                  <div className="user-message">
                    <div className="message-label">You</div>
                    <div className="message-content">
                      <div className="markdown-content">
                        <Markdown>{msg.content}</Markdown>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="assistant-message">
                    <div className="message-label">LLM Council</div>

                    {/* Stage 1 */}
                    {msg.loading?.stage1 && (
                      <div className="stage-loading">
                        <div className="spinner"></div>
                        <span>Running Stage 1: Collecting individual responses...</span>
                      </div>
                    )}
                    {msg.stage1 && <Stage1 responses={msg.stage1} />}

                    {/* Stage 2 */}
                    {msg.loading?.stage2 && (
                      <div className="stage-loading">
                        <div className="spinner"></div>
                        <span>Running Stage 2: Peer rankings...</span>
                      </div>
                    )}
                    {msg.stage2 && (
                      <Stage2
                        rankings={msg.stage2}
                        labelToModel={msg.metadata?.label_to_model}
                        aggregateRankings={msg.metadata?.aggregate_rankings}
                      />
                    )}

                    {/* Stage 3 */}
                    {msg.loading?.stage3 && (
                      <div className="stage-loading">
                        <div className="spinner"></div>
                        <span>Running Stage 3: Final synthesis...</span>
                      </div>
                    )}
                    {msg.stage3 && <Stage3 finalResponse={msg.stage3} />}
                  </div>
                )}
              </div>
            ))}
          </>
        )}

        {isLoading && (
          <div className="loading-indicator">
            <div className="spinner"></div>
            <span>Consulting the council...</span>
            <button
              type="button"
              className="cancel-button"
              onClick={onCancelMessage}
            >
              Cancel
            </button>
          </div>
        )}

        {!isLoading && canRetry && (
          <div className="retry-banner">
            <span>That request didn't complete.</span>
            <button type="button" className="retry-button" onClick={onRetry}>
              ↻ Retry
            </button>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {recommendation
        && input.trim().length >= RECOMMENDATION_MIN_LENGTH
        && !isLoading && (
        <div className="suggestion-banner">
          <span>
            💡 Based on {recommendation.based_on_conversations}{' '}
            similar past {recommendation.based_on_conversations === 1 ? 'conversation' : 'conversations'},{' '}
            <strong>{recommendation.recommended.map(shortModelName).join(', ')}</strong>
            {' '}{recommendation.recommended.length === 1 ? 'has' : 'have'} ranked best
            for {recommendation.category} questions in your council.
          </span>
          <div className="suggestion-actions">
            <button
              type="button"
              className="suggestion-apply-btn"
              onClick={() => {
                onApplyRecommendation(recommendation.recommended);
                setRecommendation(null);
              }}
            >
              Use these models
            </button>
            <button
              type="button"
              className="suggestion-dismiss-btn"
              onClick={() => setRecommendation(null)}
              aria-label="Dismiss suggestion"
            >
              ×
            </button>
          </div>
        </div>
      )}

      <form className="input-form" onSubmit={handleSubmit}>
        <textarea
          ref={textareaRef}
          className="message-input"
          placeholder="Ask your question... (Shift+Enter for new line, Enter to send)"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isLoading}
          rows={1}
        />
        {isLoading ? (
          <button
            type="button"
            className="send-button send-button--cancel"
            onClick={onCancelMessage}
          >
            Stop
          </button>
        ) : (
          <button
            type="submit"
            className="send-button"
            disabled={!input.trim()}
          >
            Send
          </button>
        )}
      </form>
    </div>
  );
}
