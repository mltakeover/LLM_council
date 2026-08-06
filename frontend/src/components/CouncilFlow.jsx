import { useMemo, useState } from 'react';
import { shortModelName as shortModelId, providerName as providerOf } from '../utils/modelDisplay';
import './CouncilFlow.css';

const PHASE_LABELS = {
  ready: 'Ready',
  connecting: 'Connecting',
  stage1: 'Collecting independent answers',
  stage2: 'Peer review and ranking',
  stage3: 'Chairman synthesis',
  complete: 'Council complete',
  error: 'Council stopped',
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
    complete: 'Completed',
    failed: 'Failed',
  }[status] || 'Waiting';
}

function StageStatus({ label, status = 'pending' }) {
  return (
    <div className={`flow-stage flow-stage--${status}`}>
      <span className="flow-stage-indicator" aria-hidden="true" />
      <span className="flow-stage-label">{label}</span>
      <span className="flow-stage-state">{statusText(status)}</span>
    </div>
  );
}

function ModelNode({ model }) {
  const stageStates = [model.stage1, model.stage2];
  const connectionState = stageStates.includes('active')
    ? 'active'
    : stageStates.every((status) => status === 'complete')
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
      <article className={`flow-model-card flow-model-card--${connectionState}`}>
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
          <StageStatus label="Answer" status={model.stage1} />
          <StageStatus label="Review" status={model.stage2} />
        </div>
      </article>
    </div>
  );
}

export default function CouncilFlow({ progress, isLoading = false }) {
  const [collapsed, setCollapsed] = useState(false);
  const phase = progress?.phase || (isLoading ? 'connecting' : 'ready');
  const models = progress?.models || [];
  const chairman = progress?.chairman || {};

  const settledTasks = useMemo(() => {
    const isSettled = (status) => (
      status === 'complete' || status === 'failed'
    );
    const modelTasks = models.reduce(
      (count, model) => (
        count
        + Number(isSettled(model.stage1))
        + Number(isSettled(model.stage2))
      ),
      0,
    );
    return modelTasks + Number(isSettled(chairman.stage3));
  }, [models, chairman.stage3]);

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
                {models.map((model) => <ModelNode key={model.id} model={model} />)}
              </div>

              <div className={`flow-synthesis-line flow-synthesis-line--${chairman.stage3 || 'pending'}`} aria-hidden="true">
                <span className="flow-packet" />
              </div>

              <article className={`flow-chairman flow-chairman--${chairman.stage3 || 'pending'}`}>
                <div className="flow-chairman-crown" aria-hidden="true">◆</div>
                <div className="flow-chairman-copy">
                  <small>Chairman · final synthesis</small>
                  <strong title={shortModelName(chairman.id)}>{shortModelName(chairman.id)}</strong>
                </div>
                <StageStatus label="Synthesis" status={chairman.stage3 || 'pending'} />
              </article>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
