import QualitySummary from "./shared/quality-summary";
import SectionCard from "./shared/section-card";
import StatCard from "./shared/stat-card";

interface ImageReportProps {
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

export default function ImageReport({ report }: ImageReportProps) {
  if (!report) {
    return null;
  }

  const analysis = (report.analysis ?? {}) as Record<string, unknown>;
  const recommendation = (report.recommendation ?? {}) as Record<string, unknown>;

  return (
    <div className="space-y-6">
      <QualitySummary report={report} />

      <SectionCard title="Compression outcome">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard title="Original size" value={formatBytes(report.original_size)} />
          <StatCard title="Optimized size" value={formatBytes(report.optimized_size)} />
          <StatCard title="Size reduction" value={`${report.compression_ratio ?? 0}%`} />
          <StatCard title="Processing time" value={`${report.processing_time ?? "-"}s`} />
          <StatCard title="Format before" value={String(report.format_before ?? "-")} />
          <StatCard title="Format after" value={String(report.format_after ?? "-")} />
        </div>
      </SectionCard>

      <SectionCard title="Image analysis">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <StatCard title="Dimensions" value={`${analysis.width ?? "-"} × ${analysis.height ?? "-"}`} />
          <StatCard title="Entropy" value={String(analysis.entropy ?? "-")} />
          <StatCard title="Edge density" value={String(analysis.edge_density ?? "-")} />
          <StatCard title="Color complexity" value={String(analysis.color_complexity ?? "-")} />
        </div>
      </SectionCard>

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
