"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { CircleStop, Info, LoaderCircle, Menu, RefreshCw, Timer } from "lucide-react";
import { ActivityFeed } from "@/components/thread/activity-feed";
import { useThreadLayout } from "@/components/thread/thread-layout";
import { ParticipantAvatars } from "@/components/thread/participant-avatars";
import { PhaseProgress } from "@/components/thread/phase-progress";
import { ReplyInput } from "@/components/thread/reply-input";
import { threadName } from "@/lib/thread-name";
import { useThreadStream } from "@/hooks/use-thread-stream";
import { useElapsed } from "@/hooks/use-elapsed";
import { HarnessBadge } from "@/components/ui/harness-badge";
import { StateDot } from "@/components/ui/state-dot";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { BASE } from "@/lib/constants";

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
    sendReply,
    liveSteps,
  } = useThreadStream(threadKey);
  const humanName = thread?.thread_name || threadName(threadKey);
  const [isInterrupting, setIsInterrupting] = useState(false);
  const [interruptError, setInterruptError] = useState<string | null>(null);
  const isEngineer = thread?.harness === "engineer";
  const isWaiting = thread?.state === "waiting";
  const isRunning = thread?.state === "running" || thread?.state === "working";
  const canInterrupt = !!thread && !isEngineer && isRunning;
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

  const interruptRun = useCallback(async () => {
    if (!thread || !canInterrupt || isInterrupting) return;
    setInterruptError(null);
    setIsInterrupting(true);
    try {
      const res = await fetch(`${BASE}/api/agent/interrupt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slack_thread_key: threadKey }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data?.error) {
        const message =
          typeof data?.error === "string"
            ? data.error
            : `Interrupt failed${res.ok ? "" : ` (${res.status})`}.`;
        setInterruptError(message);
        return;
      }
      fetchThread();
    } finally {
      setIsInterrupting(false);
    }
  }, [canInterrupt, fetchThread, isInterrupting, thread, threadKey]);

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
        void interruptRun();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [canInterrupt, fetchThread, interruptRun]);

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
                onClick={interruptRun}
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

        {isEngineer && isWaiting && (
          <div className="shrink-0 px-4 pb-3 sm:px-5">
            <ReplyInput threadKey={thread.slack_thread_key} onSend={sendReply} />
          </div>
        )}
      </div>
    </div>
  );
}
