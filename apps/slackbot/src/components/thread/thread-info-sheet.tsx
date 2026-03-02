"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  CircleStop,
  Copy,
  ExternalLink,
  RefreshCw,
  X,
} from "lucide-react";
import { HarnessBadge } from "@/components/ui/harness-badge";
import { StateDot } from "@/components/ui/state-dot";
import { ParticipantAvatars } from "@/components/thread/participant-avatars";
import { cn } from "@/lib/utils";
import type { ThreadDetail } from "@/lib/types";

type TokenUsage = {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number | null;
  estimated: boolean;
  authoritative: boolean;
  model: string | null;
};

type ThreadInfoSheetProps = {
  open: boolean;
  onClose: () => void;
  thread: ThreadDetail;
  tokenUsage: TokenUsage | null;
  elapsed: string;
  onRefresh: () => void;
  onStop?: () => void;
  canStop: boolean;
};

function getFocusableElements(container: HTMLElement): HTMLElement[] {
  const candidates = container.querySelectorAll<HTMLElement>(
    "a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex='-1'])",
  );
  return Array.from(candidates).filter((el) => !el.hasAttribute("disabled") && el.tabIndex >= 0);
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm font-mono tabular-nums text-foreground mt-0.5">{children}</dd>
    </div>
  );
}

