"use client";

import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { LoaderCircle, Send, Square } from "lucide-react";
import type { ThreadState } from "@/lib/types";

type ComposerMode = "reply" | "execute";

type MessageInputProps = {
  mode: ComposerMode;
  state: ThreadState;
  isAgentRunning: boolean;
  canSend?: boolean;
  blockedReason?: string;
  onSend: (message: string) => Promise<boolean>;
  onStop: () => Promise<boolean>;
};

const MAX_ROWS = 6;

export function MessageInput({
  mode,
  state,
  isAgentRunning,
  canSend = true,
  blockedReason,
  onSend,
  onStop,
}: MessageInputProps) {
  const [value, setValue] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const isComposingRef = useRef(false);
  const inputId = useId();
  const hintId = `${inputId}-hint`;

  const trimmedValue = value.trim();
  const hasText = trimmedValue.length > 0;
  const isStopMode = isAgentRunning && !hasText && !isSubmitting;

  const placeholder = useMemo(() => {
    if (isSubmitting) return "Sending...";
    if (isStopMode) return "Agent is working...";
    if (!canSend) return "Engineer is working...";
    if (mode === "reply") return "Reply to engineer...";
    if (state === "error") return "Restart with new message...";
    return "Send a message...";
  }, [canSend, isStopMode, isSubmitting, mode, state]);

  const announce = useCallback((message: string) => {
    setAnnouncement("");
    window.setTimeout(() => {
      setAnnouncement(message);
    }, 0);
  }, []);

  const resizeTextarea = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    textarea.style.height = "0px";
    const styles = window.getComputedStyle(textarea);
    const lineHeight = Number.parseFloat(styles.lineHeight) || 20;
    const paddingTop = Number.parseFloat(styles.paddingTop) || 0;
    const paddingBottom = Number.parseFloat(styles.paddingBottom) || 0;
    const maxHeight = lineHeight * MAX_ROWS + paddingTop + paddingBottom;
    const nextHeight = Math.min(textarea.scrollHeight, maxHeight);

    textarea.style.height = `${nextHeight}px`;
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? "auto" : "hidden";
  }, []);

  useLayoutEffect(() => {
    resizeTextarea();
  }, [resizeTextarea, value]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea || typeof ResizeObserver === "undefined") return;

    const observer = new ResizeObserver(() => {
      resizeTextarea();
    });
    observer.observe(textarea);
    return () => observer.disconnect();
  }, [resizeTextarea]);

  useEffect(() => {
    setError(null);
  }, [mode, state]);

  const submitMessage = useCallback(async () => {
    if (isSubmitting || !hasText) return;
    if (!canSend) {
      setError(blockedReason ?? "Sending is currently unavailable.");
      return;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      const didSend = await onSend(trimmedValue);
      if (!didSend) return;
      setValue("");
      announce("Message sent");
      textareaRef.current?.focus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message.");
    } finally {
      setIsSubmitting(false);
    }
  }, [announce, blockedReason, canSend, hasText, isSubmitting, onSend, trimmedValue]);

  const stopRun = useCallback(async () => {
    if (isSubmitting) return;
    setError(null);
    setIsSubmitting(true);
    try {
      const didStop = await onStop();
      if (!didStop) return;
      announce("Run stopped");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to stop run.");
    } finally {
      setIsSubmitting(false);
    }
  }, [announce, isSubmitting, onStop]);

  const handleSubmit = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (isStopMode) {
        await stopRun();
        return;
      }
      await submitMessage();
    },
    [isStopMode, stopRun, submitMessage],
  );

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key !== "Enter") return;
      const nativeEvent = event.nativeEvent as KeyboardEvent & { keyCode?: number };
      const isComposing = nativeEvent.isComposing || nativeEvent.keyCode === 229 || isComposingRef.current;
      if (isComposing) return;

      const isDesktop = window.matchMedia("(min-width: 768px)").matches;
      const isShortcutSend = event.metaKey || event.ctrlKey;
      const isDesktopEnterSend = isDesktop && !event.shiftKey;
      if (!isShortcutSend && !isDesktopEnterSend) return;

      event.preventDefault();
      if (isStopMode) {
        void stopRun();
        return;
      }
      void submitMessage();
    },
    [isStopMode, stopRun, submitMessage],
  );

  return (
    <form
      onSubmit={handleSubmit}
      aria-label="Message composer"
      className="mt-3 flex flex-col gap-2 bg-card border border-border rounded-sm p-2 pb-[max(0.5rem,env(safe-area-inset-bottom))]"
    >
      {error ? (
        <p className="px-2 text-xs text-destructive" aria-live="polite">
          {error}
        </p>
      ) : null}
      <div className="flex gap-2 items-end">
        <label htmlFor={inputId} className="sr-only">
          Message
        </label>
        <textarea
          ref={textareaRef}
          id={inputId}
          name="message"
          rows={1}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          onCompositionStart={() => {
            isComposingRef.current = true;
          }}
          onCompositionEnd={() => {
            isComposingRef.current = false;
          }}
          placeholder={placeholder}
          disabled={isSubmitting}
          autoComplete="off"
          aria-describedby={hintId}
          className="flex-1 resize-none [field-sizing:content] bg-background text-base md:text-sm text-foreground placeholder:text-muted-foreground px-3 py-2 min-h-11 disabled:opacity-60 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring rounded-sm border border-input"
        />
        <button
          type={isStopMode ? "button" : "submit"}
          onClick={isStopMode ? () => void stopRun() : undefined}
          disabled={isSubmitting || (!isStopMode && (!hasText || !canSend))}
          aria-label={isStopMode ? "Stop generating" : "Send message"}
          className="inline-flex min-h-11 min-w-11 items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium text-primary-foreground bg-primary hover:opacity-90 rounded-sm disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer shrink-0"
        >
          {isSubmitting ? (
            <LoaderCircle className="size-4 animate-spin" />
          ) : isStopMode ? (
            <Square className="size-3.5 fill-current" />
          ) : (
            <Send className="size-3.5" />
          )}
        </button>
      </div>
      <p id={hintId} className="sr-only">
        Press Enter to send on desktop, or Command/Ctrl plus Enter on any device. Shift plus Enter
        inserts a new line.
      </p>
      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        {announcement}
      </div>
    </form>
  );
}
