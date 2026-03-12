import { Link } from "react-router-dom";
import {
  Upload,
  Database,
  MessageSquare,
  FileSpreadsheet,
  AlertCircle,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  useDatasets,
  useConnections,
  useConversations,
} from "@/hooks/use-dashboard-data";
import type { Dataset, Connection, Conversation } from "@/types/api";

const MAX_VISIBLE_ITEMS = 6;

function statusColor(status: string): string {
  switch (status) {
    case "ready":
    case "connected":
      return "bg-green-500";
    case "processing":
    case "uploading":
      return "bg-yellow-500";
    case "error":
    case "disconnected":
      return "bg-red-500";
    default:
      return "bg-gray-400";
  }
}

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatRowCount(count: number | null): string {
  if (count === null) return "--";
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M rows`;
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}K rows`;
  return `${count} rows`;
}

function SectionError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-destructive/50 bg-destructive/10 p-4">
      <AlertCircle className="size-5 shrink-0 text-destructive" />
      <p className="text-sm text-destructive">{message}</p>
      <Button variant="outline" size="sm" onClick={onRetry} className="ml-auto">
        Retry
      </Button>
    </div>
  );
}

function SectionSkeleton() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 3 }).map((_, i) => (
        <div
          key={i}
          className="h-32 animate-pulse rounded-xl border bg-muted/50"
        />
      ))}
    </div>
  );
}

