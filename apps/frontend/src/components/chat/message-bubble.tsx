import { User, Bot } from "lucide-react";
import { cn } from "@/lib/utils";
import { MarkdownContent } from "./markdown-content";
import { InlineResultBlock } from "./inline-result-block";

interface MessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  /** Message metadata containing SQL, query results, chart config etc. */
  metadata?: Record<string, unknown> | null;
  children?: React.ReactNode;
}

export function MessageBubble({
  role,
  content,
  metadata,
  children,
}: MessageBubbleProps) {
  const isUser = role === "user";

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
        {!isUser && metadata && (
          <InlineResultBlock metadata={metadata} />
        )}
      </div>
    </div>
  );
}
