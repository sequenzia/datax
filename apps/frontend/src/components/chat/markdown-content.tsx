import { useMemo } from "react";
import { Streamdown } from "streamdown";

interface MarkdownContentProps {
  /** The markdown content to render */
  content: string;
}

/**
 * Renders static markdown content for completed assistant messages.
 * Supports headings, bold, italic, code blocks (with SQL highlighting),
 * lists, tables, and clickable links.
 */
export function MarkdownContent({ content }: MarkdownContentProps) {
  const controls = useMemo(
    () => ({
      code: { copy: true, download: false },
      table: { copy: true, download: false, fullscreen: false },
    }),
    [],
  );

  return (
    <div className="streaming-markdown" data-testid="markdown-content">
      <Streamdown mode="static" controls={controls}>
        {content}
      </Streamdown>
    </div>
  );
}
