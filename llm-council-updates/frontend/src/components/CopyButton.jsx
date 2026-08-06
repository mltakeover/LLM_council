import { useState } from 'react';
import './CopyButton.css';

/** Small copy-to-clipboard button with a brief "Copied" confirmation. */
export default function CopyButton({ text, className = '', label = 'Copy' }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch (error) {
      // Fallback for contexts without Clipboard API access (e.g. non-HTTPS).
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      try {
        document.execCommand('copy');
      } catch {
        console.error('Copy failed:', error);
      }
      document.body.removeChild(textarea);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <button
      type="button"
      className={`copy-button ${className}`}
      onClick={handleCopy}
      aria-label={copied ? 'Copied to clipboard' : label}
    >
      {copied ? '✓ Copied' : label}
    </button>
  );
}
