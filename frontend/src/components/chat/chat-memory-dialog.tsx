"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { chatApi } from "@/lib/api";
import type { ChatHistoryResponse, CoachMemorySummary, RunnerMemory } from "@/types";
import { useCoachChat } from "./coach-chat-provider";
import { SessionRecap } from "./session-recap";

type Change = { kind: "memory"; memory: RunnerMemory } | { kind: "delete"; session: string } |
  { kind: "step"; session: string; step: string; completed: boolean };

export function ChatMemoryDialog({ history, open, onOpenChange }: {
  history: ChatHistoryResponse; open: boolean; onOpenChange: (open: boolean) => void;
}) {
  const { applySavedMemory, retryHistory, isSending, isEndingChat, isHistoryFetching } = useCoachChat();
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const mutation = useMutation<CoachMemorySummary, Error, Change>({
    mutationFn: change => {
      const revision = history.revision ?? 0;
      if (change.kind === "memory") return chatApi.updateMemory(change.memory, revision);
      if (change.kind === "delete") return chatApi.deleteSession(change.session, revision);
      return chatApi.updateNextStep(change.session, change.step, change.completed, revision);
    },
    onSuccess: summary => { applySavedMemory(summary); toast.success("Saved"); },
    onError: error => { toast.error(error.message); retryHistory(); },
  });
  const busy = mutation.isPending || isSending || isEndingChat || isHistoryFetching;
  const sessions = history.session_history ?? [];

  return <Dialog open={open} onOpenChange={next => { if (!mutation.isPending) onOpenChange(next); }}>
    <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
      <DialogHeader><DialogTitle>History &amp; memory</DialogTitle>
        <DialogDescription>Review your latest 10 session summaries and control what the coach remembers.</DialogDescription>
      </DialogHeader>
      <section className="space-y-3">
        <h3 className="font-semibold">Runner memory</h3>
        <p className="text-sm text-muted-foreground">Edit a field or clear it to forget that information. Saved session recaps are separate; delete a recap to remove earlier mentions there.</p>
        {!!history.messages.length && <p className="text-sm text-muted-foreground">End your current chat before editing memory.</p>}
        <MemoryEditor key={history.revision ?? 0} history={history} disabled={busy || !!history.messages.length} saving={mutation.isPending} onSave={memory => mutation.mutate({ kind: "memory", memory })} />
      </section>
      <section className="space-y-3 border-t pt-4"><h3 className="font-semibold">Completed sessions</h3>
        <p className="text-sm text-muted-foreground">Deleting a summary also deletes its saved next steps. It does not change runner memory. Full transcripts are not saved after End chat.</p>
        {!sessions.length && <p className="text-sm text-muted-foreground">No completed sessions yet.</p>}
        {sessions.map(session => <details key={session.id} className="rounded-lg border p-3">
          <summary className="cursor-pointer text-sm font-medium">{new Date(session.ended_at).toLocaleString()}</summary>
          <div className="mt-3 space-y-3"><SessionRecap session={session} />
            {!!session.next_steps.length && <fieldset disabled={busy} className="space-y-2"><legend className="mb-2 text-sm font-semibold">Track next steps</legend>
              {session.next_steps.map(step => <label key={step.id} className="flex items-start gap-2 text-sm">
                <input type="checkbox" checked={step.completed} onChange={event => mutation.mutate({ kind: "step", session: session.id, step: step.id, completed: event.target.checked })} className="mt-1" />
                <span>{step.text}</span>
              </label>)}
            </fieldset>}
            {deleteId === session.id ? <div className="space-y-2"><p className="text-sm">Delete this summary and its next steps?</p>
              <div className="flex gap-2"><Button variant="destructive" disabled={busy} onClick={() => mutation.mutate({ kind: "delete", session: session.id })}>Confirm delete</Button>
                <Button variant="outline" disabled={busy} onClick={() => setDeleteId(null)}>Cancel</Button></div>
            </div> : <Button variant="outline" size="sm" disabled={busy} onClick={() => setDeleteId(session.id)}>Delete summary</Button>}
          </div>
        </details>)}
      </section>
    </DialogContent>
  </Dialog>;
}

function MemoryEditor({ history, disabled, saving, onSave }: { history: ChatHistoryResponse; disabled: boolean; saving: boolean; onSave: (memory: RunnerMemory) => void }) {
  const [goal, setGoal] = useState(history.current_goal ?? "");
  const [preferences, setPreferences] = useState(history.preferences.join("\n"));
  const [topics, setTopics] = useState(history.topics_of_interest.join("\n"));
  const [progress, setProgress] = useState(history.progress ?? "");
  const entries = (value: string) => value.split("\n").map(item => item.trim()).filter(Boolean);
  return (
        <form onSubmit={event => { event.preventDefault(); onSave({
          current_goal: goal.trim() || null, preferences: entries(preferences), topics_of_interest: entries(topics), progress: progress.trim() || null,
        }); }} className="space-y-3">
          <fieldset disabled={disabled} className="space-y-3 disabled:opacity-60">
            {[
              { label: "Current goal", value: goal, set: setGoal, max: 2000 },
              { label: "Preferences (one per line)", value: preferences, set: setPreferences, max: 15000 },
              { label: "Topics of interest (one per line)", value: topics, set: setTopics, max: 15000 },
              { label: "Reported progress", value: progress, set: setProgress, max: 2000 },
            ].map(field => <label key={field.label} className="block space-y-1 text-sm"><span>{field.label}</span>
              <textarea value={field.value} onChange={event => field.set(event.target.value)} maxLength={field.max} rows={2} className="w-full rounded-md border bg-background p-2" />
            </label>)}
            <Button type="submit">{saving ? "Saving…" : "Save memory"}</Button>
          </fieldset>
        </form>
  );
}
