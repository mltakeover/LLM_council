import test from 'node:test';
import assert from 'node:assert/strict';

import { conversationToMarkdown } from '../src/utils/exportConversation.js';

test('conversation export includes all council stages', () => {
  const markdown = conversationToMarkdown({
    title: 'Architecture review',
    messages: [
      { role: 'user', content: 'Review this HLD' },
      {
        role: 'assistant',
        stage1: [{ model: 'ollama:qwen', response: 'Independent finding', elapsed_seconds: 1.2 }],
        stage2: [{ model: 'ollama:llama', ranking: 'Response A first', elapsed_seconds: 0.8 }],
        stage3: { model: 'ollama:qwen', response: 'Final report', elapsed_seconds: 2.1 },
      },
    ],
  });

  assert.match(markdown, /^# Architecture review/m);
  assert.match(markdown, /Stage 1: Individual Responses/);
  assert.match(markdown, /Independent finding/);
  assert.match(markdown, /Stage 2: Peer Rankings/);
  assert.match(markdown, /Final report/);
});
