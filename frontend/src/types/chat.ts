export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  /** Client-only: set when an optimistically-sent message failed to deliver. */
  status?: "failed";
}

export interface ChatbotRequest {
  message: string;
}

export interface ChatbotResponse {
  reply: string;
  active_session_id?: string | null;
  revision?: number;
}

export interface CompletedChatSession {
  id: string;
  started_at: string | null;
  ended_at: string;
  recap: string;
  next_steps: { id: string; text: string; runner_quote: string; completed: boolean }[];
  open_questions: string[];
  memory_changes: { field: string; before: string | string[] | null; after: string | string[] | null; runner_quote?: string | null }[];
}

export interface RunnerMemory {
  current_goal: string | null;
  preferences: string[];
  topics_of_interest: string[];
  progress: string | null;
}

export interface ChatMemory {
  current_goal: string | null;
  preferences: string[];
  topics_of_interest: string[];
  progress: string | null;
  current_conversation: ChatMessage[];
  active_session_id?: string | null;
  session_history?: CompletedChatSession[];
  revision?: number;
}

export interface CoachMemorySummary {
  chat: ChatMemory;
}

export interface ChatbotEndResponse {
  summary: CoachMemorySummary;
  session?: CompletedChatSession | null;
}

export interface ChatHistoryResponse {
  messages: ChatMessage[];
  current_goal: string | null;
  preferences: string[];
  topics_of_interest: string[];
  progress: string | null;
  active_session_id?: string | null;
  session_history?: CompletedChatSession[];
  revision?: number;
}
