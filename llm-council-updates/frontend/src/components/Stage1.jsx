import { useState } from 'react';
import Markdown from './Markdown';
import { shortModelName } from '../utils/modelDisplay';
import './Stage1.css';

function formatDuration(seconds) {
  return seconds == null ? null : `${seconds.toFixed(1)}s`;
}

export default function Stage1({ responses }) {
  const [activeTab, setActiveTab] = useState(0);

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

  const active = responses[activeTab];
  const duration = formatDuration(active.elapsed_seconds);

  return (
    <div className="stage stage1">
      <h3 className="stage-title">Stage 1: Individual Responses</h3>

      <div
        className="tabs"
        role="tablist"
        aria-label="Individual model responses"
        onKeyDown={handleTabKeyDown}
      >
        {responses.map((resp, index) => (
          <button
            key={index}
            id={`stage1-tab-${index}`}
            role="tab"
            type="button"
            aria-selected={activeTab === index}
            aria-controls={`stage1-panel-${index}`}
            tabIndex={activeTab === index ? 0 : -1}
            className={`tab ${activeTab === index ? 'active' : ''}`}
            onClick={() => setActiveTab(index)}
          >
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
        </div>
        <div className="response-text markdown-content">
          <Markdown>{active.response}</Markdown>
        </div>
      </div>
    </div>
  );
}
