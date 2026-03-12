/** TanStack Query hooks for conversation browsing with infinite scroll. */

import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { fetchConversationsPaginated, deleteConversation } from "@/lib/api";
import type { ConversationListResponse } from "@/types/api";

const PAGE_SIZE = 20;

export function useConversationList(search: string) {
  return useInfiniteQuery<ConversationListResponse>({
    queryKey: ["conversations", "list", search],
    queryFn: ({ pageParam }) =>
      fetchConversationsPaginated({
        cursor: pageParam as string | undefined,
        limit: PAGE_SIZE,
        search: search || undefined,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    retry: 3,
    retryDelay: (attemptIndex: number) =>
      Math.min(1000 * 2 ** attemptIndex, 30000),
  });
}

export function useDeleteConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteConversation(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });
}
