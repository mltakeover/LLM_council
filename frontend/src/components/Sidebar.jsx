import { useState } from 'react';
import CouncilPresets from './CouncilPresets';
import ProviderStatus from './ProviderStatus';
import './Sidebar.css';


function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return null;
  const gigabytes = bytes / (1024 ** 3);
  return `${gigabytes.toFixed(gigabytes >= 10 ? 0 : 1)} GB`;
}


function providerLabel(provider) {
  const labels = {
    openai: 'OpenAI',
    anthropic: 'Anthropic',
    google: 'Gemini',
    xai: 'xAI',
    ollama: 'Ollama',
  };
  return labels[provider] || provider;
}


function ConversationItem({
  conversation,
  isActive,
  onSelect,
  onDelete,
  onRename,
}) {
  const [isRenaming, setIsRenaming] = useState(false);
  const [draftTitle, setDraftTitle] = useState(conversation.title || '');

  const startRenaming = (event) => {
    event.stopPropagation();
    setDraftTitle(conversation.title || '');
    setIsRenaming(true);
  };

  const commitRename = () => {
    const trimmed = draftTitle.trim();
    setIsRenaming(false);
    if (trimmed && trimmed !== conversation.title) {
      onRename(conversation.id, trimmed);
    }
  };

  const handleRenameKeyDown = (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      commitRename();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      setIsRenaming(false);
    }
  };

  const handleDelete = (event) => {
    event.stopPropagation();
    if (window.confirm(`Delete "${conversation.title || 'this conversation'}"? This cannot be undone.`)) {
      onDelete(conversation.id);
    }
  };

  return (
    <div className={`conversation-item ${isActive ? 'active' : ''}`}>
      <button
        type="button"
        className="conversation-select"
        onClick={() => onSelect(conversation.id)}
      >
        {isRenaming ? (
          <input
            type="text"
            className="conversation-rename-input"
            value={draftTitle}
            autoFocus
            onClick={(event) => event.stopPropagation()}
            onChange={(event) => setDraftTitle(event.target.value)}
            onBlur={commitRename}
            onKeyDown={handleRenameKeyDown}
          />
        ) : (
          <span className="conversation-title">
            {conversation.title || 'New Conversation'}
          </span>
        )}
        <span className="conversation-meta">
          {conversation.message_count} messages
        </span>
      </button>

      {!isRenaming && (
        <div className="conversation-actions">
          <button
            type="button"
            className="conversation-action-btn"
            onClick={startRenaming}
            aria-label="Rename conversation"
            title="Rename"
          >
            ✎
          </button>
          <button
            type="button"
            className="conversation-action-btn conversation-action-btn--danger"
            onClick={handleDelete}
            aria-label="Delete conversation"
            title="Delete"
          >
            🗑
          </button>
        </div>
      )}
    </div>
  );
}


