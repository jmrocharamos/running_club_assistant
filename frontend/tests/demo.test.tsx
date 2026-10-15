import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "@/proxy";
import DemoPage from "@/app/demo/page";
import { DemoBanner } from "@/components/demo-banner";
import { demoApi } from "@/lib/api/demo";
import type { User } from "@/types";

const { navigation, session } = vi.hoisted(() => ({
  navigation: { push: vi.fn(), replace: vi.fn() },
  session: { user: undefined as User | undefined },
}));
vi.mock("next/navigation", () => ({ useRouter: () => navigation }));
vi.mock("@/components/providers/session-provider", () => ({ useSession: () => session }));

beforeEach(() => { navigation.push.mockClear(); navigation.replace.mockClear(); session.user = undefined; });
afterEach(() => vi.useRealTimers());

function mount(component: React.ReactNode) {
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={cache}>{component}</QueryClientProvider>);
  return cache;
}

it("lets anonymous visitors open demo pages without redirecting to login", () => {
  for (const path of ["/demo", "/demo/expired", "/api/demo/start"]) {
    const response = proxy(new NextRequest(`https://club.example${path}`));
    expect(response.headers.get("location")).toBeNull();
  }
});

it("starts a demo without credentials and opens the dashboard", async () => {
  vi.spyOn(demoApi, "config").mockResolvedValue({ enabled: true, minutes: 15, limits: {} });
  const user = { id: "demo-id", full_name: "Demo Runner", is_demo: true } as User;
  const start = vi.spyOn(demoApi, "start").mockResolvedValue(user);
  mount(<DemoPage />);
  const button = screen.getByRole("button", { name: "Start 15-minute demo" });
  await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
  await userEvent.click(button);
  await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/dashboard"));
  expect(start).toHaveBeenCalledTimes(1);
  expect(screen.queryByLabelText("Password")).toBeNull();
});

it("shows when the demo is disabled", async () => {
  vi.spyOn(demoApi, "config").mockResolvedValue({ enabled: false, minutes: 15, limits: {} });
  mount(<DemoPage />);
  await screen.findByText("The demo is not enabled right now.");
  expect((screen.getByRole("button", { name: "Start 15-minute demo" }) as HTMLButtonElement).disabled).toBe(true);
});

it("displays server usage and sends an expired demo to the expiry screen", async () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-14T12:00:00Z"));
  const expires = "2026-10-14T12:00:02Z";
  session.user = { id: "demo", is_demo: true, demo_expires_at: expires } as User;
  vi.spyOn(demoApi, "status").mockResolvedValue({ expires_at: expires, limits: {}, remaining: { chat: 4, plans: 1, revisions: 1, summaries: 1 } });
  mount(<DemoBanner />);
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(screen.getByText(/Attempts left: 4 chats/)).toBeTruthy();
  await act(async () => { await vi.advanceTimersByTimeAsync(2100); });
  expect(navigation.replace).toHaveBeenCalledWith("/demo/expired");
});

it("does not fetch demo status for a registered user", () => {
  session.user = { id: "registered", is_demo: false } as User;
  const status = vi.spyOn(demoApi, "status");
  mount(<DemoBanner />);
  expect(screen.queryByLabelText("Demo session")).toBeNull();
  expect(status).not.toHaveBeenCalled();
});
