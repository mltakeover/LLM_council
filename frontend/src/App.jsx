import { useEffect, useRef, useState } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import CouncilFlow from './components/CouncilFlow';
import { api } from './api';
import './App.css';


const SELECTED_MODELS_KEY = 'llm-council:selected-models';
const CHAIRMAN_MODEL_KEY = 'llm-council:chairman-model';
const REVIEW_PROFILE_KEY = 'llm-council:review-profile';
const INCLUDE_CONTEXT_KEY = 'llm-council:include-context';


function createProgress(models, chairmanModel, phase = 'ready') {
  return {
    phase,
    models: models.map((id) => ({
      id,
      stage1: 'pending',
      stage2: 'pending',
      attempts: {},
      elapsed: {},
      errors: {},
    })),
    chairman: {
      id: chairmanModel,
      stage3: 'pending',
      attempts: {},
      elapsed: {},
      errors: {},
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
  const [maxCouncilModels, setMaxCouncilModels] = useState(8);
  const [reviewProfiles, setReviewProfiles] = useState([]);
  const [reviewProfile, setReviewProfile] = useState(
    localStorage.getItem(REVIEW_PROFILE_KEY) || 'general'
  );
  const [includeContext, setIncludeContext] = useState(
    localStorage.getItem(INCLUDE_CONTEXT_KEY) !== 'false'
  );
  const [cloudPrivacyConfirmed, setCloudPrivacyConfirmed] = useState(false);
  const [councilProgress, setCouncilProgress] = useState(
    createProgress([], null)
  );
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [lastFailedRequest, setLastFailedRequest] = useState(null);

  const abortControllerRef = useRef(null);

  useEffect(() => {
    loadConversations();
    loadModels();
    loadReviewProfiles();
    // Bootstrap once; refresh actions call the same loaders explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  const loadReviewProfiles = async () => {
    try {
      const payload = await api.getReviewProfiles();
      const profiles = payload.profiles || [];
      setReviewProfiles(profiles);
      if (!profiles.some((profile) => profile.id === reviewProfile)) {
        const fallback = profiles[0]?.id || 'general';
        setReviewProfile(fallback);
        localStorage.setItem(REVIEW_PROFILE_KEY, fallback);
      }
    } catch (error) {
      console.error('Failed to load review profiles:', error);
      setReviewProfiles([
        { id: 'general', name: 'General review', description: 'Balanced review across quality, risk, and implementation.' },
      ]);
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
      const catalogMaxModels = catalog.limits?.max_council_models || 8;

      let savedModels = [];
      try {
        savedModels = JSON.parse(
          localStorage.getItem(SELECTED_MODELS_KEY) || '[]'
        );
      } catch {
        savedModels = [];
      }

      const restoredModels = Array.isArray(savedModels)
        ? savedModels
            .filter((model) => selectableSet.has(model))
            .slice(0, catalogMaxModels)
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
      setMaxCouncilModels(catalogMaxModels);
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
    const applicable = modelIds
      .filter((id) => selectableIds.has(id))
      .slice(0, maxCouncilModels);
    if (applicable.length === 0) return;

    let nextChairman = chairmanModel;
    if (!applicable.includes(nextChairman)) {
      nextChairman = applicable[0];
      setChairmanModel(nextChairman);
      localStorage.setItem(CHAIRMAN_MODEL_KEY, nextChairman);
    }

    setSelectedModels(applicable);
    setCloudPrivacyConfirmed(false);
    localStorage.setItem(SELECTED_MODELS_KEY, JSON.stringify(applicable));
    setCouncilProgress(createProgress(applicable, nextChairman));
  };

  const handleToggleModel = (modelId) => {
    if (isLoading) return;

    setCloudPrivacyConfirmed(false);
    setSelectedModels((previous) => {
      const isSelected = previous.includes(modelId);
      if (isSelected && previous.length === 1) {
        return previous;
      }
      if (!isSelected && previous.length >= maxCouncilModels) {
        setModelError(`Select no more than ${maxCouncilModels} council models.`);
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
      setModelError(null);
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

  const handleReviewProfileChange = (profileId) => {
    if (isLoading) return;
    setReviewProfile(profileId);
    localStorage.setItem(REVIEW_PROFILE_KEY, profileId);
  };

  const handleIncludeContextChange = (enabled) => {
    if (isLoading) return;
    setIncludeContext(enabled);
    localStorage.setItem(INCLUDE_CONTEXT_KEY, String(enabled));
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

  const applyModelEvent = (eventType, data = {}) => {
    const statusByEvent = {
      model_started: 'active',
      model_retrying: 'retrying',
      model_completed: 'complete',
      model_failed: 'failed',
    };
    const status = statusByEvent[eventType];
    const stage = data.stage;
    if (!status || !stage || !data.model) return;

    setCouncilProgress((previous) => {
      const details = {
        attempts: data.attempts || data.attempt,
        elapsed: data.elapsed_seconds,
        error: data.error,
      };
      if (stage === 'stage3') {
        return {
          ...previous,
          chairman: {
            ...previous.chairman,
            id: data.model,
            stage3: status,
            attempts: { ...previous.chairman.attempts, stage3: details.attempts },
            elapsed: { ...previous.chairman.elapsed, stage3: details.elapsed },
            errors: { ...previous.chairman.errors, stage3: details.error },
          },
        };
      }
      return {
        ...previous,
        models: previous.models.map((model) => (
          model.id === data.model
            ? {
                ...model,
                [stage]: status,
                attempts: { ...model.attempts, [stage]: details.attempts },
                elapsed: { ...model.elapsed, [stage]: details.elapsed },
                errors: { ...model.errors, [stage]: details.error },
              }
            : model
        )),
      };
    });
  };

  const handleSendMessage = async (content, selectedDocuments = []) => {
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
    setLastFailedRequest(null);
    setCouncilProgress(
      createProgress(activeModels, activeChairman, 'connecting')
    );

    const documentIds = selectedDocuments.map((document) => document.id);
    const userMessage = { role: 'user', content, documents: selectedDocuments };
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
          reviewProfile,
          includeContext,
          documentIds,
          cloudProcessingConfirmed: cloudPrivacyConfirmed,
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
              }));
              break;

            case 'model_started':
            case 'model_retrying':
            case 'model_completed':
            case 'model_failed':
              applyModelEvent(eventType, event.data);
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
              }));
              break;

            case 'stage2_complete': {
              const successful = new Set(
                (event.data || []).map((result) => result.model)
              );
              const stageSkipped = event.metadata?.stage2_skipped;
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
                  stage2: stageSkipped
                    ? 'skipped'
                    : (successful.has(model.id) ? 'complete' : 'failed'),
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
                  ...previous.chairman,
                  id: event.data?.chairman_model || previous.chairman.id,
                  stage3: previous.chairman.stage3,
                },
              }));
              break;

            case 'stage3_complete': {
              const failed = (
                event.data?.success === false
                || event.data?.response?.startsWith('Error:')
              );
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
              setLastFailedRequest(null);
              setCloudPrivacyConfirmed(false);
              setIsLoading(false);
              break;

            case 'error': {
              const streamError = event.error || {
                code: 'stream_error',
                message: event.message || 'The council stream stopped.',
                retryable: true,
              };
              console.error('Stream error:', streamError);
              updateLastAssistant((message) => ({
                ...message,
                stage3: {
                  model: 'error',
                  response: streamError.message,
                  success: false,
                  error: streamError,
                },
                loading: { stage1: false, stage2: false, stage3: false },
              }));
              setCouncilProgress((previous) => ({
                ...previous,
                phase: 'error',
                error: streamError.message,
                models: previous.models.map((model) => ({
                  ...model,
                  stage1: ['active', 'retrying'].includes(model.stage1)
                    ? 'failed'
                    : model.stage1,
                  stage2: ['active', 'retrying'].includes(model.stage2)
                    ? 'failed'
                    : model.stage2,
                })),
                chairman: {
                  ...previous.chairman,
                  stage3: ['active', 'retrying'].includes(previous.chairman.stage3)
                    ? 'failed'
                    : previous.chairman.stage3,
                },
              }));
              setModelError(streamError.message);
              setLastFailedRequest({ content, selectedDocuments });
              setIsLoading(false);
              break;
            }

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
        updateLastAssistant((message) => ({
          ...message,
          stage3: {
            model: 'cancelled',
            response: 'Council request cancelled.',
            success: false,
          },
          loading: { stage1: false, stage2: false, stage3: false },
        }));
        setCouncilProgress((previous) => ({
          ...previous,
          phase: 'cancelled',
          error: null,
          models: previous.models.map((model) => ({
            ...model,
            stage1: ['active', 'retrying'].includes(model.stage1) ? 'failed' : model.stage1,
            stage2: ['active', 'retrying'].includes(model.stage2) ? 'failed' : model.stage2,
          })),
          chairman: {
            ...previous.chairman,
            stage3: ['active', 'retrying'].includes(previous.chairman.stage3)
              ? 'failed'
              : previous.chairman.stage3,
          },
        }));
      } else {
        console.error('Failed to send message:', error);
        updateLastAssistant((message) => ({
          ...message,
          stage3: {
            model: 'error',
            response: error.message,
            success: false,
          },
          loading: { stage1: false, stage2: false, stage3: false },
        }));
        setCouncilProgress((previous) => ({
          ...previous,
          phase: 'error',
          error: error.message,
        }));
        setModelError(error.message);
      }
      setLastFailedRequest({ content, selectedDocuments });
      setIsLoading(false);
    } finally {
      abortControllerRef.current = null;
    }
  };

  const handleCancelMessage = () => {
    abortControllerRef.current?.abort();
  };

  const handleRetry = () => {
    if (lastFailedRequest && !isLoading) {
      const request = lastFailedRequest;
      setLastFailedRequest(null);
      handleSendMessage(request.content, request.selectedDocuments);
    }
  };

  const selectedCatalogModels = availableModels.filter((model) => (
    selectedModels.includes(model.id)
  ));
  const cloudModels = selectedCatalogModels.filter((model) => !model.is_local);
  const requiresCloudConfirmation = cloudModels.length > 0;

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
        reviewProfiles={reviewProfiles}
        reviewProfile={reviewProfile}
        includeContext={includeContext}
        onToggleModel={handleToggleModel}
        onChairmanChange={handleChairmanChange}
        onReviewProfileChange={handleReviewProfileChange}
        onIncludeContextChange={handleIncludeContextChange}
        onRefreshModels={loadModels}
        modelsLoading={modelsLoading}
        modelError={modelError}
        selectionDisabled={isLoading}
        open={sidebarOpen}
      />

      <main className="council-workspace">
        <CouncilFlow progress={councilProgress} />
        <ChatInterface
          key={currentConversationId || 'no-conversation'}
          conversation={currentConversation}
          onSendMessage={handleSendMessage}
          onCancelMessage={handleCancelMessage}
          onRetry={handleRetry}
          canRetry={Boolean(lastFailedRequest)}
          isLoading={isLoading}
          onApplyRecommendation={handleApplyRecommendation}
          selectedModels={selectedModels}
          chairmanModel={chairmanModel}
          reviewProfile={reviewProfile}
          reviewProfiles={reviewProfiles}
          includeContext={includeContext}
          requiresCloudConfirmation={requiresCloudConfirmation}
          cloudModelNames={cloudModels.map((model) => model.name)}
          cloudPrivacyConfirmed={cloudPrivacyConfirmed}
          onCloudPrivacyConfirmed={setCloudPrivacyConfirmed}
        />
      </main>
    </div>
  );
}

export default App;
