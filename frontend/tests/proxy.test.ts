import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "../src/proxy";

describe("page authentication with API forwarding", () => {
  it.each(["/api", "/api/auth/login", "/api/users/me"])(
    "passes %s through without a cookie", (path) => {
      const response = proxy(new NextRequest(`https://club.example${path}`));
      expect(response.headers.get("location")).toBeNull();
      expect(response.headers.get("x-middleware-next")).toBe("1");
    },
  );
  it.each(["/dashboard", "/apiary"])("still protects %s", (path) => {
    const response = proxy(new NextRequest(`https://club.example${path}`));
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toContain("/login?next=");
  });
});