function DatasetCard({ dataset }: { dataset: Dataset }) {
  return (
    <Link to={`/datasets/${dataset.id}`}>
      <Card className="transition-shadow hover:shadow-md">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm">{dataset.name}</CardTitle>
            <span
              className={`inline-block size-2.5 rounded-full ${statusColor(dataset.status)}`}
              title={dataset.status}
              data-testid="dataset-status"
            />
          </div>
          <CardDescription>{dataset.file_format.toUpperCase()}</CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>{formatRowCount(dataset.row_count)}</span>
            <span>{formatDate(dataset.created_at)}</span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function ConnectionCard({ connection }: { connection: Connection }) {
  return (
    <Link to={`/connections/${connection.id}`}>
      <Card className="transition-shadow hover:shadow-md">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm">{connection.name}</CardTitle>
            <span
              className={`inline-block size-2.5 rounded-full ${statusColor(connection.status)}`}
              title={connection.status}
              data-testid="connection-status"
            />
          </div>
          <CardDescription>{connection.db_type}</CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          <p className="truncate text-xs text-muted-foreground">
            {connection.host}
          </p>
        </CardContent>
      </Card>
    </Link>
  );
}

function ConversationRow({ conversation }: { conversation: Conversation }) {
  return (
    <Link
      to={`/chat/${conversation.id}`}
      className="flex items-center justify-between rounded-lg border px-4 py-3 transition-colors hover:bg-accent"
    >
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{conversation.title}</p>
        <p className="text-xs text-muted-foreground">
          {formatDate(conversation.updated_at)}
        </p>
      </div>
      <span className="ml-4 shrink-0 text-xs text-muted-foreground">
        {conversation.message_count}{" "}
        {conversation.message_count === 1 ? "message" : "messages"}
      </span>
    </Link>
  );
}

function DatasetsSection() {
  const { data: datasets, isLoading, isError, refetch } = useDatasets();

  return (
    <section aria-labelledby="datasets-heading">
      <div className="mb-4 flex items-center justify-between">
        <h2 id="datasets-heading" className="text-lg font-semibold">
          Datasets
        </h2>
        {datasets && datasets.length > MAX_VISIBLE_ITEMS && (
          <Link
            to="/datasets"
            className="text-sm text-primary hover:underline"
          >
            View all
          </Link>
        )}
      </div>

      {isLoading && <SectionSkeleton />}

      {isError && (
        <SectionError
          message="Failed to load datasets."
          onRetry={() => void refetch()}
        />
      )}

      {datasets && datasets.length === 0 && (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center gap-3 py-8">
            <FileSpreadsheet className="size-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              No datasets uploaded yet.
            </p>
            <Button variant="outline" size="sm" asChild>
              <Link to="/datasets/upload">Upload Data</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {datasets && datasets.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {datasets.slice(0, MAX_VISIBLE_ITEMS).map((dataset) => (
            <DatasetCard key={dataset.id} dataset={dataset} />
          ))}
        </div>
      )}
    </section>
  );
}

function ConnectionsSection() {
  const {
    data: connections,
    isLoading,
    isError,
    refetch,
  } = useConnections();

  return (
    <section aria-labelledby="connections-heading">
      <div className="mb-4 flex items-center justify-between">
        <h2 id="connections-heading" className="text-lg font-semibold">
          Connections
        </h2>
        {connections && connections.length > MAX_VISIBLE_ITEMS && (
          <Link
            to="/connections"
            className="text-sm text-primary hover:underline"
          >
            View all
          </Link>
        )}
      </div>

      {isLoading && <SectionSkeleton />}

      {isError && (
        <SectionError
          message="Failed to load connections."
          onRetry={() => void refetch()}
        />
      )}

      {connections && connections.length === 0 && (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center gap-3 py-8">
            <Database className="size-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              No database connections configured.
            </p>
            <Button variant="outline" size="sm" asChild>
              <Link to="/connections/new">Add Connection</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {connections && connections.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {connections.slice(0, MAX_VISIBLE_ITEMS).map((connection) => (
            <ConnectionCard key={connection.id} connection={connection} />
          ))}
        </div>
      )}
    </section>
  );
}

function ConversationsSection() {
  const {
    data: conversations,
    isLoading,
    isError,
    refetch,
  } = useConversations();

  return (
    <section aria-labelledby="conversations-heading">
      <div className="mb-4 flex items-center justify-between">
        <h2 id="conversations-heading" className="text-lg font-semibold">
          Recent Conversations
        </h2>
        {conversations && conversations.length > MAX_VISIBLE_ITEMS && (
          <Link to="/chat" className="text-sm text-primary hover:underline">
            View all
          </Link>
        )}
      </div>

      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="h-16 animate-pulse rounded-lg border bg-muted/50"
            />
          ))}
        </div>
      )}

      {isError && (
        <SectionError
          message="Failed to load conversations."
          onRetry={() => void refetch()}
        />
      )}

      {conversations && conversations.length === 0 && (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center gap-3 py-8">
            <MessageSquare className="size-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              No conversations yet.
            </p>
            <Button variant="outline" size="sm" asChild>
              <Link to="/chat">Start Conversation</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {conversations && conversations.length > 0 && (
        <div className="space-y-3">
          {conversations.slice(0, MAX_VISIBLE_ITEMS).map((conversation) => (
            <ConversationRow
              key={conversation.id}
              conversation={conversation}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function QuickActions() {
  return (
    <section aria-labelledby="quick-actions-heading">
      <h2 id="quick-actions-heading" className="sr-only">
        Quick Actions
      </h2>
      <div className="flex flex-wrap gap-3">
        <Button asChild>
          <Link to="/datasets/upload">
            <Upload className="size-4" />
            Upload Data
          </Link>
        </Button>
        <Button variant="outline" asChild>
          <Link to="/connections/new">
            <Database className="size-4" />
            Add Connection
          </Link>
        </Button>
        <Button variant="outline" asChild>
          <Link to="/chat">
            <MessageSquare className="size-4" />
            Start Conversation
          </Link>
        </Button>
      </div>
    </section>
  );
}

export function DashboardPage() {
  return (
    <div className="space-y-8 p-6">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="mt-1 text-muted-foreground">
          Overview of your datasets, connections, and conversations.
        </p>
      </div>

      <QuickActions />
      <DatasetsSection />
      <ConnectionsSection />
      <ConversationsSection />
    </div>
  );
}
