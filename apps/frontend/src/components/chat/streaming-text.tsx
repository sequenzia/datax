import { useEffect, useRef, useMemo } from "react";
import { Streamdown } from "streamdown";

interface StreamingTextProps {
  /** The accumulated text content being streamed */
  content: string;
  /** Whether streaming is currently active (shows cursor) */
  isStreaming: boolean;
}

/**
 * Renders streaming markdown content using Streamdown.
 * Supports headings, bold, italic, code blocks (with SQL highlighting),
 * lists, tables, links, and more. Shows a blinking caret during streaming.
 */
export function StreamingText({ content, isStreaming }: StreamingTextProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll as content grows during streaming
  useEffect(() => {
    if (isStreaming && containerRef.current) {
      const el = containerRef.current;
      el.scrollTop = el.scrollHeight;
    }
  }, [content, isStreaming]);

  const mode = isStreaming ? "streaming" : "static";

  // Memoize controls config to avoid unnecessary re-renders
  const controls = useMemo(
    () => ({
      code: { copy: true, download: false },
      table: { copy: true, download: false, fullscreen: false },
    }),
    [],
  );

  return (
    <div
      ref={containerRef}
      className="streaming-markdown"
      data-testid="streaming-text"
    >
      <Streamdown
        mode={mode}
        caret={isStreaming ? "block" : undefined}
        controls={controls}
      >
        {content}
      </Streamdown>
      {isStreaming && !content && (
        <span
          className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-foreground align-text-bottom"
          data-testid="streaming-cursor"
          aria-hidden="true"
        />
      )}
    </div>
  );
}
