import Markdown from './Markdown';
import CopyButton from './CopyButton';
import { shortModelName } from '../utils/modelDisplay';
import './Stage3.css';

function formatDuration(seconds) {
  return seconds == null ? null : `${seconds.toFixed(1)}s`;
}

export default function Stage3({ finalResponse }) {
  if (!finalResponse) {
    return null;
  }

  const duration = formatDuration(finalResponse.elapsed_seconds);

  return (
    <div className="stage stage3">
      <h3 className="stage-title">Stage 3: Final Council Answer</h3>
      <div className="final-response">
        <div className="final-response-header">
          <div className="chairman-label">
            Chairman: {shortModelName(finalResponse.model)}
            {duration && <span className="model-timing"> · {duration}</span>}
          </div>
          <CopyButton text={finalResponse.response} label="Copy answer" />
        </div>
        <div className="final-text markdown-content">
          <Markdown>{finalResponse.response}</Markdown>
        </div>
      </div>
    </div>
  );
}
