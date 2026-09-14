import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import DashboardPage from "@/app/(app)/dashboard/page";
import { recommendationsApi, surveysApi } from "@/lib/api";
import { ApiError } from "@/types/api";

vi.mock("@/hooks/use-current-user", () => ({ useCurrentUser: () => ({ user: { full_name: "Demo Runner" }, isLoading: false }) }));
vi.mock("@/components/chat/coach-chat-provider", () => ({ useCoachChat: () => ({ openChat: vi.fn() }) }));
vi.mock("@/components/plans/generate-plan-button", () => ({ GeneratePlanButton: () => <button>Generate my plan</button> }));
vi.mock("@/components/plans/recommendation-card", () => ({ RecommendationCard: () => <div>Saved plan</div> }));

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><DashboardPage /></QueryClientProvider>);
}

it.each(["survey", "recommendations"])("shows a %s failure and recovers on retry", async (failed) => {
  const survey = vi.spyOn(surveysApi, "getLatest").mockResolvedValue({ id: "survey" } as Awaited<ReturnType<typeof surveysApi.getLatest>>);
  const plans = vi.spyOn(recommendationsApi, "list").mockResolvedValue([]);
  (failed === "survey" ? survey : plans).mockRejectedValueOnce(new Error("Unavailable"));
  mount();
  await screen.findByRole("alert");
  expect(screen.queryByText("Complete your running survey")).toBeNull();
  expect(screen.queryByText("Generate your first plan")).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Try again" }));
  await screen.findByText("Generate your first plan");
  expect(screen.queryByRole("alert")).toBeNull();
  expect(survey).toHaveBeenCalledTimes(failed === "survey" ? 2 : 1);
  expect(plans).toHaveBeenCalledTimes(failed === "recommendations" ? 2 : 1);
});

it("still shows onboarding for a genuine missing survey", async () => {
  vi.spyOn(surveysApi, "getLatest").mockRejectedValue(new ApiError({ kind: "not_found", status: 404, message: "No survey" }));
  vi.spyOn(recommendationsApi, "list").mockResolvedValue([]);
  mount();
  await screen.findByText("Complete your running survey");
  expect(screen.queryByRole("alert")).toBeNull();
});
