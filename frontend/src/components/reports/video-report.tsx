import QualitySummary from "./shared/quality-summary";
import SectionCard from "./shared/section-card";
import StatCard from "./shared/stat-card";

interface VideoReportProps {
  report: Record<string, unknown>;
}

function formatBytes(value: unknown) {
  if (typeof value !== "number") {
    return "-";
  }

  if (value >= 1024 * 1024) {
    return `${(value / (1024 * 1024)).toFixed(2)} MB`;
  }

  if (value >= 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }

  return `${value} B`;
}

export default function VideoReport({ report }: VideoReportProps) {
  if (!report) {
    return null;
  }

  const analysis = (report.analysis ?? {}) as Record<string, unknown>;
  const recommendation = (report.recommendation ?? {}) as Record<string, unknown>;
  const chunkPlan = (report.chunk_plan ?? null) as Record<string, unknown> | null;
  const benchmarkResults = (report.benchmark_results ?? []) as Array<Record<string, unknown>>;

  return (
    <div className="space-y-6">
      <QualitySummary report={report} />

      <SectionCard title="Compression outcome">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard title="Original size" value={formatBytes(report.original_size)} />
          <StatCard title="Optimized size" value={formatBytes(report.optimized_size)} />
          <StatCard title="Size reduction" value={`${report.compression_ratio ?? 0}%`} />
          <StatCard title="Processing time" value={`${report.processing_time ?? "-"}s`} />
          <StatCard title="Resolution" value={`${analysis.width ?? "-"} × ${analysis.height ?? "-"}`} />
          <StatCard title="Duration" value={`${analysis.duration ?? "-"}s`} />
          <StatCard title="FPS" value={String(analysis.fps ?? "-")} />
          <StatCard title="Motion intensity" value={String(analysis.motion_intensity ?? "-")} />
        </div>
      </SectionCard>

      {chunkPlan ? (
        <SectionCard title="Chunking plan">
          <div className="grid gap-3 sm:grid-cols-3">
            <StatCard title="Chunk count" value={String(chunkPlan.chunk_count ?? "-")} />
            <StatCard title="Chunk length" value={`${chunkPlan.chunk_length_seconds ?? "-"}s`} />
            <StatCard
              title="Parallelism"
              value={
                Number(chunkPlan.chunk_count ?? 0) > 1
                  ? `${chunkPlan.chunk_count} concurrent workers`
                  : "Single-pass encode"
              }
            />
          </div>
        </SectionCard>
      ) : null}

      {benchmarkResults.length > 0 ? (
        <SectionCard title="Codec benchmark">
          <div className="space-y-2">
            {benchmarkResults.slice(0, 5).map((result, index) => (
              <div
                key={`${result.codec}-${index}`}
                className="flex items-center justify-between rounded-lg border border-border/70 px-3 py-2 text-sm"
              >
                <span className="font-medium text-foreground">{String(result.codec ?? "codec")}</span>
                <span className="text-muted-foreground">
                  {formatBytes(result.size)} · {String(result.duration ?? "-")}s
                </span>
              </div>
            ))}
          </div>
        </SectionCard>
      ) : null}

      {Object.keys(recommendation).length > 0 ? (
        <SectionCard title="Optimization decision">
          <div className="space-y-2 text-sm">
            {Object.entries(recommendation).map(([key, value]) => (
              <div key={key} className="flex justify-between gap-4 border-b border-border/60 pb-2">
                <span className="font-medium capitalize text-foreground">{key.replaceAll("_", " ")}</span>
                <span className="text-right text-muted-foreground">{String(value)}</span>
              </div>
            ))}
          </div>
        </SectionCard>
      ) : null}
    </div>
  );
}
