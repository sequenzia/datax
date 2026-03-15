import { useRef, useCallback, useEffect, type KeyboardEvent, type FormEvent } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DatasourceSelector, SelectedSourceChips } from "@/components/chat/datasource-selector";
import type { Dataset, Connection, DataSource } from "@/types/api";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  /** Optional message displayed when the input is disabled */
  disabledMessage?: string | null;
  /** Optional initial value to pre-fill the input */
  initialValue?: string | null;
  datasets?: Dataset[];
  connections?: Connection[];
  selectedSources?: DataSource[];
  onToggleSource?: (source: DataSource) => void;
  onClearSources?: () => void;
}

/**
 * Chat text input with Cmd/Ctrl+Enter to send and a send button.
 * Prevents empty submissions.
 */
export function ChatInput({
  onSend,
  disabled = false,
  disabledMessage = null,
  initialValue = null,
  datasets = [],
  connections = [],
  selectedSources = [],
  onToggleSource,
  onClearSources,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Pre-fill textarea when initialValue changes
  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea || !initialValue) return;

    textarea.value = initialValue;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
    textarea.focus();
  }, [initialValue]);

  const handleSubmit = useCallback(
    (e?: FormEvent) => {
      e?.preventDefault();
      const textarea = textareaRef.current;
      if (!textarea) return;

      const value = textarea.value.trim();
      if (!value || disabled) return;

      onSend(value);
      textarea.value = "";
      textarea.style.height = "auto";
    },
    [onSend, disabled],
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
    <div data-testid="chat-input-container">
      {disabled && disabledMessage && (
        <div
          className="border-t border-border bg-muted/50 px-3 py-1.5 text-center text-xs text-muted-foreground"
          data-testid="chat-disabled-message"
        >
          {disabledMessage}
        </div>
      )}
      <SelectedSourceChips selectedSources={selectedSources} onRemove={(s) => onToggleSource?.(s)} />
      <form
        onSubmit={handleSubmit}
        className="flex items-end gap-2 border-t border-border bg-background px-3 py-3"
        data-testid="chat-input-form"
      >
        {onToggleSource && (
          <DatasourceSelector
            datasets={datasets}
            connections={connections}
            selectedSources={selectedSources}
            onToggle={onToggleSource}
            onClear={() => onClearSources?.()}
            disabled={disabled}
          />
        )}
        <textarea
          ref={textareaRef}
          placeholder={disabled && disabledMessage ? disabledMessage : "Ask a question about your data..."}
          className="flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
          rows={1}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          disabled={disabled}
          data-testid="chat-input"
          aria-label="Chat message input"
        />
        <Button
          type="submit"
          size="icon"
          disabled={disabled}
          data-testid="send-button"
          aria-label="Send message"
        >
          <Send className="size-4" />
        </Button>
        <span className="sr-only">
          Press Cmd+Enter or Ctrl+Enter to send
        </span>
      </form>
    </div>
  );
}
