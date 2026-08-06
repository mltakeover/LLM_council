import { useState } from 'react';
import Markdown from './Markdown';
import { shortModelName } from '../utils/modelDisplay';
import './Stage2.css';

function deAnonymizeText(text, labelToModel) {
  if (!labelToModel) return text;

  let result = text;
  // Replace each "Response X" with the actual model name
  Object.entries(labelToModel).forEach(([label, model]) => {
    result = result.replace(new RegExp(label, 'g'), `**${shortModelName(model)}**`);
  });
  return result;
}

function formatDuration(seconds) {
  return seconds == null ? null : `${seconds.toFixed(1)}s`;
}

export default function Stage2({ rankings, labelToModel, aggregateRankings }) {
  const [activeTab, setActiveTab] = useState(0);

  if (!rankings || rankings.length === 0) {
    return null;
  }

  const handleTabKeyDown = (event) => {
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      setActiveTab((previous) => (previous + 1) % rankings.length);
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      setActiveTab((previous) => (
        (previous - 1 + rankings.length) % rankings.length
      ));
    }
  };

  const active = rankings[activeTab];
  const duration = formatDuration(active.elapsed_seconds);

  return (
    <div className="stage stage2">
      <h3 className="stage-title">Stage 2: Peer Rankings</h3>

      <h4>Raw Evaluations</h4>
      <p className="stage-description">
        Each model evaluated all responses (anonymized as Response A, B, C, etc.) and provided rankings.
        Below, model names are shown in <strong>bold</strong> for readability, but the original evaluation used anonymous labels.
      </p>

      <div
        className="tabs"
        role="tablist"
        aria-label="Peer ranking evaluations"
        onKeyDown={handleTabKeyDown}
      >
        {rankings.map((rank, index) => (
          <button
            key={index}
            id={`stage2-tab-${index}`}
            role="tab"
            type="button"
            aria-selected={activeTab === index}
            aria-controls={`stage2-panel-${index}`}
            tabIndex={activeTab === index ? 0 : -1}
            className={`tab ${activeTab === index ? 'active' : ''}`}
            onClick={() => setActiveTab(index)}
          >
            {shortModelName(rank.model)}
          </button>
        ))}
      </div>

      <div
        className="tab-content"
        role="tabpanel"
        id={`stage2-panel-${activeTab}`}
        aria-labelledby={`stage2-tab-${activeTab}`}
      >
        <div className="ranking-model">
          {active.model}
          {duration && <span className="model-timing"> · {duration}</span>}
        </div>
        <div className="ranking-content markdown-content">
          <Markdown>
            {deAnonymizeText(active.ranking, labelToModel)}
          </Markdown>
        </div>

        {active.parsed_ranking && active.parsed_ranking.length > 0 && (
          <div className="parsed-ranking">
            <strong>Extracted Ranking:</strong>
            <ol>
              {active.parsed_ranking.map((label, i) => (
                <li key={i}>
                  {labelToModel && labelToModel[label]
                    ? shortModelName(labelToModel[label])
                    : label}
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>

      {aggregateRankings && aggregateRankings.length > 0 && (
        <div className="aggregate-rankings">
          <h4>Aggregate Rankings (Street Cred)</h4>
          <p className="stage-description">
            Combined results across all peer evaluations (lower score is better):
          </p>
          <div className="aggregate-list">
            {aggregateRankings.map((agg, index) => (
              <div key={index} className="aggregate-item">
                <span className="rank-position">#{index + 1}</span>
                <span className="rank-model">
                  {shortModelName(agg.model)}
                </span>
                <span className="rank-score">
                  Avg: {agg.average_rank.toFixed(2)}
                </span>
                <span className="rank-count">
                  ({agg.rankings_count} votes)
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
