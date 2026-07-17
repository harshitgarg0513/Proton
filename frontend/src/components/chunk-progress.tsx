"use client";

import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

export type ChunkJobItem = {
  id: number;
  chunk_index: number | null;
  status: string;
  progress: number;
};

interface ChunkProgressProps {
  chunkJobs: ChunkJobItem[];
  totalChunks: number;
  completedChunks: number;
  chunkLengthSeconds?: number | null;
}

function chunkStatusTone(status: string) {
  switch (status.toLowerCase()) {
    case "completed":
      return "text-emerald-700";
    case "failed":
      return "text-rose-700";
    case "processing":
      return "text-blue-700";
    default:
      return "text-muted-foreground";
  }
}

function chunkProgressValue(status: string, progress: number) {
  if (status.toLowerCase() === "completed") {
    return 100;
  }

  if (status.toLowerCase() === "failed") {
    return progress || 100;
  }

  return progress;
}

export function ChunkProgress({
  chunkJobs,
  totalChunks,
  completedChunks,
  chunkLengthSeconds,
}: ChunkProgressProps) {
  if (totalChunks <= 1) {
    return null;
  }

  const rows: ChunkJobItem[] =
    chunkJobs.length > 0
      ? [...chunkJobs].sort((left, right) => (left.chunk_index ?? 0) - (right.chunk_index ?? 0))
      : Array.from({ length: totalChunks }, (_, index) => ({
          id: index,
          chunk_index: index,
          status: index < completedChunks ? "COMPLETED" : "PENDING",
          progress: index < completedChunks ? 100 : 0,
        }));

  return (
    <div className="space-y-3 rounded-xl border border-border bg-muted/20 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-foreground">Parallel chunk workers</p>
          <p className="text-xs text-muted-foreground">
            {completedChunks}/{totalChunks} chunks complete
            {chunkLengthSeconds ? ` · ~${chunkLengthSeconds}s each` : ""}
          </p>
        </div>
        <span className="rounded-full bg-blue-500/10 px-2.5 py-1 text-xs font-medium text-blue-700">
          {totalChunks} workers
        </span>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        {rows.map((chunk) => {
          const index = (chunk.chunk_index ?? 0) + 1;
          const value = chunkProgressValue(chunk.status, chunk.progress);

          return (
            <div key={chunk.id} className="rounded-lg border border-border/70 bg-background px-3 py-2">
              <div className="mb-1.5 flex items-center justify-between gap-2 text-xs">
                <span className="font-medium text-foreground">Chunk {index}</span>
                <span className={cn("font-medium capitalize", chunkStatusTone(chunk.status))}>
                  {chunk.status.toLowerCase()}
                </span>
              </div>
              <Progress value={value} className="h-1.5" />
            </div>
          );
        })}
      </div>
    </div>
  );
}
