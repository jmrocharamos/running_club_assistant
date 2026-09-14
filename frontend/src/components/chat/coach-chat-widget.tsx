"use client";

import { MessageCircle, X } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { BravesMark } from "@/components/brand/logo";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

import { ChatComposer } from "./chat-composer";
import { ChatMessage } from "./chat-message";
import { useCoachChat } from "./coach-chat-provider";
import { EndChatSummaryDialog } from "./end-chat-summary-dialog";

const WELCOME_MESSAGE = {
  role: "assistant" as const,
  content:
    "Hi! I’m your Berlin Braves running assistant. Ask me about training and recovery, fueling, running shoes, or club schedules, events, gym, and yoga.",
};

function ThinkingBubble() {
  return (
    <div className="flex items-start gap-2.5">
      <BravesMark className="size-7 shrink-0" />
      <div className="flex items-center gap-1 rounded-2xl rounded-tl-sm bg-muted px-3.5 py-2.5">
        {[0, 1, 2].map((index) => (
          <span
            key={index}
            className="size-1.5 animate-bounce rounded-full bg-muted-foreground/60"
            style={{ animationDelay: `${index * 120}ms` }}
          />
        ))}
      </div>
    </div>
  );
}

export function CoachChatWidget() {
  const {
    messages,
    isHistoryLoading,
    isHistoryError,
    isHistoryFetching,
    retryHistory,
    isOpen,
    hasUnread,
    closeChat,
    toggleChat,
    sendMessage,
    retryMessage,
    isSending,
    endChat,
    isEndingChat,
    endedChatSummary,
    dismissEndedChatSummary,
  } = useCoachChat();

  const isHistoryUnavailable = isHistoryLoading || isHistoryError || isHistoryFetching;

  const [isConfirmingEnd, setIsConfirmingEnd] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const scrollAnchorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  function handleClose() {
    closeChat();
    triggerRef.current?.focus();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.stopPropagation();
      handleClose();
    }
  }

  function handleConfirmEndChat() {
    setIsConfirmingEnd(false);
    endChat();
  }

  return (
    <>
      <Button
        ref={triggerRef}
        type="button"
        onClick={toggleChat}
        aria-expanded={isOpen}
        aria-label={isOpen ? "Close assistant chat" : "Open assistant chat"}
        className={cn(
          "fixed right-4 bottom-[calc(1rem+env(safe-area-inset-bottom))] z-40 size-14 rounded-full shadow-lg sm:right-6",
          isOpen && "ring-2 ring-primary ring-offset-2 ring-offset-background",
        )}
      >
        {isOpen ? <X className="size-5" /> : <MessageCircle className="size-5" />}
        {hasUnread && !isOpen && (
          <span
            className="absolute top-0 right-0 size-3 rounded-full bg-destructive ring-2 ring-background"
            aria-hidden="true"
          />
        )}
      </Button>

      {isOpen && (
        <div
          ref={panelRef}
          role="dialog"
          aria-label="Assistant chat"
          onKeyDown={handleKeyDown}
          className={cn(
            "fixed inset-x-0 bottom-0 z-40 flex h-[85vh] flex-col rounded-t-2xl border bg-card shadow-2xl",
            "sm:inset-x-auto sm:right-6 sm:bottom-[calc(5.5rem+env(safe-area-inset-bottom))] sm:h-[min(600px,calc(100vh-8rem))] sm:w-[400px] sm:max-w-[calc(100vw-2rem)] sm:rounded-2xl",
          )}
        >
          <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
            <div className="flex items-center gap-2">
              <BravesMark className="size-6" />
              <span className="font-display text-sm font-black tracking-tight uppercase">
                Assistant
              </span>
            </div>
            <div className="flex items-center gap-1">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setIsConfirmingEnd(true)}
                disabled={isEndingChat || isSending || isHistoryUnavailable || messages.length === 0}
              >
                {isEndingChat ? "Ending…" : "End chat"}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                onClick={handleClose}
                aria-label="Close assistant chat"
              >
                <X className="size-4" />
              </Button>
            </div>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto p-4">
            {isHistoryLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-10 w-2/3" />
                <Skeleton className="ml-auto h-10 w-1/2" />
              </div>
            ) : isHistoryError ? (
              <div role="alert" className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  Couldn’t load your conversation. Please try again.
                </p>
                <Button onClick={retryHistory} disabled={isHistoryFetching}>
                  {isHistoryFetching ? "Retrying…" : "Retry"}
                </Button>
              </div>
            ) : messages.length === 0 ? (
              <div className="flex h-full items-start">
                <ChatMessage message={WELCOME_MESSAGE} />
              </div>
            ) : (
              messages.map((message, index) => (
                <ChatMessage key={index} message={message} onRetry={retryMessage} />
              ))
            )}
            {isSending && <ThinkingBubble />}
            <div ref={scrollAnchorRef} />
          </div>

          <ChatComposer
            onSend={sendMessage}
            disabled={isSending || isEndingChat || isHistoryUnavailable}
            autoFocus
          />
        </div>
      )}

      <Dialog open={isConfirmingEnd} onOpenChange={setIsConfirmingEnd}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>End this chat?</DialogTitle>
            <DialogDescription>
              Your assistant will record and summarize this conversation to
              remember for next time. This can&apos;t be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose
              render={<Button type="button" variant="outline" disabled={isEndingChat} />}
            >
              Cancel
            </DialogClose>
            <Button type="button" onClick={handleConfirmEndChat} disabled={isEndingChat || isHistoryUnavailable}>
              {isEndingChat ? "Ending…" : "End chat"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <EndChatSummaryDialog
        chat={endedChatSummary}
        open={endedChatSummary !== null}
        onOpenChange={(open) => {
          if (!open) dismissEndedChatSummary();
        }}
      />
    </>
  );
}
