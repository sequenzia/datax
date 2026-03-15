import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ChatInput } from "../chat-input";
import { MessageBubble } from "../message-bubble";
import { StreamingText } from "../streaming-text";

// Mock streamdown to render children as plain text in tests
vi.mock("streamdown", () => ({
  Streamdown: ({
    children,
    mode,
  }: {
    children?: string;
    mode?: string;
  }) => (
    <div data-testid="streamdown" data-mode={mode}>
      {children}
    </div>
  ),
}));

describe("ChatInput", () => {
  const mockOnSend = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders textarea and send button", () => {
    render(
      <ChatInput onSend={mockOnSend} />,
    );
    expect(screen.getByTestId("chat-input")).toBeInTheDocument();
    expect(screen.getByTestId("send-button")).toBeInTheDocument();
  });

  it("prevents empty submission", async () => {
    render(
      <ChatInput onSend={mockOnSend} />,
    );
    const sendButton = screen.getByTestId("send-button");
    await userEvent.click(sendButton);
    expect(mockOnSend).not.toHaveBeenCalled();
  });

  it("prevents whitespace-only submission", async () => {
    render(
      <ChatInput onSend={mockOnSend} />,
    );
    const input = screen.getByTestId("chat-input");
    await userEvent.type(input, "   ");
    await userEvent.click(screen.getByTestId("send-button"));
    expect(mockOnSend).not.toHaveBeenCalled();
  });

  it("sends message on form submit with content", async () => {
    render(
      <ChatInput onSend={mockOnSend} />,
    );
    const input = screen.getByTestId("chat-input");
    await userEvent.type(input, "Hello AI");
    await userEvent.click(screen.getByTestId("send-button"));
    expect(mockOnSend).toHaveBeenCalledWith("Hello AI");
  });

  it("clears input after sending", async () => {
    render(
      <ChatInput onSend={mockOnSend} />,
    );
    const input = screen.getByTestId("chat-input") as HTMLTextAreaElement;
    await userEvent.type(input, "Hello AI");
    await userEvent.click(screen.getByTestId("send-button"));
    expect(input.value).toBe("");
  });

  it("sends on Ctrl+Enter", async () => {
    render(
      <ChatInput onSend={mockOnSend} />,
    );
    const input = screen.getByTestId("chat-input");
    await userEvent.type(input, "Hello");
    await userEvent.keyboard("{Control>}{Enter}{/Control}");
    expect(mockOnSend).toHaveBeenCalledWith("Hello");
  });

  it("sends on Meta+Enter", async () => {
    render(
      <ChatInput onSend={mockOnSend} />,
    );
    const input = screen.getByTestId("chat-input");
    await userEvent.type(input, "Hello");
    await userEvent.keyboard("{Meta>}{Enter}{/Meta}");
    expect(mockOnSend).toHaveBeenCalledWith("Hello");
  });

  it("disables input when disabled prop is true", () => {
    render(
      <ChatInput onSend={mockOnSend} disabled />,
    );
    expect(screen.getByTestId("chat-input")).toBeDisabled();
  });
});

describe("MessageBubble", () => {
  it("renders user message with user styling", () => {
    render(<MessageBubble role="user" content="Hello" />);
    const bubble = screen.getByTestId("message-bubble-user");
    expect(bubble).toBeInTheDocument();
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  it("renders assistant message with markdown rendering", () => {
    render(<MessageBubble role="assistant" content="Hi there" />);
    const bubble = screen.getByTestId("message-bubble-assistant");
    expect(bubble).toBeInTheDocument();
    expect(screen.getByTestId("markdown-content")).toBeInTheDocument();
    expect(screen.getByText("Hi there")).toBeInTheDocument();
  });

  it("renders user messages as plain text", () => {
    render(<MessageBubble role="user" content="Hello" />);
    expect(screen.queryByTestId("markdown-content")).not.toBeInTheDocument();
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  it("renders assistant messages in static mode", () => {
    render(<MessageBubble role="assistant" content="Hi there" />);
    const streamdown = screen.getByTestId("streamdown");
    expect(streamdown).toHaveAttribute("data-mode", "static");
  });

  it("wraps long messages", () => {
    const longMessage = "A".repeat(500);
    render(<MessageBubble role="user" content={longMessage} />);
    expect(screen.getByText(longMessage)).toBeInTheDocument();
  });

  it("renders children instead of content when provided", () => {
    render(
      <MessageBubble role="assistant" content="">
        <span data-testid="custom-child">Custom content</span>
      </MessageBubble>,
    );
    expect(screen.getByTestId("custom-child")).toBeInTheDocument();
  });
});

describe("StreamingText", () => {
  it("renders content text", () => {
    render(<StreamingText content="Hello world" isStreaming={false} />);
    expect(screen.getByText("Hello world")).toBeInTheDocument();
  });

  it("renders content in streaming mode", () => {
    render(<StreamingText content="Hello" isStreaming={true} />);
    const streamdown = screen.getByTestId("streamdown");
    expect(streamdown).toHaveAttribute("data-mode", "streaming");
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  it("renders content in static mode when not streaming", () => {
    render(<StreamingText content="Hello" isStreaming={false} />);
    const streamdown = screen.getByTestId("streamdown");
    expect(streamdown).toHaveAttribute("data-mode", "static");
  });

  it("shows fallback cursor when streaming with empty content", () => {
    render(<StreamingText content="" isStreaming={true} />);
    expect(screen.getByTestId("streaming-text")).toBeInTheDocument();
    expect(screen.getByTestId("streaming-cursor")).toBeInTheDocument();
  });

  it("hides fallback cursor when streaming with content", () => {
    render(<StreamingText content="Hello" isStreaming={true} />);
    expect(screen.queryByTestId("streaming-cursor")).not.toBeInTheDocument();
  });

  it("hides fallback cursor when not streaming", () => {
    render(<StreamingText content="" isStreaming={false} />);
    expect(screen.queryByTestId("streaming-cursor")).not.toBeInTheDocument();
  });

  it("renders streaming-text container", () => {
    render(<StreamingText content="Hello" isStreaming={true} />);
    expect(screen.getByTestId("streaming-text")).toBeInTheDocument();
  });
});
