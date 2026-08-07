import { useState } from 'react';
import { shortModelName as shortModelId, providerName as providerOf } from '../utils/modelDisplay';
import './CouncilFlow.css';

const PHASE_LABELS = {
  ready: 'Ready',
  connecting: 'Connecting',
  stage1: 'Collecting independent answers',
  stage2: 'Peer evaluation and ranking',
  stage3: 'Chairman synthesis',
  complete: 'Council complete',
  error: 'Council stopped',
  cancelled: 'Cancelled by user',
};

function shortModelName(modelId) {
  return modelId ? shortModelId(modelId) : 'Not selected';
}

function providerName(modelId) {
  return modelId ? providerOf(modelId) : 'Chairman';
}

function statusText(status) {
  return {
    pending: 'Waiting',
    active: 'In progress',
    retrying: 'Retrying',
    complete: 'Completed',
    failed: 'Failed',
    skipped: 'Not needed',
  }[status] || 'Waiting';
}

function tokenText(usage) {
  if (!usage?.total_tokens) return null;
  return `${usage.total_tokens.toLocaleString()} tokens`;
}

function StageStatus({ label, status = 'pending', attempts, elapsed, usage, error }) {
  const detail = error?.message
    || (elapsed != null ? `${elapsed}s${attempts ? ` · ${attempts} attempt${attempts === 1 ? '' : 's'}` : ''}${tokenText(usage) ? ` · ${tokenText(usage)}` : ''}` : null)
    || (attempts ? `Attempt ${attempts}` : null);
  return (
    <div className={`flow-stage-wrap flow-stage-wrap--${status}`} title={error?.message || undefined}>
      <div className={`flow-stage flow-stage--${status}`}>
        <span className="flow-stage-indicator" aria-hidden="true" />
        <span className="flow-stage-label">{label}</span>
        <span className="flow-stage-state">{statusText(status)}</span>
      </div>
      {detail && <small className="flow-stage-detail">{detail}</small>}
    </div>
  );
}

function RunDetails({ node, onClose }) {
  if (!node) return null;
  const stages = node.kind === 'chairman'
    ? [{ key: 'stage3', label: 'Synthesis' }]
    : [
        { key: 'stage1', label: 'Independent answer' },
        { key: 'stage2', label: 'Peer evaluation' },
      ];

  return (
    <aside className="flow-detail-panel" aria-label={`${shortModelName(node.id)} run details`}>
      <header>
        <div>
          <small>{node.kind === 'chairman' ? 'Chairman details' : 'Council member details'}</small>
          <h3>{shortModelName(node.id)}</h3>
          <p>{providerName(node.id)} · {node.id}</p>
        </div>
        <button type="button" onClick={onClose} aria-label="Close model details">×</button>
      </header>
      <div className="flow-detail-grid">
        {stages.map(({ key, label }) => {
          const usage = node.usage?.[key];
          const error = node.errors?.[key];
          return (
            <section key={key} className={`flow-detail-stage flow-detail-stage--${node[key] || 'pending'}`}>
              <div className="flow-detail-stage-heading">
                <strong>{label}</strong>
                <span>{statusText(node[key])}</span>
              </div>
              <dl>
                <div><dt>Elapsed</dt><dd>{node.elapsed?.[key] == null ? '—' : `${node.elapsed[key]}s`}</dd></div>
                <div><dt>Attempts</dt><dd>{node.attempts?.[key] ?? '—'}</dd></div>
                <div><dt>Input tokens</dt><dd>{usage?.input_tokens?.toLocaleString() ?? 'Not reported'}</dd></div>
                <div><dt>Output tokens</dt><dd>{usage?.output_tokens?.toLocaleString() ?? 'Not reported'}</dd></div>
                <div><dt>Total tokens</dt><dd>{usage?.total_tokens?.toLocaleString() ?? 'Not reported'}</dd></div>
              </dl>
              {error && (
                <div className="flow-detail-error" role="alert">
                  <strong>{error.code || 'Provider error'}</strong>
                  <span>{error.message}</span>
                </div>
              )}
            </section>
          );
        })}
      </div>
    </aside>
  );
}

function ModelNode({ model, selected, onSelect }) {
  const stageStates = [model.stage1, model.stage2];
  const connectionState = stageStates.some((status) => ['active', 'retrying'].includes(status))
    ? 'active'
      : stageStates.every((status) => ['complete', 'skipped'].includes(status))
      ? 'complete'
      : stageStates.includes('failed')
        ? 'failed'
        : stageStates.includes('complete')
          ? 'active'
          : 'pending';

  return (
    <div className={`flow-branch flow-branch--${connectionState}`}>
      <div className="flow-branch-line" aria-hidden="true">
        <span className="flow-packet" />
      </div>
      <button
        type="button"
        className={`flow-model-card flow-model-card--${connectionState}${selected ? ' flow-model-card--selected' : ''}`}
        onClick={onSelect}
        aria-pressed={selected}
        title={`Open run details for ${shortModelName(model.id)}`}
      >
        <header className="flow-model-header">
          <span className="flow-provider-icon" aria-hidden="true">
            {providerName(model.id).charAt(0)}
          </span>
          <span className="flow-model-identity">
            <strong title={shortModelName(model.id)}>{shortModelName(model.id)}</strong>
            <small>{providerName(model.id)}</small>
          </span>
          <span className={`flow-model-dot flow-model-dot--${connectionState}`} />
        </header>
        <div className="flow-model-stages">
          <StageStatus
            label="Answer"
            status={model.stage1}
            attempts={model.attempts?.stage1}
            elapsed={model.elapsed?.stage1}
            usage={model.usage?.stage1}
            error={model.errors?.stage1}
          />
          <StageStatus
            label="Evaluate"
            status={model.stage2}
            attempts={model.attempts?.stage2}
            elapsed={model.elapsed?.stage2}
            usage={model.usage?.stage2}
            error={model.errors?.stage2}
          />
        </div>
      </button>
    </div>
  );
}

