import type { CompletedChatSession } from "@/types";

const labels: Record<string, string> = {
  current_goal: "Goal", preferences: "Preferences", topics_of_interest: "Topics of interest", progress: "Reported progress",
};

function readable(value: string | string[] | null) {
  return Array.isArray(value) ? value.join(", ") || "None" : value || "None";
}

export function SessionRecap({ session }: { session: CompletedChatSession }) {
  return <div className="space-y-4 text-sm">
    <section><h3 className="font-semibold">Recap</h3><p className="mt-1 whitespace-pre-wrap">{session.recap}</p></section>
    <section><h3 className="font-semibold">Agreed next steps</h3>
      {session.next_steps.length ? <ul className="mt-1 list-inside list-disc">{session.next_steps.map(step => <li key={step.id}>{step.text}{step.completed && " · Completed"}</li>)}</ul>
        : <p className="mt-1 text-muted-foreground">No next steps were explicitly agreed.</p>}
    </section>
    {!!session.open_questions.length && <section><h3 className="font-semibold">Open questions</h3><ul className="mt-1 list-inside list-disc">{session.open_questions.map((question, index) => <li key={index}>{question}</li>)}</ul></section>}
    <section><h3 className="font-semibold">Memory changes</h3>
      {session.memory_changes.length ? <div className="mt-2 space-y-2">{session.memory_changes.map(change => <div key={change.field} className="rounded-lg border p-3">
        <p className="font-medium">{labels[change.field] ?? change.field}</p>
        <p className="text-muted-foreground">Previously: {readable(change.before)}</p><p>Now: {readable(change.after)}</p>
        {change.runner_quote && <p className="mt-1 text-xs text-muted-foreground">You said: “{change.runner_quote}”</p>}
      </div>)}</div> : <p className="mt-1 text-muted-foreground">Nothing new was added to your runner memory.</p>}
    </section>
  </div>;
}
