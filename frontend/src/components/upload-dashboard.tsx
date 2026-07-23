"use client";

import axios from "axios";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertCircle,
  Atom,
  CheckCircle2,
  Clock3,
  CloudUpload,
  ExternalLink,
  FileText,
  Gauge,
  Layers,
  Loader2,
  Sparkles,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useDropzone } from "react-dropzone";
import { motion } from "framer-motion";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import AudioReport from "@/components/reports/audio-report";
import PdfReport from "@/components/reports/pdf-report";
import ImageReport from "@/components/reports/image-report";
import VideoReport from "@/components/reports/video-report";
import { ChunkProgress } from "@/components/chunk-progress";
import { ThumbnailComparison } from "@/components/thumbnail-comparison";

type JobItem = {
  id: number;
  file_id: number;
  parent_job_id: number | null;
  chunk_index: number | null;
  job_type: string;
  profile: string;
  status: string;
  progress: number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  processing_duration: number | null;
  output_storage_path: string | null;
  report_data: Record<string, unknown> | null;
};

type UploadResponse = {
  file: {
    id: number;
    filename: string;
    original_size: number;
    mime_type: string;
    storage_path: string;
    upload_status: string;
    created_at: string;
  };
  job: JobItem;
};

const rawApiUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
const apiBaseUrl = rawApiUrl && rawApiUrl.trim() !== "" ? rawApiUrl : "https://proton-backend-dn83.onrender.com";
const minioBrowserBaseUrl =
  process.env.NEXT_PUBLIC_MINIO_BROWSER_BASE_URL ?? "http://localhost:9001/browser/uploads";
const apiKey = process.env.NEXT_PUBLIC_DEMO_API_KEY ?? "demo-api-key-12345678";

const optimizationProfiles = ["smallest_size", "balanced", "best_quality", "web_optimized"] as const;
type OptimizationProfile = (typeof optimizationProfiles)[number];
const ORIGINAL_PATHS_STORAGE_KEY = "acp.jobOriginalPaths";

function readStoredOriginalPaths(): Record<number, string> {
  if (typeof window === "undefined") {
    return {};
  }

  try {
    return JSON.parse(window.sessionStorage.getItem(ORIGINAL_PATHS_STORAGE_KEY) ?? "{}") as Record<
      number,
      string
    >;
  } catch {
    return {};
  }
}

function storeOriginalPath(jobId: number, storagePath: string) {
  if (typeof window === "undefined") {
    return;
  }

  const nextPaths = {
    ...readStoredOriginalPaths(),
    [jobId]: storagePath,
  };
  window.sessionStorage.setItem(ORIGINAL_PATHS_STORAGE_KEY, JSON.stringify(nextPaths));
}

function formatBytes(bytes: number) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }

  const units = ["KB", "MB", "GB"];
  let size = bytes / 1024;
  let unitIndex = 0;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }

  return `${size.toFixed(size >= 10 ? 0 : 1)} ${units[unitIndex]}`;
}

function statusTone(status: string) {
  switch (status.toLowerCase()) {
    case "completed":
      return "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/25";
    case "failed":
      return "bg-rose-500/15 text-rose-300 ring-1 ring-rose-500/25";
    case "processing":
      return "bg-primary/15 text-primary ring-1 ring-primary/25";
    case "retrying":
    case "pending":
      return "bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/25";
    default:
      return "bg-muted text-muted-foreground ring-1 ring-border";
  }
}

