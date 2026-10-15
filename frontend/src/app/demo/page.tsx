"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AuthShell } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { demoApi } from "@/lib/api/demo";
import { queryKeys } from "@/lib/query-keys";
import { broadcastSessionChanged } from "@/lib/session-sync";

export default function DemoPage() {
  const router = useRouter();
  const cache = useQueryClient();
  const config = useQuery({ queryKey: ["demo-config"], queryFn: demoApi.config, retry: false });
  const start = useMutation({
    mutationFn: demoApi.start,
    onSuccess: user => {
      cache.setQueryData(queryKeys.currentUser, user);
      cache.removeQueries({ predicate: query => query.queryKey[0] !== queryKeys.currentUser[0] });
      broadcastSessionChanged();
      router.push("/dashboard");
    },
  });
  return <AuthShell title="Try the running coach" subtitle="A 15-minute demo. No account required." footer={<Link href="/login" className="text-primary hover:underline">Back to login</Link>}>
    <div className="space-y-4 text-sm">
      <p>Explore a sample runner profile, ask the coach questions, generate a four-week plan, and try feedback and revision.</p>
      <ul className="list-inside list-disc space-y-1"><li>5 chat messages</li><li>1 plan-generation attempt</li><li>1 revision attempt</li><li>1 end-chat summary</li></ul>
      <p className="text-muted-foreground">Use fictional information. Each visitor has a separate temporary workspace. Access ends after 15 minutes and demo content is automatically removed. Creating an account starts a fresh workspace.</p>
      {config.isError && <p role="alert">Couldn’t check demo availability. Please try again.</p>}
      {config.data && !config.data.enabled && <p role="status">The demo is not enabled right now.</p>}
      {start.isError && <p role="alert">{start.error.message}</p>}
      <Button className="w-full" disabled={!config.data?.enabled || start.isPending} onClick={() => start.mutate()}>{start.isPending ? "Starting…" : "Start 15-minute demo"}</Button>
    </div>
  </AuthShell>;
}
