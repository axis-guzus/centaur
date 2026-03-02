"use client";

export default function ThreadsError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex h-full min-h-0 items-center justify-center bg-background px-4">
      <div className="text-center" role="alert" aria-live="assertive">
        <p className="mb-3 text-sm text-destructive">Something went wrong</p>
        <p className="mb-4 max-w-sm text-xs text-muted-foreground">{error.message}</p>
        <button
          onClick={reset}
          className="cursor-pointer rounded-sm border border-border bg-transparent px-3 py-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
