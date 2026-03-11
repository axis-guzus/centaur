"use client";

import { X } from "lucide-react";
import { HarnessBadge } from "@/components/ui/harness-badge";
import { StateDot } from "@/components/ui/state-dot";
import { ParticipantAvatars } from "@/components/thread/participant-avatars";
import { ResponsivePanel } from "@/components/ui/responsive-panel";
import { useHaptics } from "@/components/haptics-provider";
import { useMediaQuery } from "@/hooks/use-media-query";
import { cn } from "@/lib/utils";
import {
  formatTokenUsageCost,
  formatTokenUsageCount,
  tokenUsageBreakdownLabel,
  tokenUsageConfidenceLabel,
  tokenUsageModelsList,
} from "@/lib/token-usage";
import { buildThreadActionItems } from "@/lib/thread-actions";
import { threadStateLabel } from "@/lib/status-semantics";
import type { ThreadDetail, ThreadTokenUsage } from "@/lib/types";
import { splitThreadKey } from "@centaur/harness-events";

type ThreadInfoSheetProps = {
  open: boolean;
  onClose: () => void;
  thread: ThreadDetail;
  tokenUsage: ThreadTokenUsage | null;
  elapsed: string;
  onRefresh: () => void;
  onStop?: () => void;
  canStop: boolean;
  mobileOnly?: boolean;
};

type ThreadInfoContentProps = {
  thread: ThreadDetail;
  tokenUsage: ThreadTokenUsage | null;
  elapsed: string;
  onClose: () => void;
  actions: ReturnType<typeof buildThreadActionItems>;
  showHandle: boolean;
};

function Stat({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <dt className="ui-caption">{label}</dt>
      <dd className="mt-1 text-sm font-medium tabular-nums text-foreground">
        {children}
      </dd>
    </div>
  );
}

