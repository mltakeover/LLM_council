/**
 * API client for the LLM Council backend.
 */

const API_BASE = 'http://localhost:8001';

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
        }),
      }
    );
    if (!response.ok) {
      throw await responseError(response, 'Failed to send message');
    }
    return response.json();
  },

  /**
   * Send a message and parse server-sent events safely across network chunks.
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
        }),
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

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split(/\r?\n\r?\n/);
      buffer = blocks.pop() || '';
      blocks.forEach(processBlock);
    }

    buffer += decoder.decode();
    if (buffer.trim()) {
      processBlock(buffer);
    }

    return terminalEvent;
  },
};
