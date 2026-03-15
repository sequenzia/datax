/** TanStack Query hooks for bookmark CRUD operations. */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchBookmarks,
  createBookmark,
  deleteBookmark,
} from "@/lib/api";
import type { CreateBookmarkRequest } from "@/types/api";

export function useBookmarkList() {
  return useQuery({
    queryKey: ["bookmarks"],
    queryFn: fetchBookmarks,
    retry: 2,
  });
}

export function useCreateBookmark() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateBookmarkRequest) => createBookmark(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["bookmarks"] });
    },
  });
}

export function useDeleteBookmark() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteBookmark(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["bookmarks"] });
    },
  });
}