function ThreadInfoContent({
  thread,
  tokenUsage,
  elapsed,
  actions,
  onClose,
  showHandle,
}: ThreadInfoContentProps) {
  const { trigger } = useHaptics();
  const modelList = tokenUsageModelsList(tokenUsage);
  const breakdownLabel = tokenUsageBreakdownLabel(tokenUsage);
  const usageConfidence = tokenUsageConfidenceLabel(tokenUsage);

  return (
    <>
      {showHandle ? (
        <div className="flex justify-center pb-2 pt-3">
          <div className="h-1 w-8 rounded-full bg-border/80" />
        </div>
      ) : null}
      <div className="px-4 pb-[max(1.25rem,env(safe-area-inset-bottom))] sm:px-5">
        <div className="mt-1 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2
              id="thread-info-title"
              className="text-lg font-semibold text-foreground"
            >
              {thread.thread_name || thread.slack_thread_key}
            </h2>
            <div className="ui-meta mt-2 flex flex-wrap items-center gap-2">
              <HarnessBadge harness={thread.harness} />
              <span className="text-border/60">·</span>
              <span className="inline-flex items-center gap-1">
                <StateDot state={thread.state} />
                <span>{threadStateLabel(thread.state)}</span>
              </span>
              <span className="text-border/60">·</span>
              <span>{elapsed}</span>
            </div>
          </div>
          <button
            type="button"
            onClick={() => { trigger("light"); onClose(); }}
            className="flex size-11 items-center justify-center rounded-lg ui-control-icon text-muted-foreground"
            aria-label="Close"
            data-touch-target
          >
            <X className="size-4" />
          </button>
        </div>

        <section className="thread-surface-soft mt-4 rounded-xl px-4 py-4">
          <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-x-5">
            <Stat label="Total tokens">
              {formatTokenUsageCount(tokenUsage?.total_tokens ?? null)}
            </Stat>
            <Stat label="Tokens in">
              {formatTokenUsageCount(tokenUsage?.input_tokens ?? null)}
            </Stat>
            <Stat label="Tokens out">
              {formatTokenUsageCount(tokenUsage?.output_tokens ?? null)}
            </Stat>
            <Stat label="Cost">{formatTokenUsageCost(tokenUsage) ?? "--"}</Stat>
            <Stat label="Model">{modelList}</Stat>
            <Stat label="Usage">{usageConfidence}</Stat>
            <Stat label="Split">{breakdownLabel}</Stat>
            <Stat label="Messages">{thread.message_count}</Stat>
          </dl>
        </section>

        {thread.participants && thread.participants.length > 0 && (
          <section className="thread-surface-soft mt-4 rounded-xl px-4 py-4">
            <h3 className="ui-kicker mb-3 text-muted-foreground">
              Participants
            </h3>
            <ParticipantAvatars
              participants={thread.participants}
              size={28}
              max={10}
              decorative={false}
            />
          </section>
        )}

        <section className="thread-surface-soft mt-4 rounded-xl px-4 py-4">
          <h3 className="ui-kicker mb-3 text-muted-foreground">
            Details
          </h3>
          <div className="space-y-2 text-sm text-muted-foreground">
            <div>
              <span className="ui-caption font-medium text-foreground">Thread key</span>
              <div className="mt-1 break-all font-mono text-detail text-muted-foreground">
                {thread.slack_thread_key}
              </div>
            </div>
          </div>
        </section>

        <section className="thread-surface-soft mt-4 rounded-xl px-3 py-3">
          <h3 className="ui-kicker mb-2 px-1 text-muted-foreground">
            Actions
          </h3>
          <div className="space-y-1">
            {actions.map((action) => (
              <button
                key={action.id}
                type="button"
                onClick={action.run}
                disabled={action.disabled}
                className={cn(
                  "thread-action-transition flex min-h-11 w-full items-center gap-3 rounded-lg px-3 py-3 text-left text-sm active:bg-accent",
                  action.tone === "destructive"
                    ? "text-destructive hover:bg-destructive/10"
                    : "text-foreground hover:bg-accent/70",
                  action.disabled && "opacity-60",
                )}
                data-touch-target
              >
                <action.icon
                  className={cn(
                    "size-5",
                    action.tone === "destructive" ? "" : "text-muted-foreground",
                  )}
                />
                {action.label}
              </button>
            ))}
          </div>
        </section>
      </div>
    </>
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
  mobileOnly = true,
}: ThreadInfoSheetProps) {
  const isDesktop = useMediaQuery("(min-width: 768px)");
  let slackUrl = "";
  if (thread.slack_thread_key.startsWith("slack:")) {
    try {
      const { channel, threadTs } = splitThreadKey(thread.slack_thread_key);
      slackUrl = `slack://app_redirect?channel=${encodeURIComponent(channel)}&thread_ts=${encodeURIComponent(threadTs)}`;
    } catch {
      // invalid key format — leave slackUrl empty
    }
  }

  function copyLink() {
    if (typeof window === "undefined") return;
    if (!navigator.clipboard?.writeText) return;
    const viewerUrl = `${window.location.origin}/${encodeURIComponent(
      thread.slack_thread_key,
    )}`;
    void navigator.clipboard
      .writeText(viewerUrl)
      .then(() => onClose())
      .catch(() => {});
  }

  const actions = buildThreadActionItems({
    canInterrupt: canStop,
    isRefreshing: false,
    compactMode: false,
    onRefresh: () => {
      onRefresh();
      onClose();
    },
    onStop: () => {
      onStop?.();
      onClose();
    },
    onCopyUrl: copyLink,
    onToggleCompact: () => {},
    onOpenSlack: slackUrl
      ? () => {
          window.open(slackUrl, "_blank");
        }
      : null,
    onOpenShortcuts: () => {},
  }).filter(
    (item) =>
      item.id === "refresh" ||
      (item.id === "stop" && canStop) ||
      item.id === "copy-url" ||
      item.id === "open-slack",
  );

  return (
    <ResponsivePanel
      open={open}
      side={isDesktop && !mobileOnly ? "right" : "bottom"}
      onClose={onClose}
      mobileOnly={mobileOnly}
      dismissibleByDrag={!isDesktop || mobileOnly}
      labelledBy="thread-info-title"
    >
      <div className="min-h-full">
        <ThreadInfoContent
          onClose={onClose}
          thread={thread}
          tokenUsage={tokenUsage}
          elapsed={elapsed}
          actions={actions}
          showHandle={!isDesktop || mobileOnly}
        />
        <div
          className="pointer-events-none h-[env(safe-area-inset-bottom)]"
          aria-hidden="true"
        />
      </div>
    </ResponsivePanel>
  );
}
