import './AdaptiveReport.css';
import { councilModeLabel } from '../utils/councilMode';

function List({ values }) {
  if (!values?.length) return null;
  return <ul>{values.map((value, index) => <li key={`${value}-${index}`}>{value}</li>)}</ul>;
}

export default function AdaptiveReport({ report }) {
  if (!report) return null;

  return (
    <section className="adaptive-report" aria-labelledby="adaptive-report-title">
      <header className="adaptive-report-header">
        <div>
          <span className="dashboard-kicker">ADAPTIVE SYNTHESIS</span>
          <h4 id="adaptive-report-title">{councilModeLabel(report.mode)} council output</h4>
        </div>
        <span className={`mode-pill mode-pill--${report.mode || 'ask'}`}>
          {councilModeLabel(report.mode)}
        </span>
      </header>

      {report.executive_summary && (
        <article className="adaptive-summary">
          <h5>Executive summary</h5>
          <p>{report.executive_summary}</p>
        </article>
      )}

      {report.direct_answer && (
        <article className="adaptive-answer">
          <h5>Direct answer</h5>
          <p>{report.direct_answer}</p>
        </article>
      )}

      {(report.verdict || report.recommendation) && (
        <div className="adaptive-decision-row">
          {report.verdict && (
            <article><span>Verdict</span><strong>{report.verdict}</strong></article>
          )}
          {report.recommendation && (
            <article><span>Recommendation</span><strong>{report.recommendation}</strong></article>
          )}
        </div>
      )}

      {report.options?.length > 0 && (
        <section className="adaptive-section">
          <h5>Options</h5>
          <div className="adaptive-card-grid">
            {report.options.map((option, index) => (
              <article key={`${option.name}-${index}`}>
                <h6>{option.name}</h6>
                <p>{option.summary}</p>
                {option.benefits?.length > 0 && <><strong>Benefits</strong><List values={option.benefits} /></>}
                {option.drawbacks?.length > 0 && <><strong>Drawbacks</strong><List values={option.drawbacks} /></>}
                {option.risks?.length > 0 && <><strong>Risks</strong><List values={option.risks} /></>}
                {option.best_for && <small><b>Best for:</b> {option.best_for}</small>}
              </article>
            ))}
          </div>
        </section>
      )}

      {report.positions?.length > 0 && (
        <section className="adaptive-section">
          <h5>Debate positions</h5>
          <div className="adaptive-card-grid">
            {report.positions.map((position, index) => (
              <article key={`${position.position}-${index}`}>
                <h6>{position.position}</h6>
                <strong>Strongest arguments</strong>
                <List values={position.strongest_arguments} />
                {position.weaknesses?.length > 0 && <><strong>Weaknesses</strong><List values={position.weaknesses} /></>}
              </article>
            ))}
          </div>
        </section>
      )}

      {report.ideas?.length > 0 && (
        <section className="adaptive-section">
          <h5>Idea board</h5>
          <div className="adaptive-card-grid">
            {report.ideas.map((idea, index) => (
              <article key={`${idea.title}-${index}`}>
                <h6>{idea.title}</h6>
                <p>{idea.description}</p>
                {idea.value && <small><b>Value:</b> {idea.value}</small>}
                <List values={idea.considerations} />
              </article>
            ))}
          </div>
        </section>
      )}

      {report.comparison?.length > 0 && (
        <section className="adaptive-section">
          <h5>Comparison</h5>
          <div className="adaptive-card-grid">
            {report.comparison.map((item, index) => (
              <article key={`${item.subject}-${index}`}>
                <h6>{item.subject}</h6>
                {item.strengths?.length > 0 && <><strong>Strengths</strong><List values={item.strengths} /></>}
                {item.weaknesses?.length > 0 && <><strong>Weaknesses</strong><List values={item.weaknesses} /></>}
                {item.best_for && <small><b>Best for:</b> {item.best_for}</small>}
              </article>
            ))}
          </div>
        </section>
      )}

      {report.plan_steps?.length > 0 && (
        <section className="adaptive-section">
          <h5>Action plan</h5>
          <ol className="adaptive-plan">
            {[...report.plan_steps]
              .sort((left, right) => left.order - right.order)
              .map((step) => (
                <li key={`${step.order}-${step.title}`}>
                  <span>{step.order}</span>
                  <div>
                    <h6>{step.title}</h6>
                    <p>{step.action}</p>
                    {step.outcome && <small><b>Outcome:</b> {step.outcome}</small>}
                    <List values={step.dependencies} />
                  </div>
                </li>
              ))}
          </ol>
        </section>
      )}

      {report.claims?.length > 0 && (
        <section className="adaptive-section">
          <h5>Claim assessment</h5>
          <div className="adaptive-claims">
            {report.claims.map((claim, index) => (
              <article key={`${claim.claim}-${index}`}>
                <span className={`claim-verdict claim-verdict--${claim.verdict}`}>
                  {councilModeLabel(claim.verdict)}
                </span>
                <h6>{claim.claim}</h6>
                <p><b>Evidence:</b> {claim.evidence}</p>
                {claim.uncertainty && <p><b>Uncertainty:</b> {claim.uncertainty}</p>}
              </article>
            ))}
          </div>
        </section>
      )}

      {report.contribution_ledger?.length > 0 && (
        <details className="adaptive-contribution-ledger">
          <summary>Contribution ledger · {report.contribution_ledger.length} workers</summary>
          <div className="adaptive-card-grid">
            {report.contribution_ledger.map((item, index) => (
              <article key={`${item.worker_model}-${index}`}>
                <span className={`claim-verdict claim-verdict--${item.decision}`}>
                  {councilModeLabel(item.decision)}
                </span>
                <h6>{item.role}</h6>
                <small>{item.worker_model}</small>
                <p>{item.reason}</p>
                <List values={item.evidence} />
              </article>
            ))}
          </div>
        </details>
      )}

      {(
        report.key_points?.length > 0
        || report.themes?.length > 0
        || report.next_steps?.length > 0
        || report.uncertainties?.length > 0
        || report.assumptions?.length > 0
        || report.dependencies?.length > 0
        || report.open_questions?.length > 0
      ) && (
        <div className="adaptive-list-grid">
          {report.key_points?.length > 0 && <section><h5>Key points</h5><List values={report.key_points} /></section>}
          {report.themes?.length > 0 && <section><h5>Themes</h5><List values={report.themes} /></section>}
          {report.next_steps?.length > 0 && <section><h5>Next steps</h5><List values={report.next_steps} /></section>}
          {report.uncertainties?.length > 0 && <section><h5>Uncertainties</h5><List values={report.uncertainties} /></section>}
          {report.assumptions?.length > 0 && <section><h5>Assumptions</h5><List values={report.assumptions} /></section>}
          {report.dependencies?.length > 0 && <section><h5>Dependencies</h5><List values={report.dependencies} /></section>}
          {report.open_questions?.length > 0 && <section><h5>Open questions</h5><List values={report.open_questions} /></section>}
        </div>
      )}
    </section>
  );
}
