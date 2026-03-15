/**
 * FollowUpSuggestions - Contextual follow-up suggestion chips.
 *
 * Renders 2-3 clickable suggestion chips below query results when the AI
 * detects interesting patterns (outliers, trends, skewed distributions,
 * unexpected nulls). Clicking a chip sends it as a new message to the AI.
 *
 * Not rendered when:
 * - No suggestions are provided
 * - The suggestions array is empty
 */

import { Lightbulb } from "lucide-react";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/stores/chat-store";

/* -------------------------------------------------------------------------- */
/*  Types                                                                      */
/* -------------------------------------------------------------------------- */

export interface FollowUpSuggestion {
  /** The suggested question text to send to the AI */
  question: string;
  /** Brief rationale explaining why this is suggested (e.g., "3 outliers detected") */
  reasoning: string;
}

export interface FollowUpSuggestionsProps {
  /** Array of 2-3 follow-up suggestions */
  suggestions: FollowUpSuggestion[];
  /** Additional CSS classes */
  className?: string;
}

/* -------------------------------------------------------------------------- */
/*  Component                                                                  */
/* -------------------------------------------------------------------------- */

export function FollowUpSuggestions({
  suggestions,
  className,
}: FollowUpSuggestionsProps) {
  if (!suggestions || suggestions.length === 0) {
    return null;
  }

  const handleChipClick = (question: string) => {
    void useChatStore.getState().sendMessage(question);
  };

  return (
    <div
      data-testid="follow-up-suggestions"
      className={cn("mt-3 space-y-2", className)}
    >
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Lightbulb className="size-3.5" />
        <span>Suggested follow-ups</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {suggestions.map((suggestion, index) => (
          <button
            key={index}
            data-testid={`suggestion-chip-${index}`}
            onClick={() => handleChipClick(suggestion.question)}
            className={cn(
              "group inline-flex flex-col items-start gap-0.5 rounded-lg border border-border",
              "bg-muted/50 px-3 py-2 text-left text-sm transition-colors",
              "hover:border-primary/50 hover:bg-primary/5",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            )}
          >
            <span
              className="font-medium text-foreground"
              data-testid={`suggestion-text-${index}`}
            >
              {suggestion.question}
            </span>
            <span
              className="text-xs text-muted-foreground"
              data-testid={`suggestion-rationale-${index}`}
            >
              {suggestion.reasoning}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
