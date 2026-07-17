import QualitySummary from "./shared/quality-summary";
import SectionCard from "./shared/section-card";
import StatCard from "./shared/stat-card";

interface Props {
  report: Record<string, unknown>;
}

export default function AudioReport({ report }: Props) {
  if (!report) return null;

  return (
    <div className="space-y-6">
      <QualitySummary report={report} />

      <SectionCard title="Audio Summary">
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard title="Original Size" value={String(report.original_size ?? "-")} />
          <StatCard title="Optimized Size" value={String(report.optimized_size ?? "-")} />
          <StatCard title="Compression" value={`${String(report.compression_ratio ?? 0)}%`} />
          <StatCard title="Processing Time" value={`${String(report.processing_time ?? 0)}s`} />
        </div>
      </SectionCard>

      <SectionCard title="Recommendation">
        <div className="space-y-2 text-sm">
          {Object.entries((report.recommendation ?? {}) as Record<string, unknown>).map(([key, value]) => (
            <div key={key} className="flex justify-between border-b pb-1">
              <span className="font-medium">{key}</span>
              <span>{String(value)}</span>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="Analysis">
        <div className="space-y-2 text-sm">
          {Object.entries((report.analysis ?? {}) as Record<string, unknown>).map(([key, value]) => (
            <div key={key} className="flex justify-between border-b pb-1">
              <span className="font-medium">{key}</span>
              <span>{String(value)}</span>
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}
