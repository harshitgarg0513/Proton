"use client";

import axios from "axios";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  Clock3,
  CloudUpload,
  ExternalLink,
  FileText,
  Loader2,
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

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
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
      return "bg-emerald-500/10 text-emerald-700";
    case "failed":
      return "bg-rose-500/10 text-rose-700";
    case "processing":
      return "bg-blue-500/10 text-blue-700";
    case "retrying":
    case "pending":
      return "bg-amber-500/10 text-amber-700";
    default:
      return "bg-slate-500/10 text-slate-700";
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
          "Content-Type": "multipart/form-data",
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
    <div className="min-h-screen bg-background">
      <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-4 py-6 md:px-8 lg:px-10">
        <header className="flex flex-col gap-2 border-b">
          <p className="text-sm font-medium uppercase tracking-wider text-muted-foreground">
            Adaptive Content Platform
          </p>
          <h1 className="text-3xl font-semibold tracking-tight text-foreground md:text-4xl">
            Content Upload and Processing
          </h1>
          <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground md:text-base">
            Upload files into MinIO, enqueue compression jobs, and monitor worker progress in real time.
          </p>
        </header>

        <main className="grid flex-1 gap-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
          <motion.div 
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5 }}
          >
            <Card>
              <CardHeader>
                <CardTitle>Upload Section</CardTitle>
                <CardDescription>Drag and drop a file, then choose an optimization profile.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                <div
                  {...getRootProps()}
                  className={cn(
                    "flex min-h-56 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors",
                    isDragActive
                      ? "border-primary bg-primary/5"
                      : "border-border hover:bg-muted/50",
                  )}
                >
                  <input {...getInputProps()} />
                  <CloudUpload className="mb-3 h-10 w-10 text-muted-foreground" />
                  <p className="text-base font-medium text-foreground">
                    {isDragActive ? "Drop the file here" : "Drag and drop a file here"}
                  </p>
                  <p className="mt-2 max-w-sm text-sm text-muted-foreground">
                    The file is uploaded to FastAPI, stored in MinIO, and queued for the worker.
                  </p>
                </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium text-foreground">Optimization profile</span>
                  <span className="text-muted-foreground">Phase 2 input</span>
                </div>
                <Tabs value={selectedProfile} onValueChange={(value) => setSelectedProfile(value as OptimizationProfile)}>
                  <TabsList className="w-full justify-between">
                    <TabsTrigger value="smallest_size">smallest_size</TabsTrigger>
                    <TabsTrigger value="balanced">balanced</TabsTrigger>
                    <TabsTrigger value="best_quality">best_quality</TabsTrigger>
                    <TabsTrigger value="web_optimized">web_optimized</TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>

              {preview ? (
                <div className="rounded-lg border bg-background p-4">
                  <div className="flex items-start gap-3">
                    <div className="rounded-lg bg-muted p-2">
                      <FileText className="h-5 w-5 text-foreground" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground">{preview.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {preview.type} · {preview.size}
                      </p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="rounded-lg border border-dashed px-4 py-5 text-sm text-muted-foreground">
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

              <div className="flex items-center gap-3">
                <Button onClick={handleUpload} disabled={!selectedFile || uploadState === "uploading"}>
                  {uploadState === "uploading" ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Uploading
                    </>
                  ) : (
                    <>
                      <FileText className="h-4 w-4" />
                      Upload file
                    </>
                  )}
                </Button>

                <p
                  className={cn(
                    "text-sm",
                    uploadState === "done" && "text-emerald-600",
                    uploadState === "error" && "text-rose-600",
                    uploadState === "idle" && "text-muted-foreground",
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
          <Card>
            <CardHeader>
              <CardTitle>Job Status List</CardTitle>
              <CardDescription>Live status from FastAPI and the Celery worker.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-3">
                {jobs.length > 0 ? (
                  jobs.map((job) => (
                    <button
                      key={job.id}
                      type="button"
                      onClick={() => setSelectedJobId(job.id)}
                      className={cn(
                        "flex w-full items-center justify-between rounded-lg border px-4 py-3 text-left transition-colors",
                        selectedJobId === job.id
                          ? "border-primary bg-primary/5"
                          : "border-border bg-background hover:bg-muted/40",
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
                      <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
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