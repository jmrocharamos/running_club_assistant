import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { CoachChatProvider } from "@/components/chat/coach-chat-provider";
import { CoachChatWidget } from "@/components/chat/coach-chat-widget";
import { chatApi } from "@/lib/api";
import type { ChatHistoryResponse, ChatMemory, CompletedChatSession } from "@/types";

const session: CompletedChatSession = {
  id: "session-1", started_at: "2026-10-14T09:00:00Z", ended_at: "2026-10-14T09:10:00Z",
  recap: "We discussed comfortable training routes.", open_questions: [],
  next_steps: [{ id: "step-1", text: "Book a gym session", runner_quote: "I will book a gym session", completed: false }],
  memory_changes: [{ field: "preferences", before: [], after: ["Trails"], runner_quote: "I like trails" }],
};

function setup(active = false) {
  let history: ChatHistoryResponse = {
    current_goal: "Finish a 5K", preferences: ["Trails"], topics_of_interest: [], progress: null,
    messages: active ? [{ role: "user", content: "I like trails" }, { role: "assistant", content: "Try the park" }] : [],
    active_session_id: active ? "session-1" : null, revision: 2, session_history: active ? [] : [structuredClone(session)],
  };
  vi.spyOn(chatApi, "getHistory").mockImplementation(async () => history);
  function saved(chat: ChatMemory) {
    const { current_conversation, ...memory } = chat;
    history = { ...memory, messages: current_conversation };
    return { chat };
  }
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><CoachChatProvider><CoachChatWidget /></CoachChatProvider></QueryClientProvider>);
  return { getHistory: () => history, saved };
}

async function openMemory() {
  await userEvent.click(screen.getByRole("button", { name: "Open assistant chat" }));
  const button = screen.getByRole("button", { name: "History & memory" });
  await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
  await userEvent.click(button);
  return screen.findByRole("dialog", { name: "History & memory" });
}

it("edits and forgets memory without removing completed sessions", async () => {
  const state = setup();
  const save = vi.spyOn(chatApi, "updateMemory").mockImplementation(async (memory, revision) => state.saved({
    ...memory, current_conversation: [], session_history: state.getHistory().session_history, revision: revision + 1,
  }));
  const dialog = await openMemory();
  await userEvent.clear(within(dialog).getByLabelText("Current goal"));
  await userEvent.click(within(dialog).getByRole("button", { name: "Save memory" }));
  await waitFor(() => expect(save).toHaveBeenCalledWith({ current_goal: null, preferences: ["Trails"], topics_of_interest: [], progress: null }, 2));
  await waitFor(() => expect((within(dialog).getByLabelText("Current goal") as HTMLTextAreaElement).value).toBe(""));
  expect(state.getHistory().session_history).toHaveLength(1);
});

it("tracks an action and deletes its recap without changing runner memory", async () => {
  const state = setup();
  const toggle = vi.spyOn(chatApi, "updateNextStep").mockImplementation(async (_id, _step, completed, revision) => {
    const history = state.getHistory();
    const sessions = structuredClone(history.session_history!);
    sessions[0].next_steps[0].completed = completed;
    return state.saved({ ...history, current_conversation: [], session_history: sessions, revision: revision + 1 });
  });
  const remove = vi.spyOn(chatApi, "deleteSession").mockImplementation(async (_id, revision) => state.saved({
    ...state.getHistory(), current_conversation: [], session_history: [], revision: revision + 1,
  }));
  const dialog = await openMemory();
  await userEvent.click(dialog.querySelector("summary")!);
  await userEvent.click(within(dialog).getByRole("checkbox", { name: "Book a gym session" }));
  await waitFor(() => expect(toggle).toHaveBeenCalledWith("session-1", "step-1", true, 2));
  await waitFor(() => expect((within(dialog).getByRole("checkbox") as HTMLInputElement).checked).toBe(true));
  await userEvent.click(within(dialog).getByRole("button", { name: "Delete summary" }));
  expect(remove).not.toHaveBeenCalled();
  await userEvent.click(within(dialog).getByRole("button", { name: "Confirm delete" }));
  await within(dialog).findByText("No completed sessions yet.");
  expect(remove).toHaveBeenCalledWith("session-1", 3);
  expect(state.getHistory().current_goal).toBe("Finish a 5K");
});

it("keeps memory editing disabled during an active chat", async () => {
  setup(true);
  const dialog = await openMemory();
  expect((within(dialog).getByLabelText("Current goal").closest("fieldset") as HTMLFieldSetElement).disabled).toBe(true);
  expect(within(dialog).getByText("End your current chat before editing memory.")).toBeTruthy();
});

it("shows the session recap, agreed actions and memory changes after ending", async () => {
  const state = setup(true);
  const end = vi.spyOn(chatApi, "endSession").mockImplementation(async () => ({
    summary: state.saved({ ...state.getHistory(), current_conversation: [], active_session_id: null, revision: 3, session_history: [session] }), session,
  }));
  await userEvent.click(screen.getByRole("button", { name: "Open assistant chat" }));
  const button = screen.getByRole("button", { name: "End chat" });
  await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
  await userEvent.click(button);
  const confirmation = await screen.findByRole("dialog", { name: "End this chat?" });
  await userEvent.click(within(confirmation).getByRole("button", { name: "End chat" }));
  const recap = await screen.findByRole("dialog", { name: "Session summary" });
  expect(within(recap).getByText(session.recap)).toBeTruthy();
  expect(within(recap).getByText("Book a gym session")).toBeTruthy();
  expect(within(recap).getByText("Memory changes")).toBeTruthy();
  expect(end).toHaveBeenCalledWith("session-1");
});
