import { useState } from 'react';
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


export default function Sidebar({
  conversations,
  currentConversationId,
  onSelectConversation,
  onNewConversation,
  availableModels,
  selectedModels,
  chairmanModel,
  onToggleModel,
  onChairmanChange,
  onRefreshModels,
  modelsLoading,
  modelError,
  selectionDisabled,
}) {
  const [modelsOpen, setModelsOpen] = useState(true);

  return (
    <aside className="sidebar">
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
              <button
                type="button"
                className="refresh-models-btn"
                onClick={onRefreshModels}
                disabled={modelsLoading || selectionDisabled}
              >
                {modelsLoading ? 'Scanning…' : 'Refresh'}
              </button>
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
          </div>
        )}
      </section>

      <div className="conversation-section-label">Conversations</div>
      <nav className="conversation-list" aria-label="Conversations">
        {conversations.length === 0 ? (
          <div className="no-conversations">
            <span className="no-conversations-icon">◇</span>
            No conversations yet
          </div>
        ) : (
          conversations.map((conversation) => (
            <button
              key={conversation.id}
              type="button"
              className={`conversation-item ${
                conversation.id === currentConversationId ? 'active' : ''
              }`}
              onClick={() => onSelectConversation(conversation.id)}
            >
              <span className="conversation-title">
                {conversation.title || 'New Conversation'}
              </span>
              <span className="conversation-meta">
                {conversation.message_count} messages
              </span>
            </button>
          ))
        )}
      </nav>
    </aside>
  );
}

