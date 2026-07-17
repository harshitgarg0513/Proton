import SectionCard from "./section-card";
import StatCard from "./stat-card";

interface QualitySummaryProps {
  report: Record<string, unknown>;
}

function formatMetric(value: unknown, suffix = "") {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  if (typeof value === "number") {
    return `${value}${suffix}`;
  }

  return `${value}${suffix}`;
}

function metricSubtitle(label: string, interpretation: string) {
  return `${label} · ${interpretation}`;
}

export default function QualitySummary({ report }: QualitySummaryProps) {
  const metrics = (report.quality_metrics ?? null) as Record<string, unknown> | null;
  const recommendation = (report.recommendation ?? null) as Record<string, unknown> | null;
  const strategy = (report.strategy ?? null) as Record<string, unknown> | null;

  const reasoning =
    recommendation?.reasoning ??
    strategy?.reasoning ??
    recommendation?.optimization_result;

  const hasQualityMetrics =
    metrics?.ssim !== undefined ||
    metrics?.psnr !== undefined ||
    metrics?.vmaf !== undefined;

  const profile = report.profile_used;
  const codec = report.codec_used ?? strategy?.codec ?? recommendation?.recommended_codec;

  return (
    <SectionCard title="Measured quality">
      <div className="space-y-4">
        {hasQualityMetrics ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {metrics?.ssim !== undefined && metrics?.ssim !== null ? (
              <StatCard
                title="SSIM"
                value={formatMetric(metrics.ssim)}
                subtitle={metricSubtitle(
                  "Structural similarity",
                  Number(metrics.ssim) >= 0.95 ? "visually near-identical" : "compression visible under scrutiny",
                )}
              />
            ) : null}
            {metrics?.psnr !== undefined && metrics?.psnr !== null ? (
              <StatCard
                title="PSNR"
                value={formatMetric(metrics.psnr, " dB")}
                subtitle={metricSubtitle(
                  "Signal-to-noise ratio",
                  Number(metrics.psnr) >= 35 ? "high fidelity" : "trade-off for smaller size",
                )}
              />
            ) : null}
            {metrics?.vmaf !== undefined && metrics?.vmaf !== null ? (
              <StatCard
                title="VMAF"
                value={formatMetric(metrics.vmaf)}
                subtitle={metricSubtitle(
                  "Netflix perceptual score",
                  Number(metrics.vmaf) >= 90 ? "excellent perceived quality" : "acceptable streaming quality",
                )}
              />
            ) : null}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            Objective quality metrics are not available for this media type.
          </p>
        )}

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard title="Profile used" value={formatMetric(profile)} />
          <StatCard title="Codec selected" value={formatMetric(codec)} />
          {strategy?.preset ? <StatCard title="Encoder preset" value={formatMetric(strategy.preset)} /> : null}
          {strategy?.crf !== undefined && strategy?.crf !== null ? (
            <StatCard title="CRF target" value={formatMetric(strategy.crf)} />
          ) : null}
          {recommendation?.target_bitrate ? (
            <StatCard title="Target bitrate" value={formatMetric(recommendation.target_bitrate)} />
          ) : null}
          {recommendation?.quality_estimate ? (
            <StatCard title="Quality estimate" value={formatMetric(recommendation.quality_estimate)} />
          ) : null}
        </div>

        {reasoning ? (
          <div className="rounded-xl border border-foreground/10 bg-foreground/[0.03] p-4">
            <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
              Why this codec & profile
            </p>
            <p className="mt-2 text-sm leading-6 text-foreground">{String(reasoning)}</p>
          </div>
        ) : null}
      </div>
    </SectionCard>
  );
}
