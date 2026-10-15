"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useForm } from "react-hook-form";

import { AuthShell } from "@/components/auth/auth-shell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authApi } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { broadcastSessionChanged } from "@/lib/session-sync";
import { loginSchema, type LoginFormValues } from "@/lib/validation/auth";
import { ApiError } from "@/types/api";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
  });

  const mutation = useMutation({
    mutationFn: (values: LoginFormValues) => authApi.login(values),
    onSuccess: (user) => {
      // Set identity first, then drop every other cached query. None of the
      // other query keys are scoped per-user, so without this a second
      // account logging in on top of a first (without a full reload in
      // between) would keep showing the first account's cached
      // dashboard/plan data until each query's own staleTime expired.
      // Clearing currentUser too (even transiently) would flash
      // "unauthenticated" and bounce AuthGuard back to /login, so it's
      // excluded from the wipe.
      queryClient.setQueryData(queryKeys.currentUser, user);
      queryClient.removeQueries({
        predicate: (query) => query.queryKey[0] !== queryKeys.currentUser[0],
      });
      // Tell any other open tabs a session change happened so they don't
      // keep showing a different account's stale identity/data.
      broadcastSessionChanged();
      router.push(searchParams.get("next") || "/dashboard");
    },
  });

  return (
    <form
      className="space-y-4"
      onSubmit={handleSubmit((values) => mutation.mutate(values))}
      noValidate
    >
      {mutation.isError && (
        <Alert variant="destructive">
          <AlertDescription>
            {mutation.error instanceof ApiError
              ? mutation.error.message
              : "Something went wrong. Please try again."}
          </AlertDescription>
        </Alert>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="email">Email</Label>
        <Input id="email" type="email" autoComplete="email" {...register("email")} />
        {errors.email && (
          <p className="text-sm text-destructive">{errors.email.message}</p>
        )}
      </div>

      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <Label htmlFor="password">Password</Label>
          <Link
            href="/forgot-password"
            className="text-xs font-medium text-primary hover:underline"
          >
            Forgot password?
          </Link>
        </div>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          {...register("password")}
        />
        {errors.password && (
          <p className="text-sm text-destructive">{errors.password.message}</p>
        )}
      </div>

      <Button type="submit" className="w-full" disabled={mutation.isPending}>
        {mutation.isPending && <Loader2 className="size-4 animate-spin" />}
        Log in
      </Button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <AuthShell
      title="Running Club Assistant"
      subtitle="Your AI running coach."
      footer={
        <>
          Don&apos;t have an account?{" "}
          <Link href="/register" className="font-medium text-primary hover:underline">
            Create one
          </Link>
        </>
      }
    >
      <Suspense
        fallback={
          <div className="flex justify-center py-6">
            <Loader2 className="size-5 animate-spin text-muted-foreground" />
          </div>
        }
      >
        <LoginForm />
      </Suspense>
      <Link href="/demo" className="mt-4 block text-center text-sm font-medium text-primary hover:underline">Try a 15-minute demo without an account</Link>
    </AuthShell>
  );
}
