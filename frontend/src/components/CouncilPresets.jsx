import { useMemo, useState } from 'react';
import { shortModelName } from '../utils/modelDisplay';
import './CouncilPresets.css';

const PRESETS_KEY = 'llm-council:presets';

function buildBuiltInPresets(models) {
  const local = models.filter((model) => model.selectable && model.is_local).map((model) => model.id);
  const cloud = models.filter((model) => model.selectable && !model.is_local).map((model) => model.id);
  const presets = [];
  if (local.length) {
    presets.push({ id: 'built-in-local-code', name: 'Local Code Review', models: local.slice(0, 3), chairmanModel: local[0], reviewProfile: 'code', includeContext: true, builtIn: true });
    presets.push({ id: 'built-in-local-hld', name: 'Local HLD Review', models: local.slice(0, 3), chairmanModel: local[0], reviewProfile: 'hld', includeContext: true, builtIn: true });
  }
  if (cloud.length) {
    const hybridModels = [...local.slice(0, 2), ...cloud.slice(0, 2)];
    presets.push({ id: 'built-in-hybrid-hld', name: 'Hybrid HLD Review', models: hybridModels, chairmanModel: cloud[0], reviewProfile: 'hld', includeContext: true, builtIn: true });
  }
  return presets;
}

function readSavedPresets() {
  try {
    const value = JSON.parse(localStorage.getItem(PRESETS_KEY) || '[]');
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

export default function CouncilPresets({ models, selectedModels, chairmanModel, reviewProfile, includeContext, disabled, onApply }) {
  const [savedPresets, setSavedPresets] = useState(readSavedPresets);
  const [name, setName] = useState('');
  const builtIns = useMemo(() => buildBuiltInPresets(models), [models]);
  const presets = [...builtIns, ...savedPresets];

  const savePreset = () => {
    const trimmed = name.trim();
    if (!trimmed || selectedModels.length === 0) return;
    const next = [
      ...savedPresets,
      {
        id: `saved-${Date.now()}`,
        name: trimmed,
        models: selectedModels,
        chairmanModel,
        reviewProfile,
        includeContext,
        builtIn: false,
      },
    ];
    setSavedPresets(next);
    localStorage.setItem(PRESETS_KEY, JSON.stringify(next));
    setName('');
  };

  const deletePreset = (id) => {
    const next = savedPresets.filter((preset) => preset.id !== id);
    setSavedPresets(next);
    localStorage.setItem(PRESETS_KEY, JSON.stringify(next));
  };

  return (
    <section className="council-presets">
      <div className="preset-heading">
        <div><strong>Council presets</strong><small>Reuse a proven model and profile mix</small></div>
      </div>
      <div className="preset-list">
        {presets.map((preset) => (
          <div className="preset-card" key={preset.id}>
            <button type="button" onClick={() => onApply(preset)} disabled={disabled}>
              <strong>{preset.name}</strong>
              <small>{preset.reviewProfile.toUpperCase()} · {preset.models.length} model{preset.models.length === 1 ? '' : 's'} · Chair: {shortModelName(preset.chairmanModel)}</small>
            </button>
            {!preset.builtIn && <button type="button" className="preset-delete" onClick={() => deletePreset(preset.id)} disabled={disabled} aria-label={`Delete ${preset.name}`}>×</button>}
          </div>
        ))}
        {presets.length === 0 && <p>No compatible presets yet.</p>}
      </div>
      <div className="preset-save-row">
        <input type="text" value={name} maxLength={40} onChange={(event) => setName(event.target.value)} placeholder="Name current setup" disabled={disabled} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); savePreset(); } }} />
        <button type="button" onClick={savePreset} disabled={disabled || !name.trim() || selectedModels.length === 0}>Save</button>
      </div>
    </section>
  );
}
