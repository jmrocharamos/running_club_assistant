"use client";

import { ClipboardList, MessageCircle, ScrollText } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useCoachChat } from "@/components/chat/coach-chat-provider";
import { GeneratePlanButton } from "@/components/plans/generate-plan-button";
import { RecommendationCard } from "@/components/plans/recommendation-card";
import { useCurrentUser } from "@/hooks/use-current-user";
import { useRecommendations } from "@/hooks/use-recommendations";
import { useLatestSurvey } from "@/hooks/use-survey";

export default function DashboardPage() {
  const { openChat } = useCoachChat();
  const { user, isLoading: isUserLoading } = useCurrentUser();
  const surveyQuery = useLatestSurvey();
  const recommendationsQuery = useRecommendations();
  const survey = surveyQuery.data;
  const recommendations = recommendationsQuery.data;
  const isLoading = isUserLoading || surveyQuery.isLoading || recommendationsQuery.isLoading;

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (surveyQuery.isError || recommendationsQuery.isError) {
    const isRetrying = surveyQuery.isFetching || recommendationsQuery.isFetching;
    return (
      <Card role="alert">
        <CardHeader>
          <CardTitle>Couldn’t load your dashboard</CardTitle>
          <CardDescription>
            We couldn’t retrieve your training information. Please try again.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            disabled={isRetrying}
            onClick={() => {
              if (surveyQuery.isError) void surveyQuery.refetch();
              if (recommendationsQuery.isError) void recommendationsQuery.refetch();
            }}
          >
            {isRetrying ? "Retrying…" : "Try again"}
          </Button>
        </CardContent>
      </Card>
    );
  }

  const hasSurvey = Boolean(survey);
  const latestRecommendation = recommendations?.[0] ?? null;
  const recentRecommendations = recommendations?.slice(0, 3) ?? [];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-display text-2xl font-black tracking-tight">
          Welcome back{user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Here&apos;s where your training stands today.
        </p>
      </div>

      {!hasSurvey && (
        <Card className="border-primary/30 bg-primary/5">
          <CardHeader>
            <CardTitle className="text-base">Complete your running survey</CardTitle>
            <CardDescription>
              Tell your coach about your goals and running history so we can
              build a plan around you.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button render={<Link href="/survey/new" />} nativeButton={false}>
              <ClipboardList className="size-4" />
              Start survey
            </Button>
          </CardContent>
        </Card>
      )}

      {hasSurvey && !latestRecommendation && (
        <Card className="border-primary/30 bg-primary/5">
          <CardHeader>
            <CardTitle className="text-base">Generate your first plan</CardTitle>
            <CardDescription>
              Your survey is ready. Let your coach build a personalized
              running plan from it.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <GeneratePlanButton label="Generate my plan" />
          </CardContent>
        </Card>
      )}

      {latestRecommendation && (
        <section className="space-y-3">
          <h2 className="text-sm font-medium text-muted-foreground">
            Latest plan
          </h2>
          <RecommendationCard recommendation={latestRecommendation} />
        </section>
      )}

      <section className="grid gap-3 sm:grid-cols-2">
        <button type="button" onClick={openChat} className="text-left">
          <Card className="h-full transition-colors hover:border-primary/50">
            <CardHeader className="flex-row items-center gap-3 space-y-0">
              <MessageCircle className="size-5 text-primary" aria-hidden="true" />
              <div>
                <CardTitle className="text-base">Ask your assistant</CardTitle>
                <CardDescription>
                  Get advice, adjust your plan, or ask a question.
                </CardDescription>
              </div>
            </CardHeader>
          </Card>
        </button>
        <Link href="/plans">
          <Card className="h-full transition-colors hover:border-primary/50">
            <CardHeader className="flex-row items-center gap-3 space-y-0">
              <ScrollText className="size-5 text-primary" aria-hidden="true" />
              <div>
                <CardTitle className="text-base">View all plans</CardTitle>
                <CardDescription>
                  Browse your recommendation history.
                </CardDescription>
              </div>
            </CardHeader>
          </Card>
        </Link>
      </section>

      {recentRecommendations.length > 1 && (
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-muted-foreground">
              Recent plans
            </h2>
            <Link
              href="/plans"
              className="text-sm font-medium text-primary hover:underline"
            >
              View all
            </Link>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {recentRecommendations.slice(1).map((recommendation) => (
              <RecommendationCard
                key={recommendation.id}
                recommendation={recommendation}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
