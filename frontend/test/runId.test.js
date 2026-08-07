import assert from 'node:assert/strict';
import test from 'node:test';

import { createRunId } from '../src/utils/runId.js';

test('createRunId returns unique UUID values', () => {
  const first = createRunId();
  const second = createRunId();

  assert.match(
    first,
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
  );
  assert.notEqual(first, second);
});
