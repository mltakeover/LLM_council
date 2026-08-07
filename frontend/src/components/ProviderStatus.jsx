import { useState } from 'react';
import { api } from '../api';
import { providerName, shortModelName } from '../utils/modelDisplay';
import './ProviderStatus.css';

function statusLabel(result) {
  if (!result) return 'Not tested';
  if (result.testing) return 'Testing…';
  return result.ok ? 'Connected' : 'Failed';
}

export default function ProviderStatus({ models, onClose, onRefresh }) {
  const [results, setResults] = useState({});

  const testModel = async (model) => {
    setResults((previous) => ({ ...previous, [model.id]: { testing: true } }));
    try {
      const result = await api.testModel(model.id);
      setResults((previous) => ({ ...previous, [model.id]: result }));
    } catch (error) {
      setResults((previous) => ({
        ...previous,
        [model.id]: { ok: false, error: { message: error.message } },
      }));
    }
  };

  return (
    <div className="provider-status-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="provider-status-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="provider-status-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <span className="sidebar-kicker">CONNECTIVITY</span>
            <h2 id="provider-status-title">Provider status</h2>
            <p>Test each model with a generic “OK” prompt. Conversation content is never included.</p>
          </div>
          <div className="provider-status-actions">
            <button type="button" onClick={onRefresh}>Refresh catalogue</button>
            <button type="button" className="provider-status-close" onClick={onClose} aria-label="Close provider status">×</button>
          </div>
        </header>

        <div className="provider-status-list">
          {models.filter((model) => model.selectable).map((model) => {
            const result = results[model.id];
            return (
              <article className="provider-status-card" key={model.id}>
                <div className="provider-status-identity">
                  <span className={`provider-status-dot provider-status-dot--${result?.testing ? 'testing' : result?.ok === true ? 'ok' : result?.ok === false ? 'failed' : 'unknown'}`} />
                  <div>
                    <strong>{shortModelName(model.id)}</strong>
                    <small>{providerName(model.id)} · {model.is_local ? 'Local' : 'Cloud'}</small>
                  </div>
                </div>
                <div className="provider-status-result">
                  <strong>{statusLabel(result)}</strong>
                  {result?.elapsed_seconds != null && <small>{result.elapsed_seconds}s</small>}
                  {result?.usage?.total_tokens && <small>{result.usage.total_tokens.toLocaleString()} tokens</small>}
                  {result?.error?.message && <small className="provider-test-error" title={result.error.message}>{result.error.message}</small>}
                </div>
                <button type="button" onClick={() => testModel(model)} disabled={result?.testing}>
                  {result?.testing ? 'Testing…' : 'Test model'}
                </button>
              </article>
            );
          })}
          {models.filter((model) => model.selectable).length === 0 && (
            <div className="provider-status-empty">No selectable models are currently available.</div>
          )}
        </div>
      </section>
    </div>
  );
}
