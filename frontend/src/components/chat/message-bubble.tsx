import { User, Bot } from "lucide-react";
import { cn } from "@/lib/utils";
import { MarkdownContent } from "./markdown-content";

interface MessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  /** If true, show as streaming (used with StreamingText externally) */
  isStreaming?: boolean;
  children?: React.ReactNode;
}

/**
 * Renders a single chat message with role-appropriate styling.
 * User messages are right-aligned with plain text;
 * assistant messages left-aligned with markdown rendering.
 */
export function MessageBubble({
  role,
  content,
  isStreaming = false,
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
          "max-w-[85%] rounded-lg px-3 py-2 text-sm",
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
      </div>
    </div>
  );
}
