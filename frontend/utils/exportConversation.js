/**
 * Build a Markdown export of a full conversation (all council stages) and
 * trigger a browser download. Entirely client-side, no backend endpoint.
 */

function formatDuration(seconds) {
  if (seconds == null) return '';
  return ` (${seconds.toFixed(1)}s)`;
}

export function conversationToMarkdown(conversation) {
  const lines = [`# ${conversation.title || 'LLM Council Conversation'}`, ''];

  conversation.messages.forEach((message) => {
    if (message.role === 'user') {
      lines.push('## 🧑 You', '', message.content, '');
      return;
    }

    if (message.stage1?.length) {
      lines.push('## Stage 1: Individual Responses', '');
      message.stage1.forEach((result) => {
        lines.push(
          `### ${result.model}${formatDuration(result.elapsed_seconds)}`,
          '',
          result.response,
          ''
        );
      });
    }

    if (message.stage2?.length) {
      lines.push('## Stage 2: Peer Rankings', '');
      message.stage2.forEach((result) => {
        lines.push(
          `### ${result.model}${formatDuration(result.elapsed_seconds)}`,
          '',
          result.ranking,
          ''
        );
      });
    }

    if (message.stage3) {
      const heading = `## Stage 3: Final Answer — Chairman: ${message.stage3.model}`
        + formatDuration(message.stage3.elapsed_seconds);
      lines.push(heading, '', message.stage3.response, '');
    }
  });

  return lines.join('\n');
}

export function downloadConversationMarkdown(conversation) {
  const markdown = conversationToMarkdown(conversation);
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);

  const safeTitle = (conversation.title || 'conversation')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'conversation';

  const link = document.createElement('a');
  link.href = url;
  link.download = `${safeTitle}.md`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
