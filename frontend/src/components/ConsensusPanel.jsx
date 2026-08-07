import { shortModelName } from '../utils/modelDisplay';
import './ConsensusPanel.css';

function agreementLabel(value) {
  return {
    unanimous: 'Unanimous ranking',
    strong: 'Strong ranking agreement',
    moderate: 'Moderate ranking agreement',
    split: 'Split ranking',
    insufficient: 'Insufficient ranking data',
  }[value] || 'Agreement unavailable';
}

export default function ConsensusPanel({ report, metrics }) {
  const consensus = report?.consensus || [];
  const disagreements = report?.disagreements || [];
  if (!report && !metrics) return null;

  const percentage = metrics?.top_choice_share == null
    ? null
    : Math.round(metrics.top_choice_share * 100);
  const tiedModels = (metrics?.tied_top_choice_models || [])
    .map(shortModelName)
    .filter(Boolean);

  return (
    <section className="consensus-panel" aria-labelledby="consensus-title">
      <header>
        <div>
          <span className="dashboard-kicker">COUNCIL SIGNAL</span>
          <h4 id="consensus-title">Consensus and dissent</h4>
        </div>
        <div className={`agreement-badge agreement-badge--${metrics?.agreement_level || 'insufficient'}`}>
          <strong>{agreementLabel(metrics?.agreement_level)}</strong>
          {percentage != null && (
            <span>
              {tiedModels.length > 1 ? (
                <>
                  {metrics.top_choice_votes} vote(s) each for {tiedModels.join(', ')} ({percentage}%)
                </>
              ) : (
                <>
                  {metrics.top_choice_votes}/{metrics.valid_ranking_count} reviewers preferred{' '}
                  {shortModelName(metrics.top_choice_model) || 'the leading response'} ({percentage}%)
                </>
              )}
            </span>
          )}
        </div>
      </header>
      <div className="consensus-columns">
        <section>
          <h5><span className="consensus-icon consensus-icon--agree">✓</span> Areas of agreement</h5>
          {consensus.length ? <ul>{consensus.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul> : <p>No explicit semantic consensus was returned.</p>}
        </section>
        <section>
          <h5><span className="consensus-icon consensus-icon--dissent">!</span> Material disagreements</h5>
          {disagreements.length ? <ul>{disagreements.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul> : <p>No material disagreement was identified.</p>}
        </section>
      </div>
      <small className="consensus-caveat">Ranking agreement measures first-choice votes. Semantic agreement is supplied by the structured Chairman report.</small>
    </section>
  );
}
