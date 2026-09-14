import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { CoachChatProvider, useCoachChat } from "@/components/chat/coach-chat-provider";
import { CoachChatWidget } from "@/components/chat/coach-chat-widget";
import { chatApi } from "@/lib/api";

function Actions() {
  const chat = useCoachChat();
  return <button onClick={() => { chat.sendMessage("ignored"); chat.retryMessage("ignored"); chat.endChat(); }}>Direct actions</button>;
}

it("shows history failure, blocks actions, and restores conversation on retry", async () => {
  const history = vi.spyOn(chatApi, "getHistory").mockRejectedValueOnce(new Error("Unavailable")).mockResolvedValue({
    messages: [{ role: "assistant", content: "Your saved conversation" }],
    current_goal: null, preferences: [], topics_of_interest: [], progress: null,
  });
  const send = vi.spyOn(chatApi, "sendMessage").mockResolvedValue({ reply: "Welcome back" } as Awaited<ReturnType<typeof chatApi.sendMessage>>);
  const end = vi.spyOn(chatApi, "endSession");
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><CoachChatProvider><Actions /><CoachChatWidget /></CoachChatProvider></QueryClientProvider>);
  await userEvent.click(screen.getByRole("button", { name: "Open assistant chat" }));
  await screen.findByRole("alert");
  expect(screen.queryByText(/Hi! I’m your Berlin Braves/)).toBeNull();
  await userEvent.type(screen.getByRole("textbox", { name: "Message" }), "Hello");
  expect((screen.getByRole("button", { name: "Send message" }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole("button", { name: "End chat" }) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.click(screen.getByRole("button", { name: "Direct actions" }));
  expect(send).not.toHaveBeenCalled();
  expect(end).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  await screen.findByText("Your saved conversation");
  await waitFor(() => expect((screen.getByRole("button", { name: "Send message" }) as HTMLButtonElement).disabled).toBe(false));
  expect(history).toHaveBeenCalledTimes(2);
  expect(screen.queryByRole("alert")).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  await screen.findByText("Welcome back");
  expect(send).toHaveBeenCalledWith("Hello");
  expect(screen.getByText("Your saved conversation")).toBeTruthy();
});


it("shows the welcome message only after a successful empty history load", async () => {
  vi.spyOn(chatApi, "getHistory").mockResolvedValue({
    messages: [], current_goal: null, preferences: [], topics_of_interest: [], progress: null,
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><CoachChatProvider><CoachChatWidget /></CoachChatProvider></QueryClientProvider>);
  await userEvent.click(screen.getByRole("button", { name: "Open assistant chat" }));
  await screen.findByText(/Hi! I’m your Berlin Braves/);
  expect(screen.queryByRole("alert")).toBeNull();
});
