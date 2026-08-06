import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import CopyButton from './CopyButton';
import './Markdown.css';

/** Recursively pull the raw text out of a React children tree. Needed
 * because rehype-highlight wraps code in nested <span> token elements, so
 * `String(children)` alone would just stringify React objects. */
function extractText(node) {
  if (node == null || typeof node === 'boolean') return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(extractText).join('');
  if (node.props && node.props.children != null) {
    return extractText(node.props.children);
  }
  return '';
}

function Pre({ children, ...props }) {
  const text = extractText(children).replace(/\n$/, '');

  return (
    <div className="code-block-wrapper">
      {text && (
        <CopyButton text={text} className="code-block-copy" label="Copy" />
      )}
      <pre {...props}>{children}</pre>
    </div>
  );
}

/** Shared Markdown renderer: GitHub-flavored code highlighting plus a
 * hover-revealed copy button on every fenced code block. */
export default function Markdown({ children }) {
  return (
    <ReactMarkdown rehypePlugins={[rehypeHighlight]} components={{ pre: Pre }}>
      {children}
    </ReactMarkdown>
  );
}
