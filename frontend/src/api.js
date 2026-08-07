/**
 * API client for the LLM Council backend.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001';

async function responseError(response, fallback) {
  try {
    const payload = await response.json();
    return new Error(payload.detail || payload.message || fallback);
  } catch {
    return new Error(fallback);
  }
}

export const api = {
  async listConversations() {
    const response = await fetch(`${API_BASE}/api/conversations`);
    if (!response.ok) {
      throw await responseError(response, 'Failed to list conversations');
    }
    return response.json();
  },

  async createConversation() {
    const response = await fetch(`${API_BASE}/api/conversations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    if (!response.ok) {
      throw await responseError(response, 'Failed to create conversation');
    }
    return response.json();
  },

  async getConversation(conversationId) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}`
    );
    if (!response.ok) {
      throw await responseError(response, 'Failed to get conversation');
    }
    return response.json();
  },

  async deleteConversation(conversationId) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}`,
      { method: 'DELETE' }
    );
    if (!response.ok) {
      throw await responseError(response, 'Failed to delete conversation');
    }
    return response.json();
  },

  async renameConversation(conversationId, title) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title }),
      }
    );
    if (!response.ok) {
      throw await responseError(response, 'Failed to rename conversation');
    }
    return response.json();
  },

  /**
   * Suggest council models for a not-yet-sent question, based on how
   * models have actually performed on similar past questions. Pass
   * `signal` to cancel a stale in-flight request (e.g. the user kept
   * typing).
   */
  async recommendModels(content, signal) {
    const response = await fetch(`${API_BASE}/api/recommend-models`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
      signal,
    });
    if (!response.ok) {
      throw await responseError(response, 'Failed to get model recommendations');
    }
    return response.json();
  },

  /** Discover configured cloud models and currently installed Ollama models. */
  async getModels() {
    const response = await fetch(`${API_BASE}/api/models`, {
      cache: 'no-store',
    });
    if (!response.ok) {
      throw await responseError(response, 'Failed to discover models');
    }
    return response.json();
  },

  async getReviewProfiles() {
    const response = await fetch(`${API_BASE}/api/review-profiles`);
    if (!response.ok) {
      throw await responseError(response, 'Failed to load review profiles');
    }
    return response.json();
  },

  async listDocuments(conversationId) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/documents`
    );
    if (!response.ok) {
      throw await responseError(response, 'Failed to list documents');
    }
    return response.json();
  },

  async uploadDocument(conversationId, file, signal) {
    const form = new FormData();
    form.append('file', file);
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/documents`,
      { method: 'POST', body: form, signal }
    );
    if (!response.ok) {
      throw await responseError(response, `Failed to upload ${file.name}`);
    }
    return response.json();
  },

  async deleteDocument(conversationId, documentId) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/documents/${documentId}`,
      { method: 'DELETE' }
    );
    if (!response.ok) {
      throw await responseError(response, 'Failed to delete document');
    }
    return response.json();
  },

  async estimateUsage(conversationId, content, options = {}, signal) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/usage-estimate`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content,
          models: options.models,
          chairman_model: options.chairmanModel,
          review_profile: options.reviewProfile,
          include_context: options.includeContext,
          document_ids: options.documentIds,
        }),
        signal,
      }
    );
    if (!response.ok) {
      throw await responseError(response, 'Failed to estimate usage');
    }
    return response.json();
  },

  async sendMessage(conversationId, content, options = {}) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/message`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content,
          models: options.models,
          chairman_model: options.chairmanModel,
          review_profile: options.reviewProfile,
          include_context: options.includeContext,
          document_ids: options.documentIds,
          cloud_processing_confirmed: options.cloudProcessingConfirmed,
        }),
        signal: options.signal,
      }
    );
    if (!response.ok) {
      throw await responseError(response, 'Failed to send message');
    }
    return response.json();
  },

  /**
   * Send a message and parse server-sent events safely across network chunks.
   * Pass `options.signal` (an AbortSignal) to allow cancelling mid-stream.
   */
  async sendMessageStream(
    conversationId,
    content,
    options,
    onEvent
  ) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/message/stream`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content,
          models: options.models,
          chairman_model: options.chairmanModel,
          review_profile: options.reviewProfile,
          include_context: options.includeContext,
          document_ids: options.documentIds,
          cloud_processing_confirmed: options.cloudProcessingConfirmed,
        }),
        signal: options.signal,
      }
    );

    if (!response.ok) {
      throw await responseError(response, 'Failed to send message');
    }

    if (!response.body) {
      throw new Error('Streaming is not supported by this browser response');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let terminalEvent = null;

    const processBlock = (block) => {
      const dataLines = block
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart());

      if (dataLines.length === 0) return;

      const rawData = dataLines.join('\n');
      try {
        const event = JSON.parse(rawData);
        if (event.type === 'complete' || event.type === 'error') {
          terminalEvent = event.type;
        }
        onEvent(event.type, event);
      } catch (error) {
        console.error('Failed to parse SSE event:', error, rawData);
      }
    };

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop() || '';
        blocks.forEach(processBlock);
      }
    } catch (error) {
      // Release the reader's lock so an aborted fetch doesn't leave the
      // underlying stream in a half-consumed state.
      reader.cancel().catch(() => {});
      throw error;
    }

    buffer += decoder.decode();
    if (buffer.trim()) {
      processBlock(buffer);
    }

    return terminalEvent;
  },
};
