import test from 'node:test';
import assert from 'node:assert/strict';

import {
  providerName,
  providerSlug,
  shortModelName,
} from '../src/utils/modelDisplay.js';


test('shortModelName preserves Ollama tags', () => {
  assert.equal(shortModelName('ollama:qwen2.5-coder:7b'), 'qwen2.5-coder:7b');
});


test('provider helpers derive display and slug values', () => {
  assert.equal(providerName('anthropic:claude-sonnet'), 'Anthropic');
  assert.equal(providerSlug('OpenAI:gpt-test'), 'openai');
});


test('model helpers handle empty values safely', () => {
  assert.equal(shortModelName(null), null);
  assert.equal(providerName(undefined), undefined);
  assert.equal(providerSlug(''), '');
});
