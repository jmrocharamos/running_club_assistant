import type { ReactNode } from "react";

import { CoachChatProvider } from "@/components/chat/coach-chat-provider";
import { CoachChatWidget } from "@/components/chat/coach-chat-widget";

import { Header } from "./header";
import { Sidebar } from "./sidebar";
import { DemoBanner } from "@/components/demo-banner";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <CoachChatProvider>
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Header />
          <DemoBanner />
          <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-6 md:px-8 md:py-8">
            {children}
          </main>
        </div>
      </div>
      <CoachChatWidget />
    </CoachChatProvider>
  );
}
