import assert from 'node:assert/strict';
import test from 'node:test';

import { encodeUuidPathSegment } from '../src/utils/pathId.js';


test('UUID path segments accept backend-generated identifiers', () => {
  const id = '3f5ec89c-d98c-4bfd-80b8-3d666c254b6f';
  assert.equal(encodeUuidPathSegment(id), id);
});


test('UUID path segments reject traversal and URL manipulation', () => {
  const invalidValues = [
    '../models',
    '3f5ec89c-d98c-4bfd-80b8-3d666c254b6f/documents',
    '3f5ec89c-d98c-4bfd-80b8-3d666c254b6f?admin=true',
    '%2e%2e%2fmodels',
    'javascript:alert(1)',
  ];

  invalidValues.forEach((value) => {
    assert.throws(() => encodeUuidPathSegment(value), /Invalid identifier/);
  });
});


test('UUID path segments reject non-string and malformed identifiers', () => {
  assert.throws(() => encodeUuidPathSegment(null), /Invalid identifier/);
  assert.throws(() => encodeUuidPathSegment('not-a-uuid'), /Invalid identifier/);
  assert.throws(
    () => encodeUuidPathSegment('3f5ec89c-d98c-4bfd-80b8-3d666c254b6f '),
    /Invalid identifier/,
  );
});
