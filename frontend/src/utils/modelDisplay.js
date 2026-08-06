/**
 * Shared helpers for rendering `provider:model-name` identifiers.
 *
 * Model IDs use a colon separator (e.g. "openai:gpt-5.6-terra",
 * "ollama:qwen3.6:latest") set by the backend's direct provider clients.
 */

export function shortModelName(modelId) {
  if (!modelId) return modelId;
  const separator = modelId.indexOf(':');
  return separator === -1 ? modelId : modelId.slice(separator + 1);
}

export function providerName(modelId) {
  if (!modelId) return modelId;
  const provider = modelId.split(':', 1)[0];
  return provider.charAt(0).toUpperCase() + provider.slice(1);
}