function ContextBar({ percent }: { percent: number }) {
  const color = percent > 80 ? "bg-destructive" : percent > 50 ? "bg-amber-500" : "bg-green-500";
  return (
    <div className="h-1.5 rounded-full bg-secondary mt-1 overflow-hidden">
      <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${percent}%` }} />
    </div>
  );
}

export function ThreadInfoSheet({
  open,
  onClose,
  thread,
  tokenUsage,
  elapsed,
  onRefresh,
  onStop,
  canStop,
}: ThreadInfoSheetProps) {
  const sheetRef = useRef<HTMLDivElement>(null);
  const [dragY, setDragY] = useState(0);
  const dragStartRef = useRef<number | null>(null);

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    dragStartRef.current = e.touches[0].clientY;
  }, []);

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (dragStartRef.current === null) return;
    const delta = e.touches[0].clientY - dragStartRef.current;
    if (delta > 0) setDragY(delta);
  }, []);

  const handleTouchEnd = useCallback(() => {
    if (dragY > 100) {
      onClose();
    }
    setDragY(0);
    dragStartRef.current = null;
  }, [dragY, onClose]);

  useEffect(() => {
    if (!open) {
      setDragY(0);
      return;
    }
    const sheet = sheetRef.current;
    const previousFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (sheet) {
      const focusable = getFocusableElements(sheet);
      (focusable[0] ?? sheet).focus();
    }

    const onKey = (e: KeyboardEvent) => {
      if (!sheet) return;
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== "Tab") return;
      const focusable = getFocusableElements(sheet);
      if (focusable.length === 0) {
        e.preventDefault();
        sheet.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (e.shiftKey) {
        if (active === first || !sheet.contains(active)) {
          e.preventDefault();
          last.focus();
        }
      } else if (active === last || !sheet.contains(active)) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previousFocused?.focus();
    };
  }, [open, onClose]);

  const contextPercent = tokenUsage
    ? Math.round((tokenUsage.total_tokens / 200_000) * 100)
    : 0;

  const [channelId, threadTs] = thread.slack_thread_key.split(":");
  const slackUrl = `slack://app_redirect?channel=${channelId}&thread_ts=${threadTs}`;

  function copyLink() {
    if (typeof window === "undefined") return;
    if (!navigator.clipboard?.writeText) return;
    const viewerUrl = `${window.location.origin}/${encodeURIComponent(thread.slack_thread_key)}`;
    void navigator.clipboard
      .writeText(viewerUrl)
      .then(() => onClose())
      .catch(() => {});
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 md:hidden" aria-modal="true" role="dialog" aria-label="Thread details">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div
        ref={sheetRef}
        tabIndex={-1}
        className="absolute inset-x-0 bottom-0 bg-background border-t border-border rounded-t-2xl max-h-[70dvh] overflow-y-auto animate-in slide-in-from-bottom duration-250"
        style={{ transform: dragY > 0 ? `translateY(${dragY}px)` : undefined }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        <div className="flex justify-center pt-3 pb-1">
          <div className="w-8 h-1 bg-border rounded-full" />
        </div>

        <div className="px-5 pb-5">
          <div className="flex items-center justify-between mt-2">
            <h2 className="text-lg font-semibold text-foreground">
              {thread.thread_name || thread.slack_thread_key}
            </h2>
            <button
              type="button"
              onClick={onClose}
              className="size-8 flex items-center justify-center rounded-md text-muted-foreground"
              aria-label="Close"
            >
              <X className="size-4" />
            </button>
          </div>

          <div className="flex items-center gap-2 mt-1 text-sm text-muted-foreground">
            <HarnessBadge harness={thread.harness} />
            <span>·</span>
            <StateDot state={thread.state} />
            <span>{thread.state}</span>
            <span>·</span>
            <span>{elapsed}</span>
          </div>

          <dl className="grid grid-cols-2 gap-y-3 gap-x-4 mt-5">
            <Stat label="Tokens in">{tokenUsage?.input_tokens.toLocaleString() ?? "--"}</Stat>
            <Stat label="Tokens out">{tokenUsage?.output_tokens.toLocaleString() ?? "--"}</Stat>
            <Stat label="Cost">
              {tokenUsage?.cost_usd !== null && tokenUsage?.cost_usd !== undefined
                ? `$${tokenUsage.cost_usd.toFixed(4)}${tokenUsage.estimated ? "~" : ""}`
                : "--"}
            </Stat>
            <Stat label="Model">{tokenUsage?.model ?? "--"}</Stat>
            <Stat label="Turns">{thread.turns.length}</Stat>
            <div>
              <dt className="text-xs text-muted-foreground">Context</dt>
              <dd className="text-sm font-mono tabular-nums text-foreground mt-0.5">{contextPercent}%</dd>
              <ContextBar percent={contextPercent} />
            </div>
          </dl>

          {thread.participants && thread.participants.length > 0 && (
            <div className="mt-5 border-t border-border pt-4">
              <h3 className="text-xs text-muted-foreground font-medium mb-2">Participants</h3>
              <ParticipantAvatars participants={thread.participants} size={28} max={10} />
            </div>
          )}

          <div className="mt-5 border-t border-border pt-4 space-y-1">
            <h3 className="text-xs text-muted-foreground font-medium mb-2">Actions</h3>

            <button
              type="button"
              onClick={() => { onRefresh(); onClose(); }}
              className="w-full flex items-center gap-3 py-3 px-2 rounded-lg text-sm text-foreground active:bg-accent transition-colors"
            >
              <RefreshCw className="size-5 text-muted-foreground" />
              Refresh thread
            </button>

            {canStop && onStop && (
              <button
                type="button"
                onClick={() => { onStop(); onClose(); }}
                className="w-full flex items-center gap-3 py-3 px-2 rounded-lg text-sm text-destructive active:bg-accent transition-colors"
              >
                <CircleStop className="size-5" />
                Stop agent
              </button>
            )}

            <button
              type="button"
              onClick={copyLink}
              className="w-full flex items-center gap-3 py-3 px-2 rounded-lg text-sm text-foreground active:bg-accent transition-colors"
            >
              <Copy className="size-5 text-muted-foreground" />
              Copy link
            </button>

            <a
              href={slackUrl}
              className="w-full flex items-center gap-3 py-3 px-2 rounded-lg text-sm text-foreground active:bg-accent transition-colors no-underline"
            >
              <ExternalLink className="size-5 text-muted-foreground" />
              Open in Slack
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
