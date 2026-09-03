import Markdown from './Markdown';
import CopyButton from './CopyButton';
import ConsensusPanel from './ConsensusPanel';
import FindingsDashboard from './FindingsDashboard';
import AdaptiveReport from './AdaptiveReport';
import { shortModelName } from '../utils/modelDisplay';
import './Stage3.css';

function formatDuration(seconds) {
  return seconds == null ? null : `${seconds.toFixed(1)}s`;
}

export default function Stage3({ finalResponse, metadata }) {
  if (!finalResponse) {
    return null;
  }

  const duration = formatDuration(finalResponse.elapsed_seconds);
  const totalTokens = finalResponse.usage?.total_tokens;
  const hygiene = finalResponse.output_hygiene?.rendered_output;
  const workforce = ['workforce', 'hybrid'].includes(
    metadata?.orchestration_strategy
  );

  return (
    <div className={`stage stage3 ${finalResponse.success === false ? 'stage3--failed' : ''}`}>
      <h3 className="stage-title">
        {finalResponse.success === false
          ? 'Council request stopped'
          : `Stage 3: Final ${workforce ? 'Master' : 'Council'} Answer`}
      </h3>
      <div className="final-response">
        <div className="final-response-header">
          <div className="chairman-label">
            {workforce ? 'Master' : 'Chairman'}: {shortModelName(finalResponse.model)}
            {duration && <span className="model-timing"> · {duration}</span>}
            {totalTokens && <span className="model-timing"> · {totalTokens.toLocaleString()} tokens</span>}
          </div>
          <CopyButton text={finalResponse.response} label="Copy answer" />
        </div>
        {hygiene && (hygiene.removed_count > 0 || hygiene.reported_only_count > 0) && (
          <div className="output-hygiene-summary" role="status">
            <strong>Output hygiene</strong>
            {hygiene.removed_count > 0 && (
              <span>{hygiene.removed_count} safe invisible character{hygiene.removed_count === 1 ? '' : 's'} removed.</span>
            )}
            {hygiene.reported_only_count > 0 && (
              <span>{hygiene.reported_only_count} directional or joining character{hygiene.reported_only_count === 1 ? '' : 's'} reported without alteration.</span>
            )}
          </div>
        )}
        {finalResponse.success !== false && (
          <>
            <ConsensusPanel
              report={finalResponse.structured_report}
              metrics={metadata?.consensus_metrics}
            />
            <AdaptiveReport report={finalResponse.structured_report} />
            {finalResponse.structured_report?.findings?.length > 0 && (
              <FindingsDashboard report={finalResponse.structured_report} />
            )}
          </>
        )}
        {finalResponse.structured_report ? (
          <details className="full-report-details">
            <summary>Full Markdown report</summary>
            <div className="final-text markdown-content">
              <Markdown>{finalResponse.response}</Markdown>
            </div>
          </details>
        ) : (
          <div className="final-text markdown-content">
            <Markdown>{finalResponse.response}</Markdown>
          </div>
        )}
      </div>
    </div>
  );
}
