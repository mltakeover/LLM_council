const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;


/**
 * Validate an application-generated UUID before it becomes a URL path segment.
 * Conversation and document identifiers are UUIDs created by the backend, so
 * rejecting every other form closes path traversal and URL-manipulation paths.
 */
export function encodeUuidPathSegment(value, label = 'identifier') {
  if (typeof value !== 'string' || !UUID_PATTERN.test(value)) {
    throw new TypeError(`Invalid ${label}`);
  }
  return encodeURIComponent(value);
}
