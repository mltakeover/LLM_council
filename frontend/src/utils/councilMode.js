export function councilModeLabel(value) {
  return (value || 'ask')
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

const ORCHESTRATION_STRATEGIES = new Set(['council', 'workforce', 'hybrid']);
const OUTPUT_HYGIENE_MODES = new Set(['off', 'report', 'clean_safe']);

export function normalizeOrchestrationStrategy(value, fallback = 'hybrid') {
  if (ORCHESTRATION_STRATEGIES.has(value)) return value;
  return ORCHESTRATION_STRATEGIES.has(fallback) ? fallback : 'hybrid';
}

export function normalizeOutputHygiene(value, fallback = 'clean_safe') {
  if (OUTPUT_HYGIENE_MODES.has(value)) return value;
  return OUTPUT_HYGIENE_MODES.has(fallback) ? fallback : 'clean_safe';
}

export function normalizeRoleAssignments(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value)
      .filter(([model, role]) => (
        typeof model === 'string'
        && model.trim()
        && typeof role === 'string'
        && role.trim()
      ))
      .map(([model, role]) => [model.trim(), role.trim().slice(0, 160)])
  );
}

export function normalizeCouncilPreset(preset = {}) {
  return {
    ...preset,
    models: Array.isArray(preset.models) ? preset.models : [],
    councilMode: preset.councilMode || 'auto',
    orchestrationStrategy: normalizeOrchestrationStrategy(
      preset.orchestrationStrategy,
      'council',
    ),
    outputHygiene: normalizeOutputHygiene(preset.outputHygiene),
    reviewProfile: preset.reviewProfile || 'general',
    roleAssignments: normalizeRoleAssignments(preset.roleAssignments),
    includeContext: preset.includeContext !== false,
  };
}

export function adaptivePanelNames(report = {}) {
  const panels = [];
  if (report.direct_answer) panels.push('answer');
  if (report.options?.length) panels.push('options');
  if (report.positions?.length) panels.push('debate');
  if (report.ideas?.length) panels.push('ideas');
  if (report.comparison?.length) panels.push('comparison');
  if (report.plan_steps?.length) panels.push('plan');
  if (report.claims?.length) panels.push('claims');
  if (report.findings?.length) panels.push('findings');
  return panels;
}
