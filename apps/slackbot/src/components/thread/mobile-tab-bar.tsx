"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { LayoutList, Zap } from "lucide-react";
import { cn } from "@/lib/utils";

type MobileTabBarProps = {
  activeThreadHref?: string;
  hasRunningAgent?: boolean;
  hasError?: boolean;
};

export function MobileTabBar({ activeThreadHref, hasRunningAgent, hasError }: MobileTabBarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [keyboardOpen, setKeyboardOpen] = useState(false);

  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    const check = () => setKeyboardOpen(vv.height < window.innerHeight * 0.75);
    vv.addEventListener("resize", check);
    return () => vv.removeEventListener("resize", check);
  }, []);

  const isThreads = pathname === "/";
  const isActive = pathname.length > 1 && !pathname.startsWith("/api/");

  function scrollCurrentViewToTop() {
    if (isThreads) {
      const list = document.querySelector<HTMLElement>("[data-thread-list-scroll='true']");
      if (list) {
        list.scrollTo({ top: 0, behavior: "smooth" });
        return;
      }
    }
    if (isActive) {
      const feed = document.querySelector<HTMLElement>("[data-thread-feed-scroll='true']");
      if (feed) {
        feed.scrollTo({ top: 0, behavior: "smooth" });
        return;
      }
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function handleThreadsTab() {
    if (isThreads) {
      scrollCurrentViewToTop();
      return;
    }
    router.push("/", { scroll: false });
  }

  function handleActiveTab() {
    if (isActive) {
      scrollCurrentViewToTop();
      return;
    }
    if (activeThreadHref) {
      router.push(activeThreadHref, { scroll: false });
    } else {
      router.push("/", { scroll: false });
    }
  }

  return (
    <div
      className={cn(
        "md:hidden flex-shrink-0 flex items-center justify-around border-t border-border bg-background/95 backdrop-blur-xl",
        keyboardOpen && "hidden",
      )}
      role="tablist"
      aria-label="Navigation"
    >
      <button
        type="button"
        role="tab"
        aria-selected={isThreads}
        onClick={handleThreadsTab}
        className={cn(
          "flex flex-col items-center justify-center gap-0.5 py-2 min-w-[64px] relative",
          isThreads ? "text-primary" : "text-muted-foreground",
        )}
      >
        {hasError && !isThreads && (
          <span className="absolute top-1.5 right-3 size-1.5 rounded-full bg-destructive" />
        )}
        <LayoutList className="size-5" />
        <span className="text-[10px] font-medium">Threads</span>
      </button>

      <button
        type="button"
        role="tab"
        aria-selected={isActive}
        onClick={handleActiveTab}
        className={cn(
          "flex flex-col items-center justify-center gap-0.5 py-2 min-w-[64px] relative",
          isActive ? "text-primary" : "text-muted-foreground",
        )}
      >
        {hasRunningAgent && (
          <span className="absolute top-1.5 right-3 size-2 rounded-full bg-green-500 animate-pulse" />
        )}
        <Zap className="size-5" />
        <span className="text-[10px] font-medium">Active</span>
      </button>
    </div>
  );
}
