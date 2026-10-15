"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSession } from "@/components/providers/session-provider";
import { demoApi } from "@/lib/api/demo";

export function DemoBanner() {
  const { user } = useSession();
  const router = useRouter();
  const [clock, setClock] = useState<number | null>(null);
  const status = useQuery({ queryKey: ["demo-status"], queryFn: demoApi.status, enabled: !!user?.is_demo,
    refetchInterval: 10_000, retry: false });
  const expiry = status.data?.expires_at ?? user?.demo_expires_at;
  useEffect(() => {
    if (!user?.is_demo || !expiry) return;
    const tick = () => {
      setClock(Date.now());
      if (Date.now() >= new Date(expiry).getTime()) router.replace("/demo/expired");
    };
    const interval = setInterval(tick, 1000);
    tick();
    return () => clearInterval(interval);
  }, [user?.is_demo, expiry, router]);
  if (!user?.is_demo || !expiry) return null;
  const seconds = clock === null ? null : Math.max(0, Math.ceil((new Date(expiry).getTime() - clock) / 1000));
  const left = status.data?.remaining;
  return <aside aria-label="Demo session" className="space-y-1 border-b bg-muted px-4 py-3 text-sm md:px-8">
    <p className="font-medium">Demo · {seconds === null ? "Loading timer…" : `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')} remaining`} · OpenAI</p>
    {left && <p>Attempts left: {left.chat} chats · {left.plans} plan · {left.revisions} revision · {left.summaries} summary</p>}
    {status.isError && <p role="status">Couldn’t refresh usage. Limits are still enforced by the server.</p>}
    <p className="text-muted-foreground">Use sample information. <Link href="/register" className="text-primary underline">Create an account</Link> to start a permanent workspace.</p>
  </aside>;
}
