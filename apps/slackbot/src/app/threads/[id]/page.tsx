"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { CircleStop, Info, LoaderCircle, Menu, RefreshCw, Timer } from "lucide-react";
import { ActivityFeed } from "@/components/thread/activity-feed";
import { MessageInput } from "@/components/thread/message-input";
import { useThreadLayout } from "@/components/thread/thread-layout";
import { ParticipantAvatars } from "@/components/thread/participant-avatars";
import { PhaseProgress } from "@/components/thread/phase-progress";
import { threadName } from "@/lib/thread-name";
import { useThreadStream } from "@/hooks/use-thread-stream";
import { useElapsed } from "@/hooks/use-elapsed";
import { HarnessBadge } from "@/components/ui/harness-badge";
import { StateDot } from "@/components/ui/state-dot";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const ENGINEER_REPLY_ONLY_MESSAGE = "Engineer threads accept input only while waiting for a reply.";

function isRunBusyError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  const message = error.message.toLowerCase();
  return (
    message.includes("already in progress") ||
    message.includes("run is already in progress") ||
    message.includes("already running") ||
    message.includes("in progress for this thread")
  );
}

function isBenignInterruptError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  const message = error.message.toLowerCase();
  return (
    message.includes("no session") ||
    message.includes("no active container") ||
    (message.includes("no active") && (message.includes("interrupt") || message.includes("process")))
  );
}

