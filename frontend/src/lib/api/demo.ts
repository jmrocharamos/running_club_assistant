import { apiClient } from "./client";
import type { User } from "@/types";

export interface DemoStatus {
  expires_at: string;
  remaining: Record<string, number>;
  limits: Record<string, number>;
}

export const demoApi = {
  config: () => apiClient.get<{ enabled: boolean; minutes: number; limits: Record<string, number> }>("/demo/config"),
  start: () => apiClient.post<User>("/demo/start"),
  status: () => apiClient.get<DemoStatus>("/demo/status"),
};
