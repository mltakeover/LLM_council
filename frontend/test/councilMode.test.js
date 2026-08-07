import test from 'node:test';
import assert from 'node:assert/strict';
import {
  adaptivePanelNames,
  councilModeLabel,
  normalizeCouncilPreset,
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
      reviewProfile: 'general',
      roleAssignments: {},
      includeContext: true,
    },
  );
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
