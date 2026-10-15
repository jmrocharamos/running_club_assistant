"use client";

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { ChatMemory } from "@/types";
import { SessionRecap } from "./session-recap";

export function EndChatSummaryDialog({ chat, open, onOpenChange }: {
  chat: ChatMemory | null; open: boolean; onOpenChange: (open: boolean) => void;
}) {
  const session = chat?.session_history?.[0];
  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
      <DialogHeader><DialogTitle>Session summary</DialogTitle>
        <DialogDescription>Your recap is saved in History &amp; memory. You can review next steps and edit what the coach remembers there.</DialogDescription>
      </DialogHeader>
      {session && <SessionRecap session={session} />}
    </DialogContent>
  </Dialog>;
}
