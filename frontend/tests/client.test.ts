import { describe, expect, it, vi } from "vitest";
import { apiClient } from "@/lib/api/client";

describe("request failures", () => {
  it.each(["TimeoutError", "AbortError"])("classifies %s as a timeout", async (name) => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("Stopped", name)));
    await expect(apiClient.post("/recommendations/generate")).rejects.toMatchObject({
      kind: "timeout",
      message: expect.stringContaining("check your plans"),
    });
  });
  it("keeps network errors distinct", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(apiClient.get("/surveys/latest")).rejects.toMatchObject({ kind: "network" });
  });
  it("preserves the finished-plan message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "This plan has finished. Generate a new plan." }),
      { status: 409, headers: { "content-type": "application/json" } },
    )));
    await expect(apiClient.post("/recommendations/123/revise")).rejects.toMatchObject({
      kind: "conflict", message: "This plan has finished. Generate a new plan.",
    });
  });
});
