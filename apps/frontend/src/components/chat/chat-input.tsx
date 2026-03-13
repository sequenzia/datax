import { useRef, useCallback, type KeyboardEvent, type FormEvent } from "react";
import { Send, Square } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ChatInputProps {
  onSend: (message: string) => void;
  onCancel?: () => void;
  isStreaming: boolean;
  disabled?: boolean;
}

/**
 * Chat text input with Cmd/Ctrl+Enter to send and a send/cancel button.
 * Prevents empty submissions.
 */
export function ChatInput({
  onSend,
  onCancel,
  isStreaming,
  disabled = false,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = useCallback(
    (e?: FormEvent) => {
      e?.preventDefault();
      const textarea = textareaRef.current;
      if (!textarea) return;

      const value = textarea.value.trim();
      if (!value || isStreaming || disabled) return;

      onSend(value);
      textarea.value = "";
      textarea.style.height = "auto";
    },
    [onSend, isStreaming, disabled],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const handleInput = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
  }, []);

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-end gap-2 border-t border-border bg-background px-3 py-3"
      data-testid="chat-input-form"
    >
      <textarea
        ref={textareaRef}
        placeholder="Ask a question about your data..."
        className="flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
        rows={1}
        onKeyDown={handleKeyDown}
        onInput={handleInput}
        disabled={disabled}
        data-testid="chat-input"
        aria-label="Chat message input"
      />
      {isStreaming ? (
        <Button
          type="button"
          size="icon"
          variant="destructive"
          onClick={onCancel}
          data-testid="cancel-stream-button"
          aria-label="Cancel streaming"
        >
          <Square className="size-4" />
        </Button>
      ) : (
        <Button
          type="submit"
          size="icon"
          disabled={disabled}
          data-testid="send-button"
          aria-label="Send message"
        >
          <Send className="size-4" />
        </Button>
      )}
      <span className="sr-only">
        Press Cmd+Enter or Ctrl+Enter to send
      </span>
    </form>
  );
}
