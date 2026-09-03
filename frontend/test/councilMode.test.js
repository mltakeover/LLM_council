import test from 'node:test';
import assert from 'node:assert/strict';
import {
  adaptivePanelNames,
  councilModeLabel,
  normalizeCouncilPreset,
  normalizeOrchestrationStrategy,
  normalizeOutputHygiene,
  normalizeRoleAssignments,
} from '../src/utils/councilMode.js';

test('council mode labels are human readable', () => {
  assert.equal(councilModeLabel('fact_check'), 'Fact Check');
});

test('legacy presets receive general-purpose defaults', () => {
  assert.deepEqual(
    normalizeCouncilPreset({ name: 'Legacy', models: ['ollama:test'] }),
    {
      name: 'Legacy',
      models: ['ollama:test'],
      councilMode: 'auto',
      orchestrationStrategy: 'council',
      outputHygiene: 'clean_safe',
      reviewProfile: 'general',
      roleAssignments: {},
      includeContext: true,
    },
  );
});

test('browser-persisted enum settings reject poisoned values', () => {
  assert.equal(normalizeOrchestrationStrategy('workforce'), 'workforce');
  assert.equal(normalizeOrchestrationStrategy('<img onerror=alert(1)>'), 'hybrid');
  assert.equal(normalizeOrchestrationStrategy('invalid', 'council'), 'council');
  assert.equal(normalizeOutputHygiene('report'), 'report');
  assert.equal(normalizeOutputHygiene('javascript:alert(1)'), 'clean_safe');
});

test('presets cannot introduce unsupported persisted enum values', () => {
  const preset = normalizeCouncilPreset({
    orchestrationStrategy: '../poison',
    outputHygiene: '<script>',
  });

  assert.equal(preset.orchestrationStrategy, 'council');
  assert.equal(preset.outputHygiene, 'clean_safe');
});

test('role assignments from browser storage are bounded and sanitised', () => {
  const roles = normalizeRoleAssignments({
    ' ollama:a ': '  Evidence analyst  ',
    'ollama:b': { invalid: true },
    '': 'Ignored',
  });

  assert.deepEqual(roles, { 'ollama:a': 'Evidence analyst' });
});

test('adaptive report panels follow available structured content', () => {
  assert.deepEqual(
    adaptivePanelNames({ options: [{ name: 'A' }], claims: [{ claim: 'B' }] }),
    ['options', 'claims'],
  );
});
