import { User, Bot } from "lucide-react";
import { cn } from "@/lib/utils";
import { MarkdownContent } from "./markdown-content";
import { InlineResultBlock } from "./inline-result-block";

interface MessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  /** Message metadata containing SQL, query results, chart config etc. */
  metadata?: Record<string, unknown> | null;
  /** Streaming metadata (accumulated from SSE events during streaming) */
  streamingMetadata?: {
    sql: string | null;
    queryResult: Record<string, unknown> | null;
    chartConfig: Record<string, unknown> | null;
  } | null;
  /** If true, show as streaming (used with StreamingText externally) */
  isStreaming?: boolean;
  children?: React.ReactNode;
}

export function MessageBubble({
  role,
  content,
  metadata,
  streamingMetadata,
  isStreaming = false,
  children,
}: MessageBubbleProps) {
  const isUser = role === "user";

  // Build effective metadata from either finalized metadata or streaming metadata
  const effectiveMetadata = metadata ?? buildStreamingMeta(streamingMetadata);

  return (
    <div
      data-testid={`message-bubble-${role}`}
      className={cn(
        "flex gap-3",
        isUser ? "flex-row-reverse" : "flex-row",
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex size-7 shrink-0 items-center justify-center rounded-full",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-muted-foreground",
        )}
      >
        {isUser ? (
          <User className="size-4" />
        ) : (
          <Bot className="size-4" />
        )}
      </div>

      {/* Message content */}
      <div
        className={cn(
          "min-w-0 max-w-[85%] rounded-lg px-3 py-2 text-sm",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground",
          isStreaming && "min-w-[60px]",
          !isUser && "overflow-x-auto",
        )}
      >
        {children ??
          (isUser ? (
            <p className="whitespace-pre-wrap break-words">{content}</p>
          ) : (
            <MarkdownContent content={content} />
          ))}

        {/* Inline result blocks for assistant messages */}
        {!isUser && effectiveMetadata && (
          <InlineResultBlock metadata={effectiveMetadata} />
        )}
      </div>
    </div>
  );
}

/** Build a metadata-like object from streaming metadata for progressive rendering */
function buildStreamingMeta(
  streaming?: {
    sql: string | null;
    queryResult: Record<string, unknown> | null;
    chartConfig: Record<string, unknown> | null;
  } | null,
): Record<string, unknown> | null {
  if (!streaming) return null;
  const meta: Record<string, unknown> = {};
  if (streaming.sql) meta.sql = streaming.sql;
  if (streaming.queryResult) meta.query_result = streaming.queryResult;
  if (streaming.chartConfig) meta.chart_config = streaming.chartConfig;
  return Object.keys(meta).length > 0 ? meta : null;
}
