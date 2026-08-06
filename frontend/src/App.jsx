import { useEffect, useRef, useState } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import CouncilFlow from './components/CouncilFlow';
import { api } from './api';
import './App.css';


const SELECTED_MODELS_KEY = 'llm-council:selected-models';
const CHAIRMAN_MODEL_KEY = 'llm-council:chairman-model';


function createProgress(models, chairmanModel, phase = 'ready') {
  return {
    phase,
    models: models.map((id) => ({
      id,
      stage1: 'pending',
      stage2: 'pending',
    })),
    chairman: {
      id: chairmanModel,
      stage3: 'pending',
    },
    error: null,
  };
}


function App() {
  const [conversations, setConversations] = useState([]);
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [currentConversation, setCurrentConversation] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  const [availableModels, setAvailableModels] = useState([]);
  const [selectedModels, setSelectedModels] = useState([]);
  const [chairmanModel, setChairmanModel] = useState(null);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [modelError, setModelError] = useState(null);
  const [councilProgress, setCouncilProgress] = useState(
    createProgress([], null)
  );
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [lastFailedContent, setLastFailedContent] = useState(null);

  const abortControllerRef = useRef(null);

  useEffect(() => {
    loadConversations();
    loadModels();
  }, []);

  useEffect(() => {
    if (currentConversationId) {
      loadConversation(currentConversationId);
    }
  }, [currentConversationId]);

  const loadConversations = async () => {
    try {
      setConversations(await api.listConversations());
    } catch (error) {
      console.error('Failed to load conversations:', error);
    }
  };

  const loadModels = async () => {
    setModelsLoading(true);
    setModelError(null);

    try {
      const catalog = await api.getModels();
      const selectableIds = catalog.models
        .filter((model) => model.selectable)
        .map((model) => model.id);
      const selectableSet = new Set(selectableIds);

      let savedModels = [];
      try {
        savedModels = JSON.parse(
          localStorage.getItem(SELECTED_MODELS_KEY) || '[]'
        );
      } catch {
        savedModels = [];
      }

      const restoredModels = Array.isArray(savedModels)
        ? savedModels.filter((model) => selectableSet.has(model))
        : [];

      const nextModels = restoredModels.length > 0
        ? restoredModels
        : catalog.default_models.filter((model) => selectableSet.has(model));

      const finalModels = nextModels.length > 0
        ? nextModels
        : selectableIds.slice(0, 1);

      const savedChairman = localStorage.getItem(CHAIRMAN_MODEL_KEY);
      const nextChairman = (
        savedChairman && finalModels.includes(savedChairman)
          ? savedChairman
          : (
              finalModels.includes(catalog.default_chairman_model)
                ? catalog.default_chairman_model
                : finalModels[0] || null
            )
      );

      setAvailableModels(catalog.models);
      setSelectedModels(finalModels);
      setChairmanModel(nextChairman);
      setCouncilProgress(createProgress(finalModels, nextChairman));

      localStorage.setItem(
        SELECTED_MODELS_KEY,
        JSON.stringify(finalModels)
      );
      if (nextChairman) {
        localStorage.setItem(CHAIRMAN_MODEL_KEY, nextChairman);
      }

      if (catalog.ollama_error) {
        setModelError(catalog.ollama_error);
      }
    } catch (error) {
      console.error('Failed to discover models:', error);
      setModelError(error.message);
    } finally {
      setModelsLoading(false);
    }
  };

  const loadConversation = async (id) => {
    try {
      setCurrentConversation(await api.getConversation(id));
    } catch (error) {
      console.error('Failed to load conversation:', error);
    }
  };

  const handleNewConversation = async () => {
    try {
      const newConversation = await api.createConversation();
      setConversations((previous) => [
        {
          id: newConversation.id,
          created_at: newConversation.created_at,
          title: newConversation.title,
          message_count: 0,
        },
        ...previous,
      ]);
      setCurrentConversationId(newConversation.id);
      setCouncilProgress(
        createProgress(selectedModels, chairmanModel)
      );
    } catch (error) {
      console.error('Failed to create conversation:', error);
      setModelError(error.message);
    }
  };

  const handleSelectConversation = (id) => {
    setCurrentConversationId(id);
    setSidebarOpen(false);
  };

  const handleDeleteConversation = async (id) => {
    try {
      await api.deleteConversation(id);
      setConversations((previous) => previous.filter((c) => c.id !== id));
      if (id === currentConversationId) {
        setCurrentConversationId(null);
        setCurrentConversation(null);
      }
    } catch (error) {
      console.error('Failed to delete conversation:', error);
      setModelError(error.message);
    }
  };

  const handleRenameConversation = async (id, title) => {
    try {
      const updated = await api.renameConversation(id, title);
      setConversations((previous) => previous.map((c) => (
        c.id === id ? { ...c, title: updated.title } : c
      )));
      setCurrentConversation((previous) => (
        previous && previous.id === id
          ? { ...previous, title: updated.title }
          : previous
      ));
    } catch (error) {
      console.error('Failed to rename conversation:', error);
      setModelError(error.message);
    }
  };

  const handleApplyRecommendation = (modelIds) => {
    if (isLoading) return;

    const selectableIds = new Set(
      availableModels.filter((model) => model.selectable).map((model) => model.id)
    );
    const applicable = modelIds.filter((id) => selectableIds.has(id));
    if (applicable.length === 0) return;

    let nextChairman = chairmanModel;
    if (!applicable.includes(nextChairman)) {
      nextChairman = applicable[0];
      setChairmanModel(nextChairman);
      localStorage.setItem(CHAIRMAN_MODEL_KEY, nextChairman);
    }

    setSelectedModels(applicable);
    localStorage.setItem(SELECTED_MODELS_KEY, JSON.stringify(applicable));
    setCouncilProgress(createProgress(applicable, nextChairman));
  };

  const handleToggleModel = (modelId) => {
    if (isLoading) return;

    setSelectedModels((previous) => {
      const isSelected = previous.includes(modelId);
      if (isSelected && previous.length === 1) {
        return previous;
      }

      const next = isSelected
        ? previous.filter((model) => model !== modelId)
        : [...previous, modelId];

      let nextChairman = chairmanModel;
      if (!next.includes(nextChairman)) {
        nextChairman = next[0] || null;
        setChairmanModel(nextChairman);
        if (nextChairman) {
          localStorage.setItem(CHAIRMAN_MODEL_KEY, nextChairman);
        }
      }

      localStorage.setItem(SELECTED_MODELS_KEY, JSON.stringify(next));
      setCouncilProgress(createProgress(next, nextChairman));
      return next;
    });
  };

  const handleChairmanChange = (modelId) => {
    if (isLoading || !selectedModels.includes(modelId)) return;

    setChairmanModel(modelId);
    localStorage.setItem(CHAIRMAN_MODEL_KEY, modelId);
    setCouncilProgress(createProgress(selectedModels, modelId));
  };

  const updateLastAssistant = (updater) => {
    setCurrentConversation((previous) => {
      if (!previous || previous.messages.length === 0) return previous;

      const messages = [...previous.messages];
      const index = messages.length - 1;
      messages[index] = updater({
        ...messages[index],
        loading: { ...messages[index].loading },
      });

      return { ...previous, messages };
    });
  };

  const handleSendMessage = async (content) => {
    if (
      !currentConversationId
      || !currentConversation
      || selectedModels.length === 0
    ) return;

    const activeModels = [...selectedModels];
    const activeChairman = chairmanModel || activeModels[0];

    const controller = new AbortController();
    abortControllerRef.current = controller;

    setIsLoading(true);
    setModelError(null);
    setLastFailedContent(null);
    setCouncilProgress(
      createProgress(activeModels, activeChairman, 'connecting')
    );

    const userMessage = { role: 'user', content };
    const assistantMessage = {
      role: 'assistant',
      stage1: null,
      stage2: null,
      stage3: null,
      metadata: null,
      loading: {
        stage1: false,
        stage2: false,
        stage3: false,
      },
    };

    setCurrentConversation((previous) => {
      if (!previous) return previous;

      return {
        ...previous,
        messages: [
          ...previous.messages,
          userMessage,
          assistantMessage,
        ],
      };
    });

    try {
      const terminalEvent = await api.sendMessageStream(
        currentConversationId,
        content,
        {
          models: activeModels,
          chairmanModel: activeChairman,
          signal: controller.signal,
        },
        (eventType, event) => {
          switch (eventType) {
            case 'council_start': {
              const eventModels = event.data?.models || activeModels;
              const eventChairman = (
                event.data?.chairman_model || activeChairman
              );
              setCouncilProgress(
                createProgress(eventModels, eventChairman, 'connecting')
              );
              break;
            }

            case 'stage1_start':
              updateLastAssistant((message) => ({
                ...message,
                loading: { ...message.loading, stage1: true },
              }));
              setCouncilProgress((previous) => ({
                ...previous,
                phase: 'stage1',
                models: previous.models.map((model) => ({
                  ...model,
                  stage1: 'active',
                })),
              }));
              break;

            case 'stage1_complete': {
              const successful = new Set(
                (event.data || []).map((result) => result.model)
              );
              updateLastAssistant((message) => ({
                ...message,
                stage1: event.data,
                loading: { ...message.loading, stage1: false },
              }));
              setCouncilProgress((previous) => ({
                ...previous,
                models: previous.models.map((model) => ({
                  ...model,
                  stage1: successful.has(model.id)
                    ? 'complete'
                    : 'failed',
                })),
              }));
              break;
            }

            case 'stage2_start':
              updateLastAssistant((message) => ({
                ...message,
                loading: { ...message.loading, stage2: true },
              }));
              setCouncilProgress((previous) => ({
                ...previous,
                phase: 'stage2',
                models: previous.models.map((model) => ({
                  ...model,
                  stage2: 'active',
                })),
              }));
              break;

            case 'stage2_complete': {
              const successful = new Set(
                (event.data || []).map((result) => result.model)
              );
              updateLastAssistant((message) => ({
                ...message,
                stage2: event.data,
                metadata: event.metadata,
                loading: { ...message.loading, stage2: false },
              }));
              setCouncilProgress((previous) => ({
                ...previous,
                models: previous.models.map((model) => ({
                  ...model,
                  stage2: successful.has(model.id)
                    ? 'complete'
                    : 'failed',
                })),
              }));
              break;
            }

            case 'stage3_start':
              updateLastAssistant((message) => ({
                ...message,
                loading: { ...message.loading, stage3: true },
              }));
              setCouncilProgress((previous) => ({
                ...previous,
                phase: 'stage3',
                chairman: {
                  id: event.data?.chairman_model || previous.chairman.id,
                  stage3: 'active',
                },
              }));
              break;

            case 'stage3_complete': {
              const failed = event.data?.response?.startsWith('Error:');
              updateLastAssistant((message) => ({
                ...message,
                stage3: event.data,
                loading: { ...message.loading, stage3: false },
              }));
              setCouncilProgress((previous) => ({
                ...previous,
                chairman: {
                  ...previous.chairman,
                  stage3: failed ? 'failed' : 'complete',
                },
              }));
              break;
            }

            case 'title_complete':
              loadConversations();
              break;

            case 'complete':
              setCouncilProgress((previous) => ({
                ...previous,
                phase: 'complete',
              }));
              loadConversations();
              setLastFailedContent(null);
              setIsLoading(false);
              break;

            case 'error':
              console.error('Stream error:', event.message);
              setCouncilProgress((previous) => ({
                ...previous,
                phase: 'error',
                error: event.message,
                models: previous.models.map((model) => ({
                  ...model,
                  stage1: model.stage1 === 'active'
                    ? 'failed'
                    : model.stage1,
                  stage2: model.stage2 === 'active'
                    ? 'failed'
                    : model.stage2,
                })),
                chairman: {
                  ...previous.chairman,
                  stage3: previous.chairman.stage3 === 'active'
                    ? 'failed'
                    : previous.chairman.stage3,
                },
              }));
              setModelError(event.message);
              setLastFailedContent(content);
              setIsLoading(false);
              break;

            default:
              console.log('Unknown event type:', eventType);
          }
        }
      );

      if (!['complete', 'error'].includes(terminalEvent)) {
        throw new Error('The council stream ended unexpectedly.');
      }
    } catch (error) {
      if (error.name === 'AbortError') {
        setCouncilProgress((previous) => ({
          ...previous,
          phase: 'cancelled',
          error: null,
          models: previous.models.map((model) => ({
            ...model,
            stage1: model.stage1 === 'active' ? 'failed' : model.stage1,
            stage2: model.stage2 === 'active' ? 'failed' : model.stage2,
          })),
          chairman: {
            ...previous.chairman,
            stage3: previous.chairman.stage3 === 'active'
              ? 'failed'
              : previous.chairman.stage3,
          },
        }));
      } else {
        console.error('Failed to send message:', error);
        setCouncilProgress((previous) => ({
          ...previous,
          phase: 'error',
          error: error.message,
        }));
        setModelError(error.message);
      }
      setLastFailedContent(content);
      setIsLoading(false);
    } finally {
      abortControllerRef.current = null;
    }
  };

  const handleCancelMessage = () => {
    abortControllerRef.current?.abort();
  };

  const handleRetry = () => {
    if (lastFailedContent && !isLoading) {
      const content = lastFailedContent;
      setLastFailedContent(null);
      handleSendMessage(content);
    }
  };

  return (
    <div className="app">
      <button
        type="button"
        className="mobile-sidebar-toggle"
        onClick={() => setSidebarOpen((open) => !open)}
        aria-label={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
        aria-expanded={sidebarOpen}
      >
        <span aria-hidden="true">☰</span>
      </button>

      {sidebarOpen && (
        <div
          className="sidebar-backdrop"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      <Sidebar
        conversations={conversations}
        currentConversationId={currentConversationId}
        onSelectConversation={handleSelectConversation}
        onNewConversation={handleNewConversation}
        onDeleteConversation={handleDeleteConversation}
        onRenameConversation={handleRenameConversation}
        availableModels={availableModels}
        selectedModels={selectedModels}
        chairmanModel={chairmanModel}
        onToggleModel={handleToggleModel}
        onChairmanChange={handleChairmanChange}
        onRefreshModels={loadModels}
        modelsLoading={modelsLoading}
        modelError={modelError}
        selectionDisabled={isLoading}
        open={sidebarOpen}
      />

      <main className="council-workspace">
        <CouncilFlow progress={councilProgress} />
        <ChatInterface
          conversation={currentConversation}
          onSendMessage={handleSendMessage}
          onCancelMessage={handleCancelMessage}
          onRetry={handleRetry}
          canRetry={Boolean(lastFailedContent)}
          isLoading={isLoading}
          onApplyRecommendation={handleApplyRecommendation}
        />
      </main>
    </div>
  );
}

export default App;
