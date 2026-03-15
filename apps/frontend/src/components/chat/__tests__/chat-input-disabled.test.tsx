import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ChatInput } from "../chat-input";

describe("ChatInput disabled state", () => {
  const mockOnSend = vi.fn();

  it("shows disabled message when disabled with disabledMessage", () => {
    render(
      <ChatInput
        onSend={mockOnSend}
        
        disabled
        disabledMessage="Configure an AI provider in Settings to start chatting"
      />,
    );

    expect(screen.getByTestId("chat-disabled-message")).toBeInTheDocument();
    expect(screen.getByTestId("chat-disabled-message")).toHaveTextContent(
      "Configure an AI provider in Settings to start chatting",
    );
  });

  it("uses disabled message as placeholder when disabled", () => {
    render(
      <ChatInput
        onSend={mockOnSend}
        
        disabled
        disabledMessage="Configure an AI provider in Settings to start chatting"
      />,
    );

    const input = screen.getByTestId("chat-input");
    expect(input).toHaveAttribute(
      "placeholder",
      "Configure an AI provider in Settings to start chatting",
    );
  });

  it("does not show disabled message when not disabled", () => {
    render(
      <ChatInput
        onSend={mockOnSend}
        
        disabled={false}
        disabledMessage="Some message"
      />,
    );

    expect(screen.queryByTestId("chat-disabled-message")).not.toBeInTheDocument();
  });

  it("does not show disabled message when disabled but no message", () => {
    render(
      <ChatInput onSend={mockOnSend} isStreaming={false} disabled />,
    );

    expect(screen.queryByTestId("chat-disabled-message")).not.toBeInTheDocument();
  });

  it("uses default placeholder when not disabled", () => {
    render(
      <ChatInput onSend={mockOnSend} isStreaming={false} />,
    );

    const input = screen.getByTestId("chat-input");
    expect(input).toHaveAttribute(
      "placeholder",
      "Ask a question about your data...",
    );
  });

  it("disables input and send button when disabled", () => {
    render(
      <ChatInput
        onSend={mockOnSend}
        
        disabled
        disabledMessage="Configure an AI provider in Settings to start chatting"
      />,
    );

    expect(screen.getByTestId("chat-input")).toBeDisabled();
    expect(screen.getByTestId("send-button")).toBeDisabled();
  });
});
