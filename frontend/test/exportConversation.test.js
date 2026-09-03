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

test('conversation export preserves managed workforce context and hygiene audit', () => {
  const markdown = conversationToMarkdown({
    title: 'Managed research',
    messages: [
      {
        role: 'user',
        content: 'Research the latest proposal',
        orchestration_strategy: 'hybrid',
        council_mode: 'fact_check',
      },
      {
        role: 'assistant',
        metadata: {
          orchestration_strategy: 'hybrid',
          workforce_plan: {
            objective: 'Produce an evidence-aware recommendation.',
            assignments: [{
              model: 'ollama:qwen',
              role: 'Research specialist',
              deliverable: 'Identify the strongest evidence.',
              success_criteria: ['Separate evidence from inference.'],
            }],
          },
        },
        stage1: [{
          model: 'ollama:qwen',
          role: 'Research specialist',
          assignment: { deliverable: 'Identify the strongest evidence.' },
          response: 'Specialist finding',
        }],
        stage2: [{ model: 'ollama:qwen', ranking: 'One unsupported claim requires review.' }],
        stage3: {
          model: 'ollama:qwen',
          response: 'Master report',
          output_hygiene: {
            rendered_output: { removed_count: 2, reported_only_count: 1 },
          },
        },
      },
    ],
  });

  assert.match(markdown, /hybrid orchestration · fact_check mode/);
  assert.match(markdown, /Manager Work Plan/);
  assert.match(markdown, /Research specialist — ollama:qwen/);
  assert.match(markdown, /Stage 1: Specialist Deliverables/);
  assert.match(markdown, /Stage 2: Targeted Quality Assurance/);
  assert.match(markdown, /Final Answer — Master/);
  assert.match(markdown, /Safe invisible characters removed: 2/);
  assert.match(markdown, /Directional\/joining characters reported only: 1/);
});
