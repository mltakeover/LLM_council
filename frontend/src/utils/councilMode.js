export function councilModeLabel(value) {
  return (value || 'ask')
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
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