function formatDuration(seconds: number | null) {
  if (seconds === null || Number.isNaN(seconds)) {
    return "-";
  }

  if (seconds < 60) {
    return `${seconds.toFixed(1)}s`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  return `${minutes}m ${remainingSeconds}s`;
}

function formatAnalyticsValue(value: unknown) {
  if (typeof value === "number") {
    if (value >= 1024 * 1024) {
      return `${(value / (1024 * 1024)).toFixed(2)} MB`;
    }

    if (value >= 1024) {
      return `${(value / 1024).toFixed(1)} KB`;
    }

    return `${value} B`;
  }

  if (typeof value === "string") {
    return value;
  }

  if (value === null || value === undefined) {
    return "-";
  }

  return String(value);
}

function formatPercent(value: unknown) {
  if (typeof value === "number") {
    return `${value.toFixed(2)}%`;
  }

  if (typeof value === "string" && value.length > 0) {
    return value.endsWith("%") ? value : `${value}%`;
  }

  return "-";
}

function minioObjectUrl(storagePath: string) {
  return `${minioBrowserBaseUrl}/${storagePath}`;
}

function isTerminalJobStatus(status: string) {
  const normalized = status.toLowerCase();
  return normalized === "completed" || normalized === "failed";
}

export function UploadDashboard() {
  const queryClient = useQueryClient();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadState, setUploadState] = useState<"idle" | "uploading" | "done" | "error">(
    "idle",
  );
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [selectedProfile, setSelectedProfile] = useState<OptimizationProfile>("balanced");
  const [originalPathsByJobId, setOriginalPathsByJobId] = useState<Record<number, string>>(
    readStoredOriginalPaths,
  );

  const jobsQuery = useQuery({
    queryKey: ["jobs"],
    queryFn: async () => {
      const response = await axios.get<JobItem[]>(`${apiBaseUrl}/api/jobs`, {
        headers: { 'X-API-Key': apiKey },
      });
      return response.data;
    },
    retry: false,
    staleTime: 30_000,
  });

  const jobs = jobsQuery.data ?? [];

  useEffect(() => {
    if (selectedJobId === null && jobs.length > 0) {
      setSelectedJobId(jobs[0].id);
    }
  }, [jobs, selectedJobId]);

  const selectedJobQuery = useQuery({
    queryKey: ["job", selectedJobId],
    queryFn: async () => {
      const response = await axios.get<JobItem>(`${apiBaseUrl}/api/jobs/${selectedJobId}`, {
        headers: { 'X-API-Key': apiKey },
      });
      return response.data;
    },
    enabled: selectedJobId !== null,
    retry: false,
  });

  useEffect(() => {
    if (selectedJobId === null) {
      return;
    }

    const cachedJob = queryClient.getQueryData<JobItem>(["job", selectedJobId]);
    const listJob = queryClient
      .getQueryData<JobItem[]>(["jobs"])
      ?.find((job) => job.id === selectedJobId);
    const knownJob = cachedJob ?? listJob;
    if (knownJob && isTerminalJobStatus(knownJob.status)) {
      return;
    }

    const source = new EventSource(`${apiBaseUrl}/api/jobs/${selectedJobId}/stream?api_key=${apiKey}`);

    function applyJobUpdate(updated: JobItem) {
      queryClient.setQueryData(["job", selectedJobId], updated);
      queryClient.setQueryData<JobItem[]>(["jobs"], (currentJobs) =>
        currentJobs?.map((job) => (job.id === updated.id ? updated : job)) ?? currentJobs,
      );

      if (updated.report_data?.chunked) {
        void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      }
    }

    source.addEventListener("job", (event) => {
      applyJobUpdate(JSON.parse(event.data) as JobItem);
    });

    source.addEventListener("done", () => {
      source.close();
    });

    source.addEventListener("error", () => {
      source.close();
    });

    return () => {
      source.close();
    };
  }, [queryClient, selectedJobId]);

  const selectedJob =
    selectedJobQuery.data ??
    jobs.find((job) => job.id === selectedJobId) ??
    null;

  const selectedReport =
    (selectedJob?.report_data ?? null) as Record<string, unknown> | null;

  const analysisReport =
    (selectedReport?.analysis ?? null) as Record<string, unknown> | null;

  const mediaType =
    String(selectedReport?.media_type ?? "").toLowerCase() ||
    (String(selectedReport?.format_before ?? "").toLowerCase() === "pdf"
      ? "pdf"
      : analysisReport?.duration !== undefined
        ? "video"
        : "image");

  const chunkJobs = useMemo(
    () =>
      jobs
        .filter(
          (job) =>
            job.parent_job_id === selectedJobId &&
            job.job_type === "compression_chunk",
        )
        .map((job) => ({
          id: job.id,
          chunk_index: job.chunk_index,
          status: job.status,
          progress: job.progress,
        })),
    [jobs, selectedJobId],
  );

  const chunkJobsTotal =
    typeof selectedJob?.report_data?.chunk_jobs_total === "number"
      ? selectedJob.report_data.chunk_jobs_total
      : typeof selectedReport?.chunk_count === "number"
        ? selectedReport.chunk_count
        : 0;

  const chunkJobsCompleted =
    typeof selectedJob?.report_data?.chunk_jobs_completed === "number"
      ? selectedJob.report_data.chunk_jobs_completed
      : 0;

  const chunkLengthSeconds =
    typeof selectedReport?.chunk_plan === "object" &&
    selectedReport?.chunk_plan !== null &&
    "chunk_length_seconds" in selectedReport.chunk_plan
      ? Number((selectedReport.chunk_plan as Record<string, unknown>).chunk_length_seconds)
      : null;

  const comparisonPreview = useMemo(() => {
    if (!selectedJob || !selectedReport) {
      return null;
    }

    const thumbnailPath = selectedReport.thumbnail_storage_path;
    const optimizedPath = selectedReport.optimized_storage_path;
    const originalPath = originalPathsByJobId[selectedJob.id];

    const originalUrl =
      typeof originalPath === "string" && originalPath.length > 0
        ? minioObjectUrl(originalPath)
        : null;

    const optimizedUrl =
      typeof thumbnailPath === "string" && thumbnailPath.length > 0
        ? minioObjectUrl(thumbnailPath)
        : typeof optimizedPath === "string" &&
            optimizedPath.length > 0 &&
            (mediaType === "image" || mediaType === "video")
          ? minioObjectUrl(optimizedPath)
          : null;

    if (!originalUrl || !optimizedUrl || originalUrl === optimizedUrl) {
      return null;
    }

    return { originalUrl, optimizedUrl };
  }, [mediaType, originalPathsByJobId, selectedJob, selectedReport]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    multiple: false,
    onDrop: (acceptedFiles) => {
      const nextFile = acceptedFiles[0] ?? null;
      setSelectedFile(nextFile);
      setUploadProgress(0);
      setUploadState("idle");
    },
  });

  const preview = useMemo(() => {
    if (!selectedFile) {
      return null;
    }

    return {
      name: selectedFile.name,
      size: formatBytes(selectedFile.size),
      type: selectedFile.type || "unknown type",
    };
  }, [selectedFile]);

  async function handleUpload() {
    if (!selectedFile) {
      return;
    }

    setUploadState("uploading");
    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("profile", selectedProfile);

      const response = await axios.post<UploadResponse>(`${apiBaseUrl}/api/files/upload`, formData, {
        headers: { 
          "X-API-Key": apiKey,
        },
        onUploadProgress: (event) => {
          if (!event.total) {
            return;
          }

          setUploadProgress(Math.round((event.loaded * 100) / event.total));
        },
      });

      setUploadState("done");
      setUploadProgress(100);
      setSelectedJobId(response.data.job.id);
      setSelectedFile(null);
      storeOriginalPath(response.data.job.id, response.data.file.storage_path);
      setOriginalPathsByJobId((currentPaths) => ({
        ...currentPaths,
        [response.data.job.id]: response.data.file.storage_path,
      }));
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
      return response.data;
    } catch {
      setUploadState("error");
    }
  }

  return (
    <div className="relative min-h-screen bg-background">
      <div className="proton-aurora pointer-events-none absolute inset-x-0 top-0 h-[420px]" />
      <div className="relative mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-10 px-4 py-10 md:px-8 lg:px-10">
        <header className="flex flex-col gap-8">
          <div className="flex flex-col items-start justify-between gap-6 md:flex-row md:items-center">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-lg shadow-primary/20 ring-1 ring-primary/30">
                <Atom className="h-6 w-6" />
              </div>
              <div className="leading-tight">
                <p className="text-lg font-semibold tracking-tight text-foreground">Proton</p>
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
                  Adaptive Compression
                </p>
              </div>
            </div>
            <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card/60 px-3.5 py-1.5 text-xs font-medium text-muted-foreground backdrop-blur">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400/70" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
              </span>
              Live worker stream
            </div>
          </div>

          <div className="max-w-3xl space-y-4">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
              <Sparkles className="h-3.5 w-3.5" />
              Rules-based media optimization
            </span>
            <h1 className="text-balance text-4xl font-semibold leading-[1.05] tracking-tight text-foreground md:text-5xl">
              Compress smarter with{" "}
              <span className="text-gradient">content-aware</span> optimization
            </h1>
            <p className="max-w-2xl text-pretty text-base leading-relaxed text-muted-foreground">
              Upload images, video, audio, or PDFs. Proton analyzes each file&apos;s
              characteristics, picks the right codec and settings, and streams
              real-time progress as your media is compressed.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            {[
              {
                icon: Gauge,
                title: "Content analysis",
                desc: "Motion, entropy & bitrate signals",
              },
              {
                icon: Layers,
                title: "Optimization profiles",
                desc: "From smallest size to best quality",
              },
              {
                icon: Activity,
                title: "Real-time progress",
                desc: "Live updates over Server-Sent Events",
              },
            ].map((feature) => (
              <div
                key={feature.title}
                className="flex items-start gap-3 rounded-2xl border border-border bg-card/50 p-4 backdrop-blur transition-colors hover:border-primary/40"
              >
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-accent text-accent-foreground">
                  <feature.icon className="h-4.5 w-4.5" />
                </div>
                <div className="space-y-0.5">
                  <p className="text-sm font-medium text-foreground">{feature.title}</p>
                  <p className="text-xs leading-relaxed text-muted-foreground">{feature.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </header>

        <main className="grid flex-1 items-start gap-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
          <motion.div 
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5 }}
          >
            <Card className="overflow-hidden rounded-3xl border-border/80 bg-card/70 shadow-xl shadow-black/20 backdrop-blur">
              <CardHeader>
                <CardTitle className="text-xl">Upload &amp; optimize</CardTitle>
                <CardDescription>Drop a file, pick a profile, and queue it for compression.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div
                  {...getRootProps()}
                  className={cn(
                    "group relative flex min-h-60 cursor-pointer flex-col items-center justify-center overflow-hidden rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-all",
                    isDragActive
                      ? "border-primary bg-primary/10"
                      : "border-border hover:border-primary/50 hover:bg-muted/40",
                  )}
                >
                  <input {...getInputProps()} />
                  <div
                    className={cn(
                      "mb-4 flex h-16 w-16 items-center justify-center rounded-2xl transition-all",
                      isDragActive
                        ? "bg-primary text-primary-foreground"
                        : "bg-accent text-accent-foreground group-hover:scale-105",
                    )}
                  >
                    <CloudUpload className="h-8 w-8" />
                  </div>
                  <p className="text-base font-semibold text-foreground">
                    {isDragActive ? "Drop the file to upload" : "Drag & drop a file here"}
                  </p>
                  <p className="mt-1.5 max-w-sm text-sm text-muted-foreground">
                    or <span className="font-medium text-primary">browse</span> — images, video, audio & PDFs supported.
                  </p>
                </div>

              <div className="space-y-2.5">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium text-foreground">Optimization profile</span>
                  <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                    {selectedProfile.replaceAll("_", " ")}
                  </span>
                </div>
                <Tabs value={selectedProfile} onValueChange={(value) => setSelectedProfile(value as OptimizationProfile)}>
                  <TabsList className="grid h-auto w-full grid-cols-2 gap-1 sm:grid-cols-4">
                    <TabsTrigger value="smallest_size" className="text-xs">Smallest</TabsTrigger>
                    <TabsTrigger value="balanced" className="text-xs">Balanced</TabsTrigger>
                    <TabsTrigger value="best_quality" className="text-xs">Best quality</TabsTrigger>
                    <TabsTrigger value="web_optimized" className="text-xs">Web</TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>

              {preview ? (
                <div className="rounded-2xl border border-border bg-muted/30 p-4">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/15 text-primary">
                      <FileText className="h-5 w-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground">{preview.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {preview.type} · {preview.size}
                      </p>
                    </div>
                    <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-400" />
                  </div>
                </div>
              ) : (
                <div className="rounded-2xl border border-dashed border-border/70 px-4 py-5 text-center text-sm text-muted-foreground">
                  No file selected yet.
                </div>
              )}

              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Upload progress</span>
                  <span className="font-medium text-foreground">{uploadProgress}%</span>
                </div>
                <Progress value={uploadProgress} className="h-2" />
              </div>

              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <Button
                  onClick={handleUpload}
                  disabled={!selectedFile || uploadState === "uploading"}
                  size="lg"
                  className="w-full shadow-lg shadow-primary/20 sm:w-auto"
                >
                  {uploadState === "uploading" ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Uploading
                    </>
                  ) : (
                    <>
                      <CloudUpload className="h-4 w-4" />
                      Upload & compress
                    </>
                  )}
                </Button>

                <p
                  className={cn(
                    "text-sm",
                    uploadState === "done" && "text-emerald-400",
                    uploadState === "error" && "text-rose-400",
                    uploadState === "idle" && "text-muted-foreground",
                    uploadState === "uploading" && "text-muted-foreground",
                  )}
                >
                  {uploadState === "done"
                    ? "Upload complete. Live progress stream connected."
                    : uploadState === "error"
                      ? "Upload failed. Check the backend service and retry."
                      : "Choose a file to begin."}
                </p>
              </div>
            </CardContent>
          </Card>
          </motion.div>

          <motion.div 
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5 }}
          >
          <Card className="overflow-hidden rounded-3xl border-border/80 bg-card/70 shadow-xl shadow-black/20 backdrop-blur">
            <CardHeader>
              <CardTitle className="text-xl">Jobs &amp; insights</CardTitle>
              <CardDescription>Live status from FastAPI and the Celery worker.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2.5">
                {jobs.length > 0 ? (
                  jobs.map((job) => (
                    <button
                      key={job.id}
                      type="button"
                      onClick={() => setSelectedJobId(job.id)}
                      className={cn(
                        "flex w-full items-center justify-between gap-3 rounded-2xl border px-4 py-3 text-left transition-all",
                        selectedJobId === job.id
                          ? "border-primary/60 bg-primary/10 ring-1 ring-primary/20"
                          : "border-border bg-muted/20 hover:border-primary/40 hover:bg-muted/40",
                      )}
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-foreground">Job #{job.id}</p>
                        <p className="text-sm text-muted-foreground">
                          File {job.file_id} · {job.job_type} · {job.profile}
                        </p>
                      </div>
                      <span
                        className={cn(
                          "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium",
                          statusTone(job.status),
                        )}
                      >
                        {job.status.toLowerCase() === "completed" ? (
                          <CheckCircle2 className="h-3.5 w-3.5" />
                        ) : job.status.toLowerCase() === "failed" ? (
                          <AlertCircle className="h-3.5 w-3.5" />
                        ) : (
                          <Clock3 className="h-3.5 w-3.5" />
                        )}
                        {job.status}
                      </span>
                    </button>
                  ))
                ) : (
                  <div className="rounded-lg border border-dashed px-4 py-6 text-sm text-muted-foreground">
                    No jobs have been created yet.
                  </div>
                )}
              </div>

              <div className="rounded-lg border bg-background p-4">
                {selectedJob ? (
                  <div className="space-y-4">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-sm font-medium text-foreground">Selected job #{selectedJob.id}</p>
                        <p className="text-sm text-muted-foreground">
                          Status {selectedJob.status} · Profile {selectedJob.profile}
                        </p>
                      </div>
                      <span className={cn("rounded-full px-2.5 py-1 text-xs font-medium", statusTone(selectedJob.status))}>
                        {selectedJob.progress}%
                      </span>
                    </div>

                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">Progress</span>
                        <span className="font-medium text-foreground">{selectedJob.progress}%</span>
                      </div>
                      <Progress value={selectedJob.progress} className="h-2" />
                      <ChunkProgress
                        chunkJobs={chunkJobs}
                        totalChunks={chunkJobsTotal}
                        completedChunks={chunkJobsCompleted}
                        chunkLengthSeconds={chunkLengthSeconds}
                      />
                    </div>

                    {comparisonPreview ? (
                      <ThumbnailComparison
                        beforeUrl={comparisonPreview.originalUrl}
                        afterUrl={comparisonPreview.optimizedUrl}
                      />
                    ) : null}

                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="rounded-lg bg-muted/40 p-3">
                        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Output link</p>
                        {selectedJob.output_storage_path ? (
                          <a
                            href={minioObjectUrl(selectedJob.output_storage_path)}
                            target="_blank"
                            rel="noreferrer"
                            className="mt-1 inline-flex items-center gap-1 text-sm font-medium text-foreground underline-offset-4 hover:underline"
                          >
                            View optimized object
                            <ExternalLink className="h-3.5 w-3.5" />
                          </a>
                        ) : (
                          <p className="mt-1 text-sm text-muted-foreground">Waiting for worker output</p>
                        )}
                      </div>

                      <div className="rounded-lg bg-muted/40 p-3">
                        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Processing time</p>
                        <p className="mt-1 text-sm font-medium text-foreground">
                          {formatDuration(selectedJob.processing_duration)}
                        </p>
                      </div>
                    </div>

                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="rounded-lg bg-muted/40 p-3">
                        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Compression ratio</p>
                        <p className="mt-1 text-sm font-medium text-foreground">
                          {formatPercent(selectedJob.report_data?.compression_ratio)}
                        </p>
                      </div>
                      <div className="rounded-lg bg-muted/40 p-3">
                        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Codec used</p>
                        <p className="mt-1 text-sm font-medium text-foreground">
                          {formatAnalyticsValue(selectedJob.report_data?.codec_used)}
                        </p>
                      </div>
                      <div className="rounded-lg bg-muted/40 p-3">
                        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Original size</p>
                        <p className="mt-1 text-sm font-medium text-foreground">
                          {formatAnalyticsValue(selectedJob.report_data?.original_size)}
                        </p>
                      </div>
                      <div className="rounded-lg bg-muted/40 p-3">
                        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Optimized size</p>
                        <p className="mt-1 text-sm font-medium text-foreground">
                          {formatAnalyticsValue(selectedJob.report_data?.optimized_size)}
                        </p>
                      </div>
                    </div>

                    {selectedReport ? (
                      <Card className="border">
                        <CardHeader>
                          <CardTitle>Phase 3 Insights</CardTitle>
                          <CardDescription>
                            Analysis, quality, benchmarking and optimization report.
                          </CardDescription>
                        </CardHeader>

                        <CardContent>
                          {mediaType === "pdf" && (
                            <PdfReport report={selectedReport} />
                          )}

                          {mediaType === "image" && (
                            <ImageReport report={selectedReport} />
                          )}

                          {mediaType === "video" && (
                            <VideoReport report={selectedReport} />
                          )}

                          {mediaType === "audio" && (
                            <AudioReport report={selectedReport} />
                          )}
                        </CardContent>
                      </Card>
                    ) : null}

                    {selectedJob.error_message ? (
                      <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-300">
                        {selectedJob.error_message}
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <div className="text-sm text-muted-foreground">
                    Upload a file to create a job and watch its live progress.
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
          </motion.div>
        </main>
      </div>
    </div>
  );
}
