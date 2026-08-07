import assert from 'node:assert/strict';
import test from 'node:test';

import { scrollElementToBottom } from '../src/utils/scroll.js';

test('scrollElementToBottom only scrolls the supplied container', () => {
  let scrollOptions = null;
  const messagesContainer = {
    scrollHeight: 640,
    scrollTo(options) {
      scrollOptions = options;
    },
  };

  assert.equal(scrollElementToBottom(messagesContainer), true);
  assert.deepEqual(scrollOptions, { top: 640, behavior: 'smooth' });
});

test('scrollElementToBottom ignores an unavailable container', () => {
  assert.equal(scrollElementToBottom(null), false);
});
