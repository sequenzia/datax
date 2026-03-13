import { useCallback, useRef, type KeyboardEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Upload,
  Database,
  MessageSquare,
  FileSpreadsheet,
  Send,
  ArrowRight,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  useDatasets,
  useConnections,
  useConversations,
} from "@/hooks/use-dashboard-data";
import { useChatStore } from "@/stores/chat-store";
import type { Conversation } from "@/types/api";

const SUGGESTIONS = [
  "Show top 10 customers by revenue",
  "Revenue trend this quarter",
  "Compare product categories",
  "Find any duplicate records",
];

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function HeroChatInput() {
  const navigate = useNavigate();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = useCallback(async () => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    const value = textarea.value.trim();
    if (!value) return;

    const newId = await useChatStore.getState().newConversation();
    if (newId) {
      navigate(`/chat/${newId}`);
      setTimeout(() => {
        void useChatStore.getState().sendMessage(value);
      }, 0);
    }
  }, [navigate]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        void handleSubmit();
      }
    },
    [handleSubmit],
  );

  const handleSuggestionClick = useCallback(
    async (question: string) => {
      const newId = await useChatStore.getState().newConversation();
      if (newId) {
        navigate(`/chat/${newId}`);
        setTimeout(() => {
          void useChatStore.getState().sendMessage(question);
        }, 0);
      }
    },
    [navigate],
  );

  return (
    <section className="mx-auto max-w-2xl space-y-4 text-center">
      <h1 className="text-3xl font-bold tracking-tight">
        {getGreeting()}. What would you like to analyze?
      </h1>

      {/* Hero input */}
      <div className="relative">
        <textarea
          ref={textareaRef}
          placeholder="Ask a question about your data..."
          className="min-h-[52px] w-full resize-none rounded-xl border bg-background px-4 py-3 pr-12 text-sm shadow-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
          rows={1}
          onKeyDown={handleKeyDown}
          onInput={() => {
            const ta = textareaRef.current;
            if (ta) {
              ta.style.height = "auto";
              ta.style.height = `${Math.min(ta.scrollHeight, 120)}px`;
            }
          }}
          data-testid="hero-chat-input"
        />
        <Button
          size="icon"
          className="absolute bottom-2 right-2"
          onClick={() => void handleSubmit()}
          aria-label="Send"
          data-testid="hero-send-button"
        >
          <Send className="size-4" />
        </Button>
      </div>

      {/* Suggestions */}
      <div className="flex flex-wrap justify-center gap-2">
        {SUGGESTIONS.map((q) => (
          <button
            key={q}
            onClick={() => void handleSuggestionClick(q)}
            className="rounded-full border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
            data-testid="suggestion-chip"
          >
            {q}
          </button>
        ))}
      </div>
    </section>
  );
}

function ConversationRow({ conversation }: { conversation: Conversation }) {
  return (
    <Link
      to={`/chat/${conversation.id}`}
      className="flex items-center justify-between rounded-lg border px-4 py-3 transition-colors hover:bg-accent"
    >
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <MessageSquare className="size-4 shrink-0 text-muted-foreground" />
        <p className="truncate text-sm font-medium">{conversation.title}</p>
      </div>
      <ArrowRight className="size-4 shrink-0 text-muted-foreground" />
    </Link>
  );
}

function RecentConversations() {
  const { data: conversations, isLoading, isError } = useConversations();

  if (isLoading || isError || !conversations || conversations.length === 0) return null;

  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
          Recent Conversations
        </h2>
        <Link to="/chat" className="text-xs text-primary hover:underline">
          View all
        </Link>
      </div>
      <div className="space-y-2">
        {conversations.slice(0, 5).map((conv) => (
          <ConversationRow key={conv.id} conversation={conv} />
        ))}
      </div>
    </section>
  );
}

function DataSourcesSummary() {
  const { data: datasets } = useDatasets();
  const { data: connections } = useConnections();

  const datasetCount = datasets?.length ?? 0;
  const connectionCount = connections?.length ?? 0;

  if (datasetCount === 0 && connectionCount === 0) {
    return (
      <section>
        <h2 className="mb-3 text-sm font-semibold text-muted-foreground uppercase tracking-wider">
          Get Started
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <Link to="/data" className="group">
            <Card className="transition-all hover:shadow-md">
              <CardContent className="flex items-center gap-3 py-4">
                <div className="rounded-lg bg-primary/10 p-2">
                  <Upload className="size-5 text-primary" />
                </div>
                <div>
                  <p className="text-sm font-medium">Upload a Dataset</p>
                  <p className="text-xs text-muted-foreground">CSV, Excel, Parquet, JSON</p>
                </div>
              </CardContent>
            </Card>
          </Link>
          <Link to="/data" className="group">
            <Card className="transition-all hover:shadow-md">
              <CardContent className="flex items-center gap-3 py-4">
                <div className="rounded-lg bg-primary/10 p-2">
                  <Database className="size-5 text-primary" />
                </div>
                <div>
                  <p className="text-sm font-medium">Connect a Database</p>
                  <p className="text-xs text-muted-foreground">PostgreSQL, MySQL</p>
                </div>
              </CardContent>
            </Card>
          </Link>
        </div>
      </section>
    );
  }

  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
          Data Sources
        </h2>
        <Link to="/data" className="text-xs text-primary hover:underline">
          Manage
        </Link>
      </div>
      <div className="flex gap-4">
        <div className="flex items-center gap-2 rounded-lg border px-4 py-3">
          <FileSpreadsheet className="size-4 text-blue-500" />
          <span className="text-sm font-medium">{datasetCount} dataset{datasetCount !== 1 ? "s" : ""}</span>
        </div>
        <div className="flex items-center gap-2 rounded-lg border px-4 py-3">
          <Database className="size-4 text-green-500" />
          <span className="text-sm font-medium">{connectionCount} connection{connectionCount !== 1 ? "s" : ""}</span>
        </div>
      </div>
    </section>
  );
}

export function DashboardPage() {
  return (
    <div className="flex h-full flex-col overflow-y-auto">
      {/* Hero section */}
      <div className="flex flex-1 items-center justify-center px-6 py-12">
        <HeroChatInput />
      </div>

      {/* Bottom sections */}
      <div className="mx-auto w-full max-w-3xl space-y-8 px-6 pb-8">
        <RecentConversations />
        <DataSourcesSummary />
      </div>
    </div>
  );
}
