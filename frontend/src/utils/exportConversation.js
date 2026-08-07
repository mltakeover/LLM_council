/**
 * Build a Markdown export of a full conversation (all council stages) and
 * trigger a browser download. Entirely client-side, no backend endpoint.
 */

function formatDuration(seconds) {
  if (seconds == null) return '';
  return ` (${seconds.toFixed(1)}s)`;
}

function safeFilename(conversation) {
  return (conversation.title || 'conversation')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'conversation';
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
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
  triggerDownload(blob, `${safeFilename(conversation)}.md`);
}

function docxParagraph(line, docx) {
  const { HeadingLevel, Paragraph, TextRun } = docx;
  if (line.startsWith('### ')) {
    return new Paragraph({ text: line.slice(4), heading: HeadingLevel.HEADING_3 });
  }
  if (line.startsWith('## ')) {
    return new Paragraph({ text: line.slice(3), heading: HeadingLevel.HEADING_2 });
  }
  if (line.startsWith('# ')) {
    return new Paragraph({ text: line.slice(2), heading: HeadingLevel.TITLE });
  }
  if (line.startsWith('- ')) {
    return new Paragraph({ text: line.slice(2), bullet: { level: 0 } });
  }
  return new Paragraph({
    children: [new TextRun({ text: line || ' ', font: 'Aptos', size: 22 })],
    spacing: { after: line ? 90 : 30 },
  });
}

export async function downloadConversationDocx(conversation) {
  const docx = await import('docx');
  const { Document, Packer } = docx;
  const lines = conversationToMarkdown(conversation).split('\n');
  const documentFile = new Document({
    creator: 'LLM Council',
    title: conversation.title || 'LLM Council Conversation',
    description: 'Exported multi-model council conversation',
    sections: [{
      properties: {},
      children: lines.map((line) => docxParagraph(line, docx)),
    }],
  });
  const blob = await Packer.toBlob(documentFile);
  triggerDownload(blob, `${safeFilename(conversation)}.docx`);
}

function plainTextForPdf(conversation) {
  return conversationToMarkdown(conversation)
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\*\*/g, '')
    .replace(/`/g, '');
}

export async function downloadConversationPdf(conversation) {
  const { jsPDF } = await import('jspdf');
  const pdf = new jsPDF({ unit: 'mm', format: 'a4' });
  const margin = 16;
  const pageHeight = pdf.internal.pageSize.getHeight();
  const contentWidth = pdf.internal.pageSize.getWidth() - (margin * 2);
  const lines = pdf.splitTextToSize(plainTextForPdf(conversation), contentWidth);
  let y = margin;
  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(10);

  lines.forEach((line) => {
    if (y > pageHeight - margin) {
      pdf.addPage();
      y = margin;
    }
    pdf.text(line, margin, y);
    y += 5;
  });

  const pageCount = pdf.getNumberOfPages();
  for (let page = 1; page <= pageCount; page += 1) {
    pdf.setPage(page);
    pdf.setFontSize(8);
    pdf.setTextColor(100);
    pdf.text(`LLM Council · Page ${page} of ${pageCount}`, margin, pageHeight - 7);
  }
  pdf.save(`${safeFilename(conversation)}.pdf`);
}
