"use client";

import {
  AlertTriangle,
  FileDiff,
  FilePenLine,
  MessagesSquare,
  TerminalSquare,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useAutoScroll } from "@/hooks/use-auto-scroll";
import type { Step } from "@/lib/describe";
import { MarkdownView } from "@/components/thread/markdown-view";
import { DiffCard } from "@/components/thread/diff-card";
import { StepGroup } from "@/components/thread/step-group";
import { TerminalCard } from "@/components/thread/terminal-card";
import { ThinkingDivider } from "@/components/thread/thinking-divider";

function sourceLabel(source?: string): string {
  const normalized = (source || "").trim().toLowerCase();
  if (!normalized) return "Unknown";
  if (normalized === "thread_ui") return "Thread Viewer";
  if (normalized === "slack") return "Slack";
  if (normalized === "slack_subscribed_message") return "Slack Thread";
  if (normalized === "api") return "API";
  return normalized.replace(/_/g, " ");
}

function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return `${words[0][0]}${words[1][0]}`.toUpperCase();
}

export function ActivityFeed({
  steps,
  state,
  participants,
}: {
  steps: Step[];
  state?: string;
  participants?: Array<{ id: string; name?: string; avatar_url?: string | null }>;
}) {
  const activeCount = steps.length;
  const { containerRef, sentinelRef } = useAutoScroll([steps]);
  const [pendingSteps, setPendingSteps] = useState(0);
  const [isNearBottom, setIsNearBottom] = useState(true);
  const previousCountRef = useRef(activeCount);
  const participantsById = new Map(
    (participants || []).map((participant) => [participant.id, participant]),
  );

  function renderStep(step: Step): React.ReactNode {
    if (step.type === "phase") {
      return (
        <div
          key={step.id}
          className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-muted-foreground"
        >
          <FileDiff className="size-3 text-primary" />
          {step.phase}
        </div>
      );
    }
    if (step.type === "thinking") {
      return <ThinkingDivider key={step.id} text={step.text} durationS={step.durationS} />;
    }
    if (step.type === "tool-group") {
      return <StepGroup key={step.id} icon={step.icon} summary={step.summary} calls={step.calls} />;
    }
    if (step.type === "diff") {
      return (
        <DiffCard
          key={step.id}
          file={step.file}
          lang={step.lang}
          oldStr={step.oldStr}
          newStr={step.newStr}
        />
      );
    }
    if (step.type === "terminal") {
      return (
        <TerminalCard
          key={step.id}
          description={step.description}
          command={step.command}
          output={step.output}
          exitCode={step.exitCode}
        />
      );
    }
    if (step.type === "file-changes") {
      return (
        <div key={step.id} className="step-item rounded-sm border border-border bg-card px-3 py-2">
          <div className="mb-1.5 flex items-center gap-2 text-xs text-muted-foreground">
            <FilePenLine className="size-3.5 text-primary" />
            File changes
          </div>
          <div className="space-y-1">
            {step.changes.map((change, index) => (
              <div key={`${change.path}-${index}`} className="text-xs font-mono text-muted-foreground">
                {change.kind} {change.path}
              </div>
            ))}
          </div>
        </div>
      );
    }
    if (step.type === "error") {
      return (
        <div
          key={step.id}
          className="step-item flex items-center gap-2 rounded-sm border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          <AlertTriangle className="size-4 shrink-0" />
          {step.message}
        </div>
      );
    }
    if (step.type === "user-message") {
      const participant = step.userId ? participantsById.get(step.userId) : undefined;
      const displayName = participant?.name || step.userId || "User";
      return (
        <div key={step.id} className="step-item rounded-sm border border-border bg-card px-3 py-2">
          <div className="mb-1.5 flex items-center gap-2 text-xs text-muted-foreground">
            {participant?.avatar_url ? (
              <img src={participant.avatar_url} alt={displayName} className="size-5 rounded-full" />
            ) : (
              <div className="flex size-5 items-center justify-center rounded-full bg-muted text-[10px] font-medium text-muted-foreground">
                {initials(displayName)}
              </div>
            )}
            <span className="text-foreground">{displayName}</span>
            <span className="rounded bg-muted px-1.5 py-0.5 text-[10px]">
              {sourceLabel(step.source)}
            </span>
          </div>
          <div className="whitespace-pre-wrap text-sm text-foreground">{step.text}</div>
        </div>
      );
    }
    if (step.type === "context-group") {
      return (
        <details
          key={step.id}
          className="step-item rounded-sm border border-dashed border-border/70 bg-card px-3 py-2"
        >
          <summary className="cursor-pointer text-xs text-muted-foreground">
            Context updates ({step.items.length})
          </summary>
          <div className="mt-2 space-y-2">
            {step.items.map((item) => {
              const participant = item.userId ? participantsById.get(item.userId) : undefined;
              const displayName = participant?.name || item.userId || "Thread participant";
              return (
                <div key={item.id} className="rounded border border-border/60 bg-background px-2 py-1.5">
                  <div className="mb-1 flex items-center gap-2 text-[11px] text-muted-foreground">
                    <span className="text-foreground">{displayName}</span>
                    <span>{sourceLabel(item.source)}</span>
                  </div>
                  <div className="whitespace-pre-wrap text-xs text-muted-foreground">{item.text}</div>
                </div>
              );
            })}
          </div>
        </details>
      );
    }
    if (step.type === "result") {
      return (
        <div key={step.id} className="step-item rounded-sm border border-border bg-card px-3 py-2">
          <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
            <MessagesSquare className="size-3.5 text-primary" />
            Result
          </div>
          <div className="relative">
            <MarkdownView text={step.text} isStreaming={step.streaming} />
          </div>
        </div>
      );
    }
    return null;
  }

  useEffect(() => {
    if (activeCount <= previousCountRef.current) {
      previousCountRef.current = activeCount;
      return;
    }
    const delta = activeCount - previousCountRef.current;
    previousCountRef.current = activeCount;
    if (!isNearBottom) {
      setPendingSteps((value) => value + delta);
    }
  }, [activeCount, isNearBottom]);

  function handleScroll() {
    const container = containerRef.current;
    if (!container) return;
    const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 120;
    setIsNearBottom(nearBottom);
    if (nearBottom) setPendingSteps(0);
  }

  function jumpToLatest() {
    sentinelRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    setPendingSteps(0);
  }

  return (
    <div className="relative flex-1 min-h-0">
      <div
        ref={containerRef}
        role="log"
        aria-live="polite"
        onScroll={handleScroll}
        className="h-full overflow-y-auto px-5 py-4 space-y-4"
      >
        {activeCount === 0 ? (
          <div className="h-full flex items-center justify-center gap-2 text-sm text-muted-foreground">
            <TerminalSquare className="size-4 text-primary" />
            {state === "idle" ? "No events yet. This thread is idle." : "Waiting for events…"}
          </div>
        ) : (
          steps.map((step) => renderStep(step))
        )}
        <div ref={sentinelRef} className="h-px" />
      </div>
      {pendingSteps > 0 && (
        <button
          type="button"
          onClick={jumpToLatest}
          aria-label={`Jump to latest, ${pendingSteps} new step${pendingSteps === 1 ? "" : "s"}`}
          className="absolute bottom-4 right-5 rounded-full border border-border bg-card px-3 py-1.5 text-xs text-foreground shadow-md hover:bg-accent cursor-pointer"
        >
          ↓ {pendingSteps} new step{pendingSteps === 1 ? "" : "s"}
        </button>
      )}
    </div>
  );
}
