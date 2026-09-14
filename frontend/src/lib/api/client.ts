import { emitUnauthorized } from "@/lib/auth-events";
import { ApiError, type FieldValidationError } from "@/types/api";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:5002";

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
}

interface RawValidationItem {
  loc?: unknown[];
  msg?: string;
}

function parseValidationDetail(detail: unknown): FieldValidationError[] {
  if (!Array.isArray(detail)) return [];

  return (detail as RawValidationItem[])
    .filter((item) => typeof item === "object" && item !== null)
    .map((item) => {
      const loc = Array.isArray(item.loc) ? item.loc : [];
      const field = loc.length > 1 ? loc.slice(1).join(".") : String(loc.at(-1) ?? "");

      return {
        field,
        message: typeof item.msg === "string" ? item.msg : "Invalid value",
      };
    });
}

function extractMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;

  if (
    typeof detail === "object" &&
    detail !== null &&
    "message" in detail &&
    typeof (detail as { message: unknown }).message === "string"
  ) {
    return (detail as { message: string }).message;
  }

  return fallback;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal } = options;

  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      credentials: "include",
      headers:
        body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException &&
      (error.name === "TimeoutError" || error.name === "AbortError")) {
      throw new ApiError({
        kind: "timeout",
        status: null,
        message: "The request timed out. If you were generating a plan, check your plans before trying again.",
      });
    }

    throw new ApiError({
      kind: "network",
      status: null,
      message: "Could not reach the server. Check your connection and try again.",
    });
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const isJson = response.headers
    .get("content-type")
    ?.includes("application/json");
  const payload = isJson ? await response.json().catch(() => null) : null;

  if (!response.ok) {
    const detail = payload?.detail;

    if (response.status === 401) {
      // A 401 from the session-restore check itself just means "not logged
      // in yet" — a normal, expected state, not a session that just expired
      // mid-use. Emitting here too would clear query state that a still-
      // mounted /auth/me query then immediately refetches, 401s again, and
      // re-emits: an infinite loop.
      if (path !== "/auth/me") {
        emitUnauthorized();
      }

      throw new ApiError({
        kind: "unauthorized",
        status: response.status,
        message: extractMessage(detail, "Your session has expired. Please log in again."),
        detail,
      });
    }

    if (response.status === 403) {
      throw new ApiError({
        kind: "forbidden",
        status: response.status,
        message: extractMessage(detail, "You don't have access to do that."),
        detail,
      });
    }

    if (response.status === 422) {
      throw new ApiError({
        kind: "validation",
        status: response.status,
        message: "Some fields need attention.",
        fieldErrors: parseValidationDetail(detail),
        detail,
      });
    }

    if (response.status === 404) {
      throw new ApiError({
        kind: "not_found",
        status: response.status,
        message: extractMessage(detail, "We couldn't find that."),
        detail,
      });
    }

    if (response.status === 409) {
      throw new ApiError({
        kind: "conflict",
        status: response.status,
        message: extractMessage(detail, "This action can't be completed right now."),
        detail,
      });
    }

    if (response.status === 400) {
      throw new ApiError({
        kind: "bad_request",
        status: response.status,
        message: extractMessage(detail, "The request could not be processed."),
        detail,
      });
    }

    throw new ApiError({
      kind: "server",
      status: response.status,
      message: extractMessage(detail, "Something went wrong on the server."),
      detail,
    });
  }

  return payload as T;
}

export const apiClient = {
  get: <T>(path: string, signal?: AbortSignal) =>
    request<T>(path, { method: "GET", signal }),
  post: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>(path, { method: "POST", body, signal }),
  patch: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>(path, { method: "PATCH", body, signal }),
  delete: <T>(path: string, signal?: AbortSignal) =>
    request<T>(path, { method: "DELETE", signal }),
};
