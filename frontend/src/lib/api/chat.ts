import { apiClient } from "./client";
import type { ChatbotEndResponse, ChatbotResponse, ChatHistoryResponse, CoachMemorySummary, RunnerMemory } from "@/types";

export const chatApi = {
  sendMessage: (message: string) =>
    apiClient.post<ChatbotResponse>("/chatbot/", { message }),

  endSession: (sessionId?: string | null) => apiClient.post<ChatbotEndResponse>("/chatbot/end", { session_id: sessionId ?? null }),

  getHistory: () => apiClient.get<ChatHistoryResponse>("/chatbot/history"),
  updateMemory: (memory: RunnerMemory, revision: number) =>
    apiClient.patch<CoachMemorySummary>("/chatbot/memory", { ...memory, revision }),
  deleteSession: (sessionId: string, revision: number) =>
    apiClient.delete<CoachMemorySummary>(`/chatbot/sessions/${encodeURIComponent(sessionId)}?revision=${revision}`),
  updateNextStep: (sessionId: string, stepId: string, completed: boolean, revision: number) =>
    apiClient.patch<CoachMemorySummary>(`/chatbot/sessions/${encodeURIComponent(sessionId)}/steps/${encodeURIComponent(stepId)}`, { completed, revision }),
};
