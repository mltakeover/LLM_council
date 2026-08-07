import { useEffect, useRef, useState } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import CouncilFlow from './components/CouncilFlow';
import { api } from './api';
import { shortModelName } from './utils/modelDisplay';
import { createRunId } from './utils/runId';
import { normalizeRoleAssignments } from './utils/councilMode';
import './App.css';


const SELECTED_MODELS_KEY = 'llm-council:selected-models';
const CHAIRMAN_MODEL_KEY = 'llm-council:chairman-model';
const COUNCIL_MODE_KEY = 'llm-council:council-mode';
const REVIEW_PROFILE_KEY = 'llm-council:review-profile';
const INCLUDE_CONTEXT_KEY = 'llm-council:include-context';
const ROLE_ASSIGNMENTS_KEY = 'llm-council:role-assignments';


function readRoleAssignments() {
  try {
    const value = JSON.parse(localStorage.getItem(ROLE_ASSIGNMENTS_KEY) || '{}');
    return normalizeRoleAssignments(value);
  } catch {
    return {};
  }
}


function createProgress(models, chairmanModel, phase = 'ready') {
  return {
    phase,
    models: models.map((id) => ({
      id,
      stage1: 'pending',
      stage2: 'pending',
      attempts: {},
      elapsed: {},
      usage: {},
      errors: {},
    })),
    chairman: {
      id: chairmanModel,
      stage3: 'pending',
      attempts: {},
      elapsed: {},
      usage: {},
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
  const [titleModel, setTitleModel] = useState(null);
  const [reviewProfiles, setReviewProfiles] = useState([]);
  const [councilModes, setCouncilModes] = useState([]);
  const [councilMode, setCouncilMode] = useState(
    localStorage.getItem(COUNCIL_MODE_KEY) || 'auto'
  );
  const [reviewProfile, setReviewProfile] = useState(
    localStorage.getItem(REVIEW_PROFILE_KEY) || 'general'
  );
  const [includeContext, setIncludeContext] = useState(
    localStorage.getItem(INCLUDE_CONTEXT_KEY) !== 'false'
  );
  const [roleAssignments, setRoleAssignments] = useState(readRoleAssignments);
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
    loadCouncilModes();
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

  const loadCouncilModes = async () => {
    try {
      const payload = await api.getCouncilModes();
      const modes = payload.modes || [];
      setCouncilModes(modes);
      if (!modes.some((mode) => mode.id === councilMode)) {
        const fallback = payload.default || modes[0]?.id || 'auto';
        setCouncilMode(fallback);
        localStorage.setItem(COUNCIL_MODE_KEY, fallback);
      }
    } catch (error) {
      console.error('Failed to load council modes:', error);
      setCouncilModes([
        {
          id: 'auto',
          name: 'Auto',
          description: 'Choose the most suitable approach for the request.',
          default_roles: [],
        },
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
      setTitleModel(catalog.title_model || null);
      setMaxCouncilModels(catalogMaxModels);
      setSelectedModels(finalModels);
      setChairmanModel(nextChairman);
      setCouncilProgress(createProgress(finalModels, nextChairman));
      setRoleAssignments((previous) => {
        const next = Object.fromEntries(
          Object.entries(previous).filter(([model]) => finalModels.includes(model))
        );
        localStorage.setItem(ROLE_ASSIGNMENTS_KEY, JSON.stringify(next));
        return next;
      });

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
      setCurrentConversation(newConversation);
      setCloudPrivacyConfirmed(false);
      setLastFailedRequest(null);
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
    setCloudPrivacyConfirmed(false);
    setLastFailedRequest(null);
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
      setRoleAssignments((assignments) => {
        const filtered = Object.fromEntries(
          Object.entries(assignments).filter(([model]) => next.includes(model))
        );
        localStorage.setItem(ROLE_ASSIGNMENTS_KEY, JSON.stringify(filtered));
        return filtered;
      });
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

  const handleCouncilModeChange = (modeId) => {
    if (isLoading) return;
    setCouncilMode(modeId);
    setRoleAssignments({});
    localStorage.setItem(COUNCIL_MODE_KEY, modeId);
    localStorage.setItem(ROLE_ASSIGNMENTS_KEY, '{}');
  };

  const handleRoleAssignmentChange = (modelId, role) => {
    if (isLoading || !selectedModels.includes(modelId)) return;
    setRoleAssignments((previous) => {
      const next = { ...previous };
      const trimmed = role.trim();
      if (trimmed) {
        next[modelId] = role.slice(0, 160);
      } else {
        delete next[modelId];
      }
      localStorage.setItem(ROLE_ASSIGNMENTS_KEY, JSON.stringify(next));
      return next;
    });
  };

  const handleResetRoles = () => {
    if (isLoading) return;
    setRoleAssignments({});
    localStorage.setItem(ROLE_ASSIGNMENTS_KEY, '{}');
  };

  const handleIncludeContextChange = (enabled) => {
    if (isLoading) return;
    setIncludeContext(enabled);
    localStorage.setItem(INCLUDE_CONTEXT_KEY, String(enabled));
  };

  const handleApplyPreset = (preset) => {
    if (isLoading) return;

    const selectable = new Set(
      availableModels.filter((model) => model.selectable).map((model) => model.id)
    );
    const nextModels = (preset.models || [])
      .filter((model) => selectable.has(model))
      .slice(0, maxCouncilModels);
    if (nextModels.length === 0) {
      setModelError('None of the models in this preset are currently available.');
      return;
    }

    const nextChairman = nextModels.includes(preset.chairmanModel)
      ? preset.chairmanModel
      : nextModels[0];
    const nextProfile = reviewProfiles.some((profile) => profile.id === preset.reviewProfile)
      ? preset.reviewProfile
      : 'general';
    const nextMode = councilModes.some((mode) => mode.id === preset.councilMode)
      ? preset.councilMode
      : 'auto';
    const nextContext = preset.includeContext !== false;
    const nextRoles = Object.fromEntries(
      Object.entries(preset.roleAssignments || {}).filter(([model]) => (
        nextModels.includes(model)
      ))
    );

    setSelectedModels(nextModels);
    setChairmanModel(nextChairman);
    setCouncilMode(nextMode);
    setReviewProfile(nextProfile);
    setRoleAssignments(nextRoles);
    setIncludeContext(nextContext);
    setCloudPrivacyConfirmed(false);
    setModelError(null);
    setCouncilProgress(createProgress(nextModels, nextChairman));

    localStorage.setItem(SELECTED_MODELS_KEY, JSON.stringify(nextModels));
    localStorage.setItem(CHAIRMAN_MODEL_KEY, nextChairman);
    localStorage.setItem(COUNCIL_MODE_KEY, nextMode);
    localStorage.setItem(REVIEW_PROFILE_KEY, nextProfile);
    localStorage.setItem(ROLE_ASSIGNMENTS_KEY, JSON.stringify(nextRoles));
    localStorage.setItem(INCLUDE_CONTEXT_KEY, String(nextContext));
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
        usage: data.usage,
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
            usage: { ...previous.chairman.usage, stage3: details.usage },
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
                usage: { ...model.usage, [stage]: details.usage },
                errors: { ...model.errors, [stage]: details.error },
              }
            : model
        )),
      };
    });
  };

  const handleSendMessage = async (
    content,
    selectedDocuments = [],
    existingRunId = null,
    existingSettings = null,
  ) => {
    if (
      !currentConversationId
      || !currentConversation
      || selectedModels.length === 0
    ) return;

    const activeModels = [...(existingSettings?.models || selectedModels)];
    const activeChairman = (
      existingSettings?.chairmanModel || chairmanModel || activeModels[0]
    );
    const activeCouncilMode = existingSettings?.councilMode || councilMode;
    const activeReviewProfile = existingSettings?.reviewProfile || reviewProfile;
    const activeIncludeContext = existingSettings?.includeContext ?? includeContext;
    const activeCloudProcessingConfirmed = (
      existingSettings?.cloudProcessingConfirmed ?? cloudPrivacyConfirmed
    );
    const activeRoleAssignments = existingSettings?.roleAssignments || Object.fromEntries(
      Object.entries(roleAssignments).filter(([model]) => activeModels.includes(model))
    );
    const activeSettings = {
      models: activeModels,
      chairmanModel: activeChairman,
      councilMode: activeCouncilMode,
      reviewProfile: activeReviewProfile,
      includeContext: activeIncludeContext,
      roleAssignments: activeRoleAssignments,
      cloudProcessingConfirmed: activeCloudProcessingConfirmed,
    };
    const runId = existingRunId || createRunId();

    const controller = new AbortController();
    abortControllerRef.current = controller;

    setIsLoading(true);
    setModelError(null);
    setLastFailedRequest(null);
    setCouncilProgress(
      createProgress(activeModels, activeChairman, 'connecting')
    );

    const documentIds = selectedDocuments.map((document) => document.id);
    const userMessage = {
      role: 'user',
      run_id: runId,
      content,
      documents: selectedDocuments,
      council_mode: activeCouncilMode,
    };
    const assistantMessage = {
      role: 'assistant',
      run_id: runId,
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

      const messages = [...previous.messages];
      const userIndex = messages.findIndex((message) => (
        message.role === 'user' && message.run_id === runId
      ));
      if (userIndex === -1) {
        return {
          ...previous,
          messages: [...messages, userMessage, assistantMessage],
        };
      }

      const assistantIndex = messages.findIndex((message, index) => (
        index > userIndex
        && message.role === 'assistant'
        && message.run_id === runId
      ));
      if (assistantIndex === -1) {
        messages.splice(userIndex + 1, 0, assistantMessage);
      } else {
        messages[assistantIndex] = assistantMessage;
      }
      return { ...previous, messages };
    });

    try {
      const terminalEvent = await api.sendMessageStream(
        currentConversationId,
        content,
        {
          runId,
          models: activeModels,
          chairmanModel: activeChairman,
          councilMode: activeCouncilMode,
          reviewProfile: activeReviewProfile,
          roleAssignments: activeRoleAssignments,
          includeContext: activeIncludeContext,
          documentIds,
          cloudProcessingConfirmed: activeCloudProcessingConfirmed,
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
              setCurrentConversation((previous) => (
                previous && event.data?.title
                  ? { ...previous, title: event.data.title }
                  : previous
              ));
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
              setLastFailedRequest({
                content,
                selectedDocuments,
                runId,
                settings: activeSettings,
              });
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
      setLastFailedRequest({
        content,
        selectedDocuments,
        runId,
        settings: activeSettings,
      });
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
      handleSendMessage(
        request.content,
        request.selectedDocuments,
        request.runId,
        request.settings,
      );
    }
  };

  const selectedCatalogModels = availableModels.filter((model) => (
    selectedModels.includes(model.id)
  ));
  const cloudModels = selectedCatalogModels.filter((model) => !model.is_local);
  const titleRequiresCloudConfirmation = Boolean(
    titleModel?.requires_cloud_confirmation
    && currentConversation?.title === 'New Conversation'
  );
  const cloudModelNames = cloudModels.map((model) => model.name);
  if (titleRequiresCloudConfirmation) {
    cloudModelNames.push(
      `${shortModelName(titleModel.id)} (conversation title only)`
    );
  }
  const requiresCloudConfirmation = (
    cloudModels.length > 0 || titleRequiresCloudConfirmation
  );

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
        councilModes={councilModes}
        councilMode={councilMode}
        reviewProfiles={reviewProfiles}
        reviewProfile={reviewProfile}
        roleAssignments={roleAssignments}
        includeContext={includeContext}
        onToggleModel={handleToggleModel}
        onChairmanChange={handleChairmanChange}
        onCouncilModeChange={handleCouncilModeChange}
        onReviewProfileChange={handleReviewProfileChange}
        onRoleAssignmentChange={handleRoleAssignmentChange}
        onResetRoles={handleResetRoles}
        onIncludeContextChange={handleIncludeContextChange}
        onApplyPreset={handleApplyPreset}
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
          councilMode={councilMode}
          reviewProfile={reviewProfile}
          reviewProfiles={reviewProfiles}
          includeContext={includeContext}
          requiresCloudConfirmation={requiresCloudConfirmation}
          cloudModelNames={cloudModelNames}
          cloudPrivacyConfirmed={cloudPrivacyConfirmed}
          onCloudPrivacyConfirmed={setCloudPrivacyConfirmed}
        />
      </main>
    </div>
  );
}

export default App;