export default function ThreadDetailPage() {
  const params = useParams();
  const { openMobileSidebar } = useThreadLayout();
  const threadKey = decodeURIComponent(params.id as string);
  const {
    thread,
    error,
    fetchThread,
    isReconnecting,
    agentStatus,
    tokenUsage,
    chatStatus,
    sendThreadMessage,
    interruptThread,
    liveSteps,
  } = useThreadStream(threadKey);
  const humanName = thread?.thread_name || threadName(threadKey);
  const [isInterrupting, setIsInterrupting] = useState(false);
  const [interruptError, setInterruptError] = useState<string | null>(null);
  const isEngineer = thread?.harness === "engineer";
  const isWaiting = thread?.state === "waiting";
  const isRunning = thread?.state === "running" || thread?.state === "working";
  const isAgentRunning = isRunning;
  const canSendFromComposer = !isEngineer || isWaiting;
  const canInterrupt = !!thread && !isEngineer && isAgentRunning;
  const activeTurnStartedAt =
    thread && thread.turns.length > 0 ? thread.turns[thread.turns.length - 1]?.started_at : null;
  const elapsedAnchor = isRunning ? activeTurnStartedAt : thread?.last_activity;
  const liveElapsed = useElapsed(elapsedAnchor, Boolean(isRunning));
  const tokenTicker = tokenUsage
    ? `${tokenUsage.total_tokens.toLocaleString()} tok / ${
        tokenUsage.cost_usd === null ? "--" : `$${tokenUsage.cost_usd.toFixed(4)}`
      }${tokenUsage.estimated ? "~" : ""}`
    : "-- tok / --";
  const phases = liveSteps.flatMap((step) => (step.type === "phase" ? [step.phase] : []));

  const stopThreadRun = useCallback(async (options?: { suppressError?: boolean }) => {
    if (!thread || !canInterrupt || isInterrupting) return false;
    setInterruptError(null);
    setIsInterrupting(true);
    try {
      await interruptThread();
      fetchThread();
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Interrupt failed.";
      if (!options?.suppressError) {
        setInterruptError(message);
      }
      throw new Error(message);
    } finally {
      setIsInterrupting(false);
    }
  }, [canInterrupt, fetchThread, interruptThread, isInterrupting, thread]);

  const sendFromComposer = useCallback(
    async (message: string) => {
      if (!thread) return false;
      setInterruptError(null);
      if (!canSendFromComposer) {
        throw new Error(ENGINEER_REPLY_ONLY_MESSAGE);
      }
      const route = isEngineer && isWaiting ? "reply" : "execute";

      if (isAgentRunning && canInterrupt) {
        const shouldInterrupt = window.confirm(
          "This will interrupt the current run and send your new message. Continue?",
        );
        if (!shouldInterrupt) return false;
        try {
          await stopThreadRun({ suppressError: true });
        } catch (error) {
          if (!isBenignInterruptError(error)) throw error;
          setInterruptError(null);
        }
      }

      const sendOnce = async () => {
        await sendThreadMessage(message, {
          route,
          ...(route === "execute"
            ? { harness: thread.harness === "engineer" ? "amp" : thread.harness }
            : {}),
        });
      };

      const maxAttempts = route === "execute" ? 6 : 1;
      for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
        try {
          await sendOnce();
          setInterruptError(null);
          fetchThread();
          return true;
        } catch (error) {
          if (!isRunBusyError(error) || attempt === maxAttempts - 1) throw error;
          await fetchThread();
          const retryDelayMs = Math.min(2000, 200 * 2 ** attempt);
          await new Promise<void>((resolve) => {
            window.setTimeout(resolve, retryDelayMs);
          });
        }
      }

      return false;
    },
    [
      fetchThread,
      isAgentRunning,
      canInterrupt,
      canSendFromComposer,
      isEngineer,
      isWaiting,
      sendThreadMessage,
      stopThreadRun,
      thread,
    ],
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const targetIsInput =
        e.target instanceof HTMLElement &&
        e.target.closest("input, textarea, select, [contenteditable='true']");

      if (targetIsInput) return;

      if (e.key.toLowerCase() === "r") {
        e.preventDefault();
        fetchThread();
        return;
      }

      if (e.key.toLowerCase() === "s" && canInterrupt) {
        e.preventDefault();
        if (!window.confirm("Stop the running agent for this thread?")) {
          return;
        }
        void stopThreadRun().catch(() => undefined);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [canInterrupt, fetchThread, stopThreadRun]);

  useEffect(() => {
    if (!thread) return;
    const previousTitle = document.title;
    if (thread.state === "working" || thread.state === "running") {
      document.title = `● Working - ${humanName}`;
    } else if (thread.state === "waiting") {
      document.title = `⚠ Input needed - ${humanName}`;
    } else if (thread.state === "error") {
      document.title = `✗ Error - ${humanName}`;
    } else {
      document.title = `✓ Done - ${humanName}`;
    }
    return () => {
      document.title = previousTitle;
    };
  }, [humanName, thread]);

  if (error && !thread) {
    return (
      <div className="flex h-full min-h-0 items-center justify-center bg-background">
        <div className="text-center">
          <p className="mb-4 text-sm text-destructive">{error}</p>
          <button
            type="button"
            onClick={fetchThread}
            className="cursor-pointer rounded-sm border border-border bg-transparent px-3 py-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!thread) {
    return (
      <div className="flex h-full min-h-0 items-center justify-center bg-background">
        <div className="text-center">
          <p className="inline-flex items-center gap-2 text-sm text-muted-foreground">
            <LoaderCircle className="size-4 animate-spin text-primary" />
            Connecting…
          </p>
          <p className="mt-2 text-xs font-mono text-muted-foreground">{threadName(threadKey)}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      <div className="shrink-0 border-b border-border bg-background">
        <div className="mx-auto w-full max-w-[980px] px-4 py-3 sm:px-5">
          <div className="flex min-w-0 items-center gap-2">
            <button
              type="button"
              onClick={openMobileSidebar}
              aria-label="Open thread list"
              className="inline-flex size-8 shrink-0 items-center justify-center rounded-sm border border-border text-muted-foreground transition-colors hover:bg-accent hover:text-foreground md:hidden"
            >
              <Menu className="size-4" />
            </button>
            <HarnessBadge harness={thread.harness} />
            <span className="min-w-0 truncate text-[12px] font-medium text-foreground">{humanName}</span>
            <span className="ml-auto inline-flex items-center gap-1 text-[11px] text-muted-foreground">
              <StateDot state={thread.state} />
              {thread.state}
            </span>
          </div>

          <div className="mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-muted-foreground">
            <ParticipantAvatars participants={thread.participants} size={20} />
            <span>
              {thread.turns.length} turn{thread.turns.length === 1 ? "" : "s"}
            </span>
            <span className="inline-flex items-center gap-1">
              <Timer className="size-3.5" />
              {liveElapsed}
            </span>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="hidden cursor-help font-mono md:inline">{tokenTicker}</span>
              </TooltipTrigger>
              <TooltipContent>
                <div className="space-y-0.5 text-xs">
                  <div>Input: {tokenUsage?.input_tokens?.toLocaleString() ?? "--"}</div>
                  <div>Output: {tokenUsage?.output_tokens?.toLocaleString() ?? "--"}</div>
                  <div>Total: {tokenUsage?.total_tokens?.toLocaleString() ?? "--"}</div>
                  <div>Model: {tokenUsage?.model ?? "--"}</div>
                  <div>{tokenUsage?.authoritative ? "Authoritative usage" : "Usage unavailable"}</div>
                </div>
              </TooltipContent>
            </Tooltip>
            <Popover>
              <PopoverTrigger asChild>
                <button
                  type="button"
                  className="cursor-pointer text-muted-foreground transition-colors hover:text-foreground"
                  aria-label="Show thread metadata"
                >
                  <Info className="size-3.5" />
                </button>
              </PopoverTrigger>
              <PopoverContent className="w-[320px]">
                <div className="space-y-2 text-xs">
                  <div className="font-semibold text-foreground">Debug IDs</div>
                  <div className="break-all font-mono text-muted-foreground">{thread.slack_thread_key}</div>
                  {thread.agent_thread_id ? (
                    <div className="break-all font-mono text-muted-foreground">{thread.agent_thread_id}</div>
                  ) : null}
                </div>
              </PopoverContent>
            </Popover>
            {canInterrupt && (
              <button
                type="button"
                onClick={() => void stopThreadRun().catch(() => undefined)}
                disabled={isInterrupting}
                className="inline-flex cursor-pointer items-center gap-1 rounded-sm border-none bg-transparent p-0 text-[11px] text-destructive transition-colors hover:opacity-80 disabled:opacity-60"
              >
                <CircleStop className={isInterrupting ? "size-3.5 animate-pulse" : "size-3.5"} />
                {isInterrupting ? "Stopping…" : "Stop"}
              </button>
            )}
            <button
              type="button"
              onClick={fetchThread}
              className="inline-flex cursor-pointer items-center gap-1 rounded-sm border-none bg-transparent p-0 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
            >
              <RefreshCw className="size-3.5" />
              Refresh
            </button>
          </div>

          {(() => {
            const showReconnect = isReconnecting && thread.state !== "error";
            const showError =
              !!error &&
              !(thread.state === "error" && error.startsWith("Stream disconnected."));
            return showError || !!interruptError || showReconnect;
          })() && (
            <div className="mt-2 inline-flex items-center gap-1.5 text-[11px] text-amber-300">
              <RefreshCw className={isReconnecting ? "size-3.5 animate-spin" : "size-3.5"} />
              {interruptError ??
                (thread.state === "error" && error?.startsWith("Stream disconnected.")
                  ? null
                  : error) ??
                (isReconnecting ? "Reconnecting stream…" : "")}
            </div>
          )}
          {chatStatus === "submitted" || chatStatus === "streaming" ? (
            <div className="mt-1 inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <LoaderCircle className="size-3.5 animate-spin text-primary" />
              Live UI stream connected
            </div>
          ) : null}
          {agentStatus ? <div className="mt-1 text-[11px] text-muted-foreground">{agentStatus}</div> : null}

          {isEngineer && phases.length > 0 && (
            <div className="mt-2">
              <PhaseProgress phases={phases} />
            </div>
          )}
        </div>
      </div>

      <div className="mx-auto flex min-h-0 w-full max-w-[980px] flex-1 flex-col">
        <ActivityFeed steps={liveSteps} state={thread.state} participants={thread.participants} />

        <div className="shrink-0 px-5 pb-3">
          <MessageInput
            mode={isEngineer && isWaiting ? "reply" : "execute"}
            state={thread.state}
            isAgentRunning={canInterrupt}
            canSend={canSendFromComposer}
            blockedReason={ENGINEER_REPLY_ONLY_MESSAGE}
            onSend={sendFromComposer}
            onStop={stopThreadRun}
          />
        </div>
      </div>
    </div>
  );
}
