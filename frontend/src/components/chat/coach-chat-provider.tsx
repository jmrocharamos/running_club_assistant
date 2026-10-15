"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  useRef,
  type ReactNode,
} from "react";
import { toast } from "sonner";

import { chatApi } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { ApiError } from "@/types/api";
import type { ChatHistoryResponse, ChatMemory, ChatMessage, CoachMemorySummary } from "@/types";

interface CoachChatContextValue {
  messages: ChatMessage[];
  isHistoryLoading: boolean;
  isHistoryError: boolean;
  isHistoryFetching: boolean;
  retryHistory: () => void;
  isOpen: boolean;
  hasUnread: boolean;
  openChat: () => void;
  closeChat: () => void;
  toggleChat: () => void;
  sendMessage: (message: string) => void;
  retryMessage: (message: string) => void;
  isSending: boolean;
  endChat: () => void;
  isEndingChat: boolean;
  endedChatSummary: ChatMemory | null;
  dismissEndedChatSummary: () => void;
  history: ChatHistoryResponse | undefined;
  applySavedMemory: (summary: CoachMemorySummary) => void;
}

const CoachChatContext = createContext<CoachChatContextValue | null>(null);

function emptyHistory(): ChatHistoryResponse {
  return {
    messages: [],
    current_goal: null,
    preferences: [],
    topics_of_interest: [],
    progress: null,
  };
}

const EMPTY_MESSAGES: ChatMessage[] = [];

export function CoachChatProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [isOpen, setIsOpen] = useState(false);
  const [hasUnread, setHasUnread] = useState(false);
  const [endedChatSummary, setEndedChatSummary] = useState<ChatMemory | null>(null);
  const actionInFlight = useRef(false);

  const {
    data: history,
    isLoading: isHistoryLoading,
    isError: isHistoryError,
    isFetching: isHistoryFetching,
    refetch: refetchHistory,
  } = useQuery({
    queryKey: queryKeys.chatHistory,
    queryFn: () => chatApi.getHistory(),
    staleTime: Infinity,
    refetchOnMount: false,
  });

  const retryHistory = useCallback(() => {
    void refetchHistory();
  }, [refetchHistory]);
  const isHistoryUnavailable = isHistoryLoading || isHistoryError || isHistoryFetching;
  const messages = history?.messages ?? EMPTY_MESSAGES;

  const openChat = useCallback(() => {
    setIsOpen(true);
    setHasUnread(false);
  }, []);

  const closeChat = useCallback(() => setIsOpen(false), []);

  const toggleChat = useCallback(() => {
    setIsOpen((current) => {
      const next = !current;
      if (next) setHasUnread(false);
      return next;
    });
  }, []);

  const sendMutation = useMutation({
    mutationFn: (message: string) => chatApi.sendMessage(message),
  });

  const applySavedMemory = useCallback((summary: CoachMemorySummary) => {
    const { current_conversation, ...memory } = summary.chat;
    queryClient.setQueryData<ChatHistoryResponse>(queryKeys.chatHistory, {
      ...memory, messages: current_conversation,
    });
    void queryClient.invalidateQueries({ queryKey: queryKeys.chatHistory });
  }, [queryClient]);

  const dispatchSend = useCallback(
    (message: string) => {
      if (isHistoryUnavailable || actionInFlight.current) return;
      actionInFlight.current = true;
      const optimisticMessage: ChatMessage = { role: "user", content: message };

      queryClient.setQueryData<ChatHistoryResponse>(queryKeys.chatHistory, (current) => ({
        ...(current ?? emptyHistory()),
        messages: [...(current?.messages ?? []), optimisticMessage],
      }));

      sendMutation.mutate(message, {
        onSettled: () => { actionInFlight.current = false; },
        onSuccess: (response) => {
          queryClient.setQueryData<ChatHistoryResponse>(queryKeys.chatHistory, (current) => ({
            ...(current ?? emptyHistory()),
            active_session_id: response.active_session_id,
            revision: response.revision,
            messages: [
              ...(current?.messages ?? []),
              { role: "assistant", content: response.reply },
            ],
          }));

          if (!isOpen) setHasUnread(true);
        },
        onError: () => {
          queryClient.setQueryData<ChatHistoryResponse>(queryKeys.chatHistory, (current) => ({
            ...(current ?? emptyHistory()),
            messages: (current?.messages ?? []).map((entry) =>
              entry === optimisticMessage ? { ...entry, status: "failed" as const } : entry,
            ),
          }));
        },
      });
    },
    [isHistoryUnavailable, isOpen, queryClient, sendMutation],
  );

  const sendMessage = useCallback(
    (message: string) => {
      dispatchSend(message);
    },
    [dispatchSend],
  );

  const retryMessage = useCallback(
    (message: string) => {
      if (isHistoryUnavailable || actionInFlight.current) return;
      queryClient.setQueryData<ChatHistoryResponse>(queryKeys.chatHistory, (current) => {
        if (!current) return current;

        const failedIndex = current.messages.findIndex(
          (entry) => entry.status === "failed" && entry.content === message,
        );
        if (failedIndex === -1) return current;

        return {
          ...current,
          messages: current.messages.filter((_, index) => index !== failedIndex),
        };
      });

      dispatchSend(message);
    },
    [dispatchSend, isHistoryUnavailable, queryClient],
  );

  const endChatMutation = useMutation({
    onSettled: () => { actionInFlight.current = false; },
    mutationFn: () => chatApi.endSession(history?.active_session_id),
    onSuccess: (response) => {
      applySavedMemory(response.summary);
      setEndedChatSummary(response.session ? { ...response.summary.chat, session_history: [response.session] } : null);
    },
    onError: (error) => {
      toast.error(
        error instanceof ApiError
          ? error.message
          : "Couldn't end the chat. Please try again.",
      );
    },
  });

  const endChat = useCallback(() => {
    if (actionInFlight.current || endChatMutation.isPending || sendMutation.isPending || isHistoryUnavailable) return;
    actionInFlight.current = true;
    endChatMutation.mutate();
  }, [endChatMutation, sendMutation.isPending, isHistoryUnavailable]);

  const value = useMemo<CoachChatContextValue>(
    () => ({
      messages,
      isHistoryLoading,
      isHistoryError,
      isHistoryFetching,
      retryHistory,
      isOpen,
      hasUnread,
      openChat,
      closeChat,
      toggleChat,
      sendMessage,
      retryMessage,
      isSending: sendMutation.isPending,
      endChat,
      isEndingChat: endChatMutation.isPending,
      endedChatSummary,
      dismissEndedChatSummary: () => setEndedChatSummary(null),
      history,
      applySavedMemory,
    }),
    [
      messages,
      isHistoryLoading,
      isHistoryError,
      isHistoryFetching,
      retryHistory,
      isOpen,
      hasUnread,
      openChat,
      closeChat,
      toggleChat,
      sendMessage,
      retryMessage,
      sendMutation.isPending,
      endChat,
      endChatMutation.isPending,
      endedChatSummary,
      history,
      applySavedMemory,
    ],
  );

  return <CoachChatContext.Provider value={value}>{children}</CoachChatContext.Provider>;
}

export function useCoachChat(): CoachChatContextValue {
  const context = useContext(CoachChatContext);

  if (!context) {
    throw new Error("useCoachChat must be used within a CoachChatProvider");
  }

  return context;
}
