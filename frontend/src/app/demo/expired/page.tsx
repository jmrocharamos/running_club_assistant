import Link from "next/link";
import { AuthShell } from "@/components/auth/auth-shell";

export default function DemoExpiredPage() {
  return <AuthShell title="Your demo has ended" subtitle="Thanks for trying the running coach." footer={<Link href="/login" className="text-primary hover:underline">Log in to an existing account</Link>}>
    <div className="space-y-4 text-sm"><p>The 15-minute session is closed. Demo data is temporary and will be removed automatically.</p>
      <p>Create an account to start your own profile and keep future plans and conversations.</p>
      <Link href="/register" className="block rounded-md bg-primary px-4 py-2 text-center font-medium text-primary-foreground">Create an account</Link>
    </div>
  </AuthShell>;
}