export default function CouncilFlow({ progress, isLoading = false }) {
  const [collapsed, setCollapsed] = useState(false);
  const [selection, setSelection] = useState(null);
  const phase = progress?.phase || (isLoading ? 'connecting' : 'ready');
  const models = progress?.models || [];
  const chairman = progress?.chairman || {};
  const selectedNode = selection?.kind === 'chairman'
    ? { ...chairman, kind: 'chairman' }
    : (
        models.find((model) => model.id === selection?.id)
          ? { ...models.find((model) => model.id === selection.id), kind: 'model' }
          : null
      );

  const isSettled = (status) => ['complete', 'failed', 'skipped'].includes(status);
  const modelTasks = models.reduce(
    (count, model) => (
      count
      + Number(isSettled(model.stage1))
      + Number(isSettled(model.stage2))
    ),
    0,
  );
  const settledTasks = modelTasks + Number(isSettled(chairman.stage3));

  const totalTasks = models.length * 2 + (chairman.id ? 1 : 0);
  const percent = totalTasks ? Math.round((settledTasks / totalTasks) * 100) : 0;
  const live = ['connecting', 'stage1', 'stage2', 'stage3'].includes(phase);
  const hasFailures = (
    models.some((model) => (
      model.stage1 === 'failed' || model.stage2 === 'failed'
    ))
    || chairman.stage3 === 'failed'
  );
  const phaseLabel = (
    phase === 'complete' && hasFailures
      ? 'Council finished with one or more failed calls'
      : PHASE_LABELS[phase] || PHASE_LABELS.ready
  );

  return (
    <section className={`council-flow council-flow--${phase}${collapsed ? ' council-flow--collapsed' : ''}`}>
      <header className="council-flow-toolbar">
        <div className="council-flow-title-wrap">
          <span className={`council-live-dot${live ? ' council-live-dot--active' : ''}`} aria-hidden="true" />
          <div>
            <h2>LLM Council Flow</h2>
            <p>{progress?.error || phaseLabel}</p>
          </div>
        </div>
        <div className="council-flow-actions">
          {totalTasks > 0 && <span className="council-progress-count">{percent}%</span>}
          <button
            type="button"
            className="council-flow-toggle"
            onClick={() => setCollapsed((value) => !value)}
            aria-expanded={!collapsed}
          >
            {collapsed ? 'Show flow' : 'Hide flow'}
          </button>
        </div>
      </header>

      {!collapsed && (
        <div className="council-flow-body">
          {models.length === 0 ? (
            <div className="council-flow-empty">
              Select council members in the sidebar, then send a message to watch the live flow.
            </div>
          ) : (
            <div className="flow-network">
              <div className={`flow-question-node flow-question-node--${live ? 'active' : phase}`}>
                <span className="flow-question-icon" aria-hidden="true">?</span>
                <span>
                  <strong>User request</strong>
                  <small>{live ? 'Dispatching to council' : phase === 'complete' ? 'Processed' : 'Ready to send'}</small>
                </span>
              </div>

              <div className={`flow-trunk flow-trunk--${phase}`} aria-hidden="true">
                <span className="flow-packet" />
              </div>

              <div className="flow-model-grid">
                {models.map((model) => (
                  <ModelNode
                    key={model.id}
                    model={model}
                    selected={selection?.kind === 'model' && selection.id === model.id}
                    onSelect={() => setSelection((previous) => (
                      previous?.kind === 'model' && previous.id === model.id
                        ? null
                        : { kind: 'model', id: model.id }
                    ))}
                  />
                ))}
              </div>

              <div className={`flow-synthesis-line flow-synthesis-line--${chairman.stage3 || 'pending'}`} aria-hidden="true">
                <span className="flow-packet" />
              </div>

              <button
                type="button"
                className={`flow-chairman flow-chairman--${chairman.stage3 || 'pending'}${selection?.kind === 'chairman' ? ' flow-chairman--selected' : ''}`}
                onClick={() => setSelection((previous) => (
                  previous?.kind === 'chairman' ? null : { kind: 'chairman', id: chairman.id }
                ))}
                aria-pressed={selection?.kind === 'chairman'}
                title="Open Chairman run details"
              >
                <div className="flow-chairman-crown" aria-hidden="true">◆</div>
                <div className="flow-chairman-copy">
                  <small>Chairman · final synthesis</small>
                  <strong title={shortModelName(chairman.id)}>{shortModelName(chairman.id)}</strong>
                </div>
                <StageStatus
                  label="Synthesis"
                  status={chairman.stage3 || 'pending'}
                  attempts={chairman.attempts?.stage3}
                  elapsed={chairman.elapsed?.stage3}
                  usage={chairman.usage?.stage3}
                  error={chairman.errors?.stage3}
                />
              </button>
              <RunDetails node={selectedNode} onClose={() => setSelection(null)} />
            </div>
          )}
        </div>
      )}
    </section>
  );
}
