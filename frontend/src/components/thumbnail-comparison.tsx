"use client";

import { useCallback, useRef, useState } from "react";

import { cn } from "@/lib/utils";

type ViewMode = "compare" | "before" | "after";

interface ThumbnailComparisonProps {
  beforeUrl: string;
  afterUrl: string;
  beforeLabel?: string;
  afterLabel?: string;
  className?: string;
}

export function ThumbnailComparison({
  beforeUrl,
  afterUrl,
  beforeLabel = "Original",
  afterLabel = "Optimized",
  className,
}: ThumbnailComparisonProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState(50);
  const [viewMode, setViewMode] = useState<ViewMode>("compare");
  const [isDragging, setIsDragging] = useState(false);

  const updatePosition = useCallback((clientX: number) => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    const rect = container.getBoundingClientRect();
    const next = ((clientX - rect.left) / rect.width) * 100;
    setPosition(Math.min(100, Math.max(0, next)));
  }, []);

  function handlePointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if (viewMode !== "compare") {
      return;
    }

    setIsDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
    updatePosition(event.clientX);
  }

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!isDragging || viewMode !== "compare") {
      return;
    }

    updatePosition(event.clientX);
  }

  function handlePointerUp(event: React.PointerEvent<HTMLDivElement>) {
    if (!isDragging) {
      return;
    }

    setIsDragging(false);
    event.currentTarget.releasePointerCapture(event.pointerId);
  }

  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium text-foreground">Before / after preview</p>
        <div className="inline-flex rounded-lg border border-border bg-muted/40 p-0.5 text-xs">
          {(["compare", "before", "after"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setViewMode(mode)}
              className={cn(
                "rounded-md px-2.5 py-1 font-medium capitalize transition-colors",
                viewMode === mode
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {mode === "compare" ? "Slider" : mode}
            </button>
          ))}
        </div>
      </div>

      <div
        ref={containerRef}
        className={cn(
          "relative aspect-video overflow-hidden rounded-2xl border border-border bg-muted/30",
          viewMode === "compare" && "cursor-ew-resize select-none touch-none",
        )}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        {viewMode === "before" ? (
          <img src={beforeUrl} alt={beforeLabel} className="h-full w-full object-contain" />
        ) : viewMode === "after" ? (
          <img src={afterUrl} alt={afterLabel} className="h-full w-full object-contain" />
        ) : (
          <>
            <img src={afterUrl} alt={afterLabel} className="absolute inset-0 h-full w-full object-contain" />
            <div className="absolute inset-y-0 left-0 overflow-hidden" style={{ width: `${position}%` }}>
              <img
                src={beforeUrl}
                alt={beforeLabel}
                className="h-full max-w-none object-contain"
                style={{ width: `${10000 / Math.max(position, 1)}%` }}
              />
            </div>
            <div
              className="pointer-events-none absolute inset-y-0 w-0.5 -translate-x-1/2 bg-white shadow-[0_0_0_1px_rgba(0,0,0,0.35)]"
              style={{ left: `${position}%` }}
            >
              <div className="absolute left-1/2 top-1/2 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-background text-xs font-semibold shadow-sm">
                ↔
              </div>
            </div>
          </>
        )}

        <span className="pointer-events-none absolute left-3 top-3 rounded-full bg-black/55 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-white">
          {viewMode === "after" ? afterLabel : beforeLabel}
        </span>
        {viewMode === "compare" ? (
          <span className="pointer-events-none absolute right-3 top-3 rounded-full bg-black/55 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-white">
            {afterLabel}
          </span>
        ) : null}
      </div>
    </div>
  );
}
