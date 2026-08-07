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
const USAGE_DEBOUNCE_MS = 450;
const MAX_SELECTED_DOCUMENTS = 5;
const DOCUMENT_ACCEPT = '.txt,.md,.py,.js,.jsx,.ts,.tsx,.json,.yaml,.yml,.toml,.csv,.sql,.xml,.html,.css,.pdf,.docx';

export default function ChatInterface({
  conversation,
  onSendMessage,
  onCancelMessage,
  onRetry,
  canRetry,
  isLoading,
  onApplyRecommendation,
  selectedModels,
  chairmanModel,
  reviewProfile,
  includeContext,
  requiresCloudConfirmation,
  cloudModelNames,
  cloudPrivacyConfirmed,
  onCloudPrivacyConfirmed,
}) {
  const [input, setInput] = useState('');
  const [recommendation, setRecommendation] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [documentError, setDocumentError] = useState(null);
  const [usageEstimate, setUsageEstimate] = useState(null);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [conversation]);

  useEffect(() => {
    let active = true;
    if (!conversation?.id) {
      return undefined;
    }

    api.listDocuments(conversation.id)
      .then((payload) => {
        if (active) setDocuments(payload.documents || []);
      })
      .catch((error) => {
        if (active) setDocumentError(error.message);
      });
    return () => {
      active = false;
    };
  }, [conversation?.id]);

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

  useEffect(() => {
    if (!conversation?.id || isLoading || (!input.trim() && selectedDocumentIds.length === 0)) {
      return undefined;
    }

    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        setUsageEstimate(await api.estimateUsage(
          conversation.id,
          input.trim(),
          {
            models: selectedModels,
            chairmanModel,
            reviewProfile,
            includeContext,
            documentIds: selectedDocumentIds,
          },
          controller.signal,
        ));
      } catch (error) {
        if (error.name !== 'AbortError') {
          console.error('Failed to estimate usage:', error);
        }
      }
    }, USAGE_DEBOUNCE_MS);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [
    conversation?.id,
    input,
    selectedDocumentIds,
    selectedModels,
    chairmanModel,
    reviewProfile,
    includeContext,
    isLoading,
  ]);

  const selectedDocuments = documents.filter((document) => (
    selectedDocumentIds.includes(document.id)
  ));
  const privacyReady = !requiresCloudConfirmation || cloudPrivacyConfirmed;

  const handleDocumentUpload = async (event) => {
    const files = Array.from(event.target.files || []);
    event.target.value = '';
    if (!conversation?.id || files.length === 0) return;
    if (selectedDocumentIds.length + files.length > MAX_SELECTED_DOCUMENTS) {
      setDocumentError(`Select no more than ${MAX_SELECTED_DOCUMENTS} documents per review.`);
      return;
    }

    setUploading(true);
    setDocumentError(null);
    try {
      const uploaded = [];
      for (const file of files) {
        uploaded.push(await api.uploadDocument(conversation.id, file));
      }
      setDocuments((previous) => [...previous, ...uploaded]);
      setSelectedDocumentIds((previous) => [
        ...previous,
        ...uploaded.map((document) => document.id),
      ]);
    } catch (error) {
      setDocumentError(error.message);
    } finally {
      setUploading(false);
    }
  };

  const toggleDocument = (documentId) => {
    if (isLoading) return;
    setSelectedDocumentIds((previous) => {
      if (previous.includes(documentId)) {
        return previous.filter((id) => id !== documentId);
      }
      if (previous.length >= MAX_SELECTED_DOCUMENTS) {
        setDocumentError(`Select no more than ${MAX_SELECTED_DOCUMENTS} documents per review.`);
        return previous;
      }
      setDocumentError(null);
      return [...previous, documentId];
    });
  };

  const removeDocument = async (documentId) => {
    if (!conversation?.id || isLoading) return;
    try {
      await api.deleteDocument(conversation.id, documentId);
      setDocuments((previous) => previous.filter((document) => document.id !== documentId));
      setSelectedDocumentIds((previous) => previous.filter((id) => id !== documentId));
    } catch (error) {
      setDocumentError(error.message);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (input.trim() && !isLoading && privacyReady) {
      onSendMessage(input, selectedDocuments);
      setInput('');
      setSelectedDocumentIds([]);
      setUsageEstimate(null);
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
                      {msg.documents?.length > 0 && (
                        <div className="message-documents">
                          {msg.documents.map((document) => (
                            <span key={document.id}>▤ {document.filename}</span>
                          ))}
                        </div>
                      )}
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

      {requiresCloudConfirmation && (
        <label className="privacy-confirmation">
          <input
            type="checkbox"
            checked={cloudPrivacyConfirmed}
            onChange={(event) => onCloudPrivacyConfirmed(event.target.checked)}
            disabled={isLoading}
          />
          <span>
            <strong>Confirm cloud processing</strong>
            This review will send the prompt and selected documents to{' '}
            {cloudModelNames.join(', ')}. Your provider account settings govern retention and training.
          </span>
        </label>
      )}

      <form className="input-form" onSubmit={handleSubmit}>
        <div className="composer-tools">
          <label className={`file-upload-button ${uploading ? 'disabled' : ''}`}>
            <input
              type="file"
              accept={DOCUMENT_ACCEPT}
              multiple
              onChange={handleDocumentUpload}
              disabled={isLoading || uploading}
            />
            {uploading ? 'Uploading…' : '＋ Add files'}
          </label>
          {usageEstimate && (input.trim() || selectedDocumentIds.length > 0) && (
            <span className="usage-estimate" title={usageEstimate.caveat}>
              ≈ {usageEstimate.estimated_source_tokens.toLocaleString()} input tokens ·{' '}
              {usageEstimate.estimated_calls.total} model calls
              {usageEstimate.chunked_review ? ' · chunked review' : ''}
            </span>
          )}
        </div>

        {documents.length > 0 && (
          <div className="document-picker" aria-label="Conversation documents">
            {documents.map((document) => {
              const selected = selectedDocumentIds.includes(document.id);
              return (
                <span className={`document-chip ${selected ? 'selected' : ''}`} key={document.id}>
                  <button
                    type="button"
                    onClick={() => toggleDocument(document.id)}
                    disabled={isLoading}
                    title={`${document.character_count.toLocaleString()} characters · ${document.chunk_count} chunks`}
                  >
                    {selected ? '✓' : '○'} {document.filename}
                  </button>
                  <button
                    type="button"
                    className="document-delete"
                    onClick={() => removeDocument(document.id)}
                    disabled={isLoading}
                    aria-label={`Delete ${document.filename}`}
                  >
                    ×
                  </button>
                </span>
              );
            })}
          </div>
        )}
        {documentError && <div className="document-error" role="alert">{documentError}</div>}

        <div className="composer-row">
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
              disabled={!input.trim() || !privacyReady}
              title={!privacyReady ? 'Confirm cloud processing before sending' : undefined}
            >
              Send
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
