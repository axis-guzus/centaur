"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Search, X } from "lucide-react";
import { HarnessBadge } from "@/components/ui/harness-badge";
import { StateDot } from "@/components/ui/state-dot";
import { cn } from "@/lib/utils";
import type { ThreadSummary } from "@/lib/types";
import { threadName as fallbackName } from "@/lib/thread-name";
import { timeAgo } from "@/lib/format";

type ThreadSidebarDrawerProps = {
  open: boolean;
  onClose: () => void;
  threads: ThreadSummary[];
  activeKey?: string;
};

function getFocusableElements(container: HTMLElement): HTMLElement[] {
  const candidates = container.querySelectorAll<HTMLElement>(
    "a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex='-1'])",
  );
  return Array.from(candidates).filter((el) => !el.hasAttribute("disabled") && el.tabIndex >= 0);
}

export function ThreadSidebarDrawer({ open, onClose, threads, activeKey }: ThreadSidebarDrawerProps) {
  const [query, setQuery] = useState("");
  const drawerRef = useRef<HTMLDivElement>(null);
  const dragStartXRef = useRef<number | null>(null);
  const [dragX, setDragX] = useState(0);

  const filtered = threads.filter((t) => {
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    const hay = `${t.thread_name ?? ""} ${t.first_message ?? ""} ${t.slack_thread_key}`.toLowerCase();
    return hay.includes(q);
  });

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    dragStartXRef.current = e.touches[0].clientX;
  }, []);

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (dragStartXRef.current === null) return;
    const delta = dragStartXRef.current - e.touches[0].clientX;
    if (delta > 0) setDragX(delta);
  }, []);

  const handleTouchEnd = useCallback(() => {
    if (dragX > 80) {
      onClose();
      if (history.state?.drawer) history.back();
    }
    setDragX(0);
    dragStartXRef.current = null;
  }, [dragX, onClose]);

  const closeDrawer = useCallback(() => {
    onClose();
    if (history.state?.drawer) history.back();
  }, [onClose]);

  function handleSelectThread() {
    closeDrawer();
  }

  const handleBackdropClose = () => {
    closeDrawer();
  };

  useEffect(() => {
    if (!open) {
      setQuery("");
      setDragX(0);
      return;
    }

    const drawer = drawerRef.current;
    const previousFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (drawer) {
      const focusable = getFocusableElements(drawer);
      (focusable[0] ?? drawer).focus();
    }

    history.pushState({ drawer: true }, "");
    const onPop = () => onClose();
    window.addEventListener("popstate", onPop);

    const onKey = (e: KeyboardEvent) => {
      if (!drawer) return;
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        closeDrawer();
        return;
      }
      if (e.key !== "Tab") return;
      const focusable = getFocusableElements(drawer);
      if (focusable.length === 0) {
        e.preventDefault();
        drawer.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (e.shiftKey) {
        if (active === first || !drawer.contains(active)) {
          e.preventDefault();
          last.focus();
        }
      } else if (active === last || !drawer.contains(active)) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);

    return () => {
      window.removeEventListener("popstate", onPop);
      document.removeEventListener("keydown", onKey);
      previousFocused?.focus();
    };
  }, [closeDrawer, onClose, open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 md:hidden" aria-modal="true" role="dialog" aria-label="Thread list">
      <div className="absolute inset-0 bg-black/40" onClick={handleBackdropClose} />
      <div
        ref={drawerRef}
        tabIndex={-1}
        className="absolute inset-y-0 left-0 bg-background border-r border-border shadow-2xl overflow-y-auto animate-in slide-in-from-left duration-250"
        style={{
          width: "min(300px, 85vw)",
          transform: dragX > 0 ? `translateX(-${dragX}px)` : undefined,
        }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        <div className="sticky top-0 z-10 bg-background p-3 border-b border-border">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter threads\u2026"
              className="w-full bg-secondary/50 border border-border/50 rounded-lg pl-9 pr-8 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              autoFocus
            />
            {query && (
              <button
                type="button"
                onClick={() => setQuery("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 size-6 flex items-center justify-center rounded text-muted-foreground"
                aria-label="Clear search"
              >
                <X className="size-3.5" />
              </button>
            )}
          </div>
        </div>

        <div className="p-2 space-y-1">
          {filtered.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-8">No threads found</p>
          )}
          {filtered.map((t) => {
            const name = t.thread_name || fallbackName(t.slack_thread_key);
            const href = `/${encodeURIComponent(t.slack_thread_key)}`;
            const isSelected = t.slack_thread_key === activeKey;
            const isRunning = t.state === "running" || t.state === "working";

            return (
              <Link
                key={t.slack_thread_key}
                href={href}
                onClick={handleSelectThread}
                className={cn(
                  "block rounded-lg p-3 no-underline text-inherit transition-colors",
                  isSelected ? "bg-accent border-l-2 border-l-primary" : "active:bg-accent/50",
                  isRunning && !isSelected && "border-l-2 border-l-green-500",
                  t.state === "error" && !isSelected && "border-l-2 border-l-destructive",
                )}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <HarnessBadge harness={t.harness} />
                  <span className="text-sm font-medium truncate flex-1 min-w-0">{name}</span>
                  <StateDot state={t.state} />
                </div>
                <div className="flex items-center gap-1.5 mt-1 text-[11px] text-muted-foreground">
                  <span>{t.state}</span>
                  <span>·</span>
                  <span>{t.turn_count}t</span>
                  <span>·</span>
                  <span>{timeAgo(t.last_activity)}</span>
                </div>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}
