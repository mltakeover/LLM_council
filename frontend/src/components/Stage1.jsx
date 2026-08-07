import { useState } from 'react';
import Markdown from './Markdown';
import { providerSlug, shortModelName } from '../utils/modelDisplay';
import './Stage1.css';

function formatDuration(seconds) {
  return seconds == null ? null : `${seconds.toFixed(1)}s`;
}

export default function Stage1({ responses }) {
  const [activeTab, setActiveTab] = useState(0);
  const [view, setView] = useState('tabs');

  if (!responses || responses.length === 0) {
    return null;
  }

  const handleTabKeyDown = (event) => {
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      setActiveTab((previous) => (previous + 1) % responses.length);
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      setActiveTab((previous) => (
        (previous - 1 + responses.length) % responses.length
      ));
    }
  };

  const active = responses[Math.min(activeTab, responses.length - 1)];
  const duration = formatDuration(active.elapsed_seconds);

  const responseMeta = (response) => {
    const parts = [];
    const responseDuration = formatDuration(response.elapsed_seconds);
    if (responseDuration) parts.push(responseDuration);
    if (response.attempts) parts.push(`${response.attempts} attempt${response.attempts === 1 ? '' : 's'}`);
    if (response.usage?.total_tokens) parts.push(`${response.usage.total_tokens.toLocaleString()} tokens`);
    return parts.join(' · ');
  };

  return (
    <div className="stage stage1">
      <div className="stage-heading-row">
        <h3 className="stage-title">Stage 1: Individual Responses</h3>
        {responses.length > 1 && (
          <div className="stage-view-toggle" aria-label="Response view">
            <button type="button" className={view === 'tabs' ? 'active' : ''} onClick={() => setView('tabs')}>Focused</button>
            <button type="button" className={view === 'compare' ? 'active' : ''} onClick={() => setView('compare')}>Compare</button>
          </div>
        )}
      </div>

      {view === 'tabs' ? (
        <>
          <div
            className="tabs"
            role="tablist"
            aria-label="Individual model responses"
            onKeyDown={handleTabKeyDown}
          >
            {responses.map((resp, index) => (
              <button
                key={resp.model}
                id={`stage1-tab-${index}`}
                role="tab"
                type="button"
                aria-selected={activeTab === index}
                aria-controls={`stage1-panel-${index}`}
                tabIndex={activeTab === index ? 0 : -1}
                className={`tab ${activeTab === index ? 'active' : ''}`}
                onClick={() => setActiveTab(index)}
              >
                <span
                  className={`tab-provider-dot tab-provider-dot--${providerSlug(resp.model)}`}
                  aria-hidden="true"
                />
                {shortModelName(resp.model)}
              </button>
            ))}
          </div>

          <div
            className="tab-content"
            role="tabpanel"
            id={`stage1-panel-${activeTab}`}
            aria-labelledby={`stage1-tab-${activeTab}`}
          >
            <div className="model-name">
              {active.model}
              {duration && <span className="model-timing"> · {duration}</span>}
              {active.usage?.total_tokens && <span className="model-timing"> · {active.usage.total_tokens.toLocaleString()} tokens</span>}
            </div>
            {(active.role || active.reviewer_role) && (
              <div className="model-role">Perspective: {active.role || active.reviewer_role}</div>
            )}
            <div className="response-text markdown-content">
              <Markdown>{active.response}</Markdown>
            </div>
          </div>
        </>
      ) : (
        <div className="response-comparison" aria-label="Side-by-side council responses">
          {responses.map((response) => (
            <article className="response-comparison-card" key={response.model}>
              <header>
                <span className={`tab-provider-dot tab-provider-dot--${providerSlug(response.model)}`} aria-hidden="true" />
                <div>
                  <strong>{shortModelName(response.model)}</strong>
                  <small>{response.role || response.reviewer_role || response.model}</small>
                </div>
              </header>
              {responseMeta(response) && <div className="comparison-meta">{responseMeta(response)}</div>}
              <div className="response-text markdown-content">
                <Markdown>{response.response}</Markdown>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
