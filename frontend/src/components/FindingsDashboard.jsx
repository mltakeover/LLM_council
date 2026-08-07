import { useMemo, useState } from 'react';
import './FindingsDashboard.css';

const SEVERITIES = ['critical', 'high', 'medium', 'low', 'information'];

function label(value) {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : 'Uncategorised';
}

export default function FindingsDashboard({ report }) {
  const [groupBy, setGroupBy] = useState('severity');
  const [severityFilter, setSeverityFilter] = useState('all');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const findings = useMemo(() => report?.findings || [], [report]);

  const categories = useMemo(() => (
    [...new Set(findings.map((finding) => finding.category).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b))
  ), [findings]);

  const filtered = findings.filter((finding) => (
    (severityFilter === 'all' || finding.severity === severityFilter)
    && (categoryFilter === 'all' || finding.category === categoryFilter)
  ));

  const groups = useMemo(() => {
    const values = groupBy === 'severity'
      ? SEVERITIES.filter((severity) => filtered.some((finding) => finding.severity === severity))
      : [...new Set(filtered.map((finding) => finding.category || 'Uncategorised'))]
          .sort((a, b) => a.localeCompare(b));
    return values.map((value) => ({
      value,
      findings: filtered.filter((finding) => (
        groupBy === 'severity'
          ? finding.severity === value
          : (finding.category || 'Uncategorised') === value
      )),
    }));
  }, [filtered, groupBy]);

  if (!report) return null;

  return (
    <section className="findings-dashboard" aria-labelledby="findings-dashboard-title">
      <header className="findings-dashboard-header">
        <div>
          <span className="dashboard-kicker">STRUCTURED FINDINGS</span>
          <h4 id="findings-dashboard-title">Findings dashboard</h4>
          <p>Filter and group the Chairman&apos;s evidence-backed findings.</p>
        </div>
        <div className="finding-counts" aria-label="Finding counts by severity">
          {SEVERITIES.map((severity) => {
            const count = findings.filter((finding) => finding.severity === severity).length;
            return (
              <span key={severity} className={`finding-count finding-count--${severity}`}>
                {label(severity)} <strong>{count}</strong>
              </span>
            );
          })}
        </div>
      </header>

      <div className="findings-controls">
        <label>
          <span>Group by</span>
          <select value={groupBy} onChange={(event) => setGroupBy(event.target.value)}>
            <option value="severity">Severity</option>
            <option value="category">Category</option>
          </select>
        </label>
        <label>
          <span>Severity</span>
          <select value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value)}>
            <option value="all">All severities</option>
            {SEVERITIES.map((severity) => <option key={severity} value={severity}>{label(severity)}</option>)}
          </select>
        </label>
        <label>
          <span>Category</span>
          <select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
            <option value="all">All categories</option>
            {categories.map((category) => <option key={category} value={category}>{category}</option>)}
          </select>
        </label>
      </div>

      {groups.length === 0 ? (
        <div className="findings-empty">No findings match the current filters.</div>
      ) : (
        <div className="finding-groups">
          {groups.map((group) => (
            <section className="finding-group" key={group.value}>
              <h5>
                <span className={groupBy === 'severity' ? `severity-dot severity-dot--${group.value}` : 'category-dot'} />
                {label(group.value)}
                <small>{group.findings.length}</small>
              </h5>
              <div className="finding-card-grid">
                {group.findings.map((finding, index) => (
                  <article className={`finding-card finding-card--${finding.severity}`} key={`${finding.title}-${index}`}>
                    <header>
                      <span>{finding.category}</span>
                      <strong>{label(finding.severity)}</strong>
                    </header>
                    <h6>{finding.title}</h6>
                    <dl>
                      <div><dt>Evidence</dt><dd>{finding.evidence}</dd></div>
                      <div><dt>Impact</dt><dd>{finding.impact}</dd></div>
                      <div><dt>Recommendation</dt><dd>{finding.recommendation}</dd></div>
                    </dl>
                  </article>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </section>
  );
}