export default function Sidebar({
  conversations,
  currentConversationId,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
  onRenameConversation,
  availableModels,
  selectedModels,
  chairmanModel,
  reviewProfiles,
  reviewProfile,
  includeContext,
  onToggleModel,
  onChairmanChange,
  onReviewProfileChange,
  onIncludeContextChange,
  onApplyPreset,
  onRefreshModels,
  modelsLoading,
  modelError,
  selectionDisabled,
  open,
}) {
  const [modelsOpen, setModelsOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [providerStatusOpen, setProviderStatusOpen] = useState(false);

  const filteredConversations = searchQuery.trim()
    ? conversations.filter((conversation) => (
        (conversation.title || 'New Conversation')
          .toLowerCase()
          .includes(searchQuery.trim().toLowerCase())
      ))
    : conversations;

  return (
    <aside className={`sidebar ${open ? 'sidebar--open' : ''}`}>
      <div className="sidebar-header">
        <div className="sidebar-brand-row">
          <div>
            <div className="sidebar-kicker">MULTI-MODEL REVIEW</div>
            <h1>LLM Council</h1>
          </div>
          <span className="sidebar-live-dot" title="Local application" />
        </div>

        <button
          className="new-conversation-btn"
          onClick={onNewConversation}
          type="button"
        >
          <span aria-hidden="true">＋</span>
          New Conversation
        </button>
      </div>

      <section className="model-selector">
        <button
          className="model-selector-heading"
          type="button"
          onClick={() => setModelsOpen((open) => !open)}
          aria-expanded={modelsOpen}
        >
          <span>
            Council Models
            <span className="selected-count">{selectedModels.length}</span>
          </span>
          <span aria-hidden="true">{modelsOpen ? '−' : '+'}</span>
        </button>

        {modelsOpen && (
          <div className="model-selector-body">
            <div className="model-selector-actions">
              <span>Choose members for the next question</span>
              <div className="model-action-buttons">
                <button
                  type="button"
                  className="provider-status-btn"
                  onClick={() => setProviderStatusOpen(true)}
                >
                  Status
                </button>
                <button
                  type="button"
                  className="refresh-models-btn"
                  onClick={onRefreshModels}
                  disabled={modelsLoading || selectionDisabled}
                >
                  {modelsLoading ? 'Scanning…' : 'Refresh'}
                </button>
              </div>
            </div>

            {modelError && (
              <div className="model-error" role="status">
                {modelError}
              </div>
            )}

            <div className="model-options" aria-label="Available models">
              {availableModels.length === 0 && !modelsLoading ? (
                <div className="model-empty">No selectable models found</div>
              ) : (
                availableModels.map((model) => {
                  const selected = selectedModels.includes(model.id);
                  const onlySelected = selected && selectedModels.length === 1;
                  const size = formatBytes(model.size);

                  return (
                    <label
                      className={`model-option ${
                        selected ? 'selected' : ''
                      } ${!model.selectable ? 'disabled' : ''}`}
                      key={model.id}
                      title={
                        model.selectable
                          ? model.id
                          : 'Ollama cloud models are excluded from local selection'
                      }
                    >
                      <input
                        type="checkbox"
                        checked={selected}
                        onChange={() => onToggleModel(model.id)}
                        disabled={
                          selectionDisabled
                          || !model.selectable
                          || onlySelected
                        }
                      />

                      <span className="model-option-content">
                        <span className="model-option-name">
                          {model.name}
                        </span>
                        <span className="model-option-meta">
                          <span className={`provider-pill ${model.provider}`}>
                            {providerLabel(model.provider)}
                          </span>
                          <span className={`location-pill ${
                            model.is_local ? 'local' : 'cloud'
                          }`}>
                            {model.is_local ? 'Local' : 'Cloud'}
                          </span>
                          {size && <span>{size}</span>}
                          {model.quantization && (
                            <span>{model.quantization}</span>
                          )}
                        </span>
                      </span>
                    </label>
                  );
                })
              )}
            </div>

            <label className="chairman-field">
              <span>Chairman</span>
              <select
                value={chairmanModel || ''}
                onChange={(event) => onChairmanChange(event.target.value)}
                disabled={selectionDisabled || selectedModels.length === 0}
              >
                {selectedModels.map((modelId) => (
                  <option key={modelId} value={modelId}>
                    {modelId.split(':').slice(1).join(':')}
                  </option>
                ))}
              </select>
            </label>

            <div className="review-settings">
              <label className="chairman-field">
                <span>Review profile</span>
                <select
                  value={reviewProfile}
                  onChange={(event) => onReviewProfileChange(event.target.value)}
                  disabled={selectionDisabled}
                >
                  {reviewProfiles.map((profile) => (
                    <option key={profile.id} value={profile.id}>
                      {profile.name}
                    </option>
                  ))}
                </select>
              </label>
              <p className="review-profile-description">
                {reviewProfiles.find((profile) => profile.id === reviewProfile)?.description
                  || 'Choose the perspective used by council members and the Chairman.'}
              </p>
              <label className="context-toggle">
                <input
                  type="checkbox"
                  checked={includeContext}
                  onChange={(event) => onIncludeContextChange(event.target.checked)}
                  disabled={selectionDisabled}
                />
                <span>
                  Use conversation context
                  <small>Include recent messages in the next review</small>
                </span>
              </label>
            </div>

            <CouncilPresets
              models={availableModels}
              selectedModels={selectedModels}
              chairmanModel={chairmanModel}
              reviewProfile={reviewProfile}
              includeContext={includeContext}
              disabled={selectionDisabled}
              onApply={onApplyPreset}
            />
          </div>
        )}
      </section>

      <div className="conversation-section-label">Conversations</div>

      {conversations.length > 0 && (
        <div className="conversation-search">
          <input
            type="search"
            placeholder="Search conversations…"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            aria-label="Search conversations"
          />
        </div>
      )}

      <nav className="conversation-list" aria-label="Conversations">
        {conversations.length === 0 ? (
          <div className="no-conversations">
            <span className="no-conversations-icon">◇</span>
            No conversations yet
          </div>
        ) : filteredConversations.length === 0 ? (
          <div className="no-conversations">
            No conversations match &ldquo;{searchQuery}&rdquo;
          </div>
        ) : (
          filteredConversations.map((conversation) => (
            <ConversationItem
              key={conversation.id}
              conversation={conversation}
              isActive={conversation.id === currentConversationId}
              onSelect={onSelectConversation}
              onDelete={onDeleteConversation}
              onRename={onRenameConversation}
            />
          ))
        )}
      </nav>
      {providerStatusOpen && (
        <ProviderStatus
          models={availableModels}
          onRefresh={onRefreshModels}
          onClose={() => setProviderStatusOpen(false)}
        />
      )}
    </aside>
  );
}
