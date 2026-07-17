# Proton

An intelligent media compression platform that analyzes content characteristics and applies rules-based optimization strategies to reduce file size while maintaining quality.

## What It Does

Uploads media files (images, videos, audio, PDFs), analyzes their content characteristics, and applies a rules-based optimization strategy to compress them using appropriate codec/CRF/resolution settings based on the content type and a chosen optimization profile. The system processes files asynchronously using Celery workers with ffmpeg, stores results in MinIO object storage, and provides real-time progress updates via Server-Sent Events.

## Architecture

```
┌─────────────┐
│   Frontend  │ (Next.js + shadcn/ui)
│   :3000     │
└──────┬──────┘
       │ HTTP/REST + SSE
       ↓
┌─────────────┐
│   Backend   │ (FastAPI)
│   :8000     │
└──────┬──────┘
       │
       ├──────────────┬──────────────┬──────────────┐
       ↓              ↓              ↓              ↓
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  Postgres   │ │    MinIO    │ │    Redis    │ │   Celery    │
│  :5432      │ │   :9000     │ │   :6379     │ │   Worker    │
└─────────────┘ └─────────────┘ └─────────────┘ └──────┬──────┘
                                                 │ ffmpeg
                                                 ↓
                                          ┌─────────────┐
                                          │  Optimized  │
                                          │   Output    │
                                          └─────────────┘

┌─────────────┐
│  Prometheus │ (Metrics)
│  :9090      │
└──────┬──────┘
       │
       ↓
┌─────────────┐
│   Grafana   │ (Visualization)
│  :3001      │
└─────────────┘
```

## How "Adaptive" Actually Works

This platform uses a **rules-based engine**, not machine learning. The system analyzes content characteristics and applies predetermined optimization strategies:

**Signals Used:**
- **Motion intensity** (video): Analyzes frame differences to determine scene complexity
- **Entropy** (images): Measures visual complexity to determine compression aggressiveness
- **Bitrate** (audio/video): Evaluates current encoding quality
- **Duration** (all media): Determines processing strategy based on length

**Optimization Profiles:**
- `smallest_size`: Maximum compression, lower quality
- `balanced`: Default profile balancing size and quality
- `best_quality`: Minimal compression, highest quality
- `web_optimized`: Optimized for web delivery with progressive loading

The rules engine selects appropriate codec settings, CRF values, and resolution adjustments based on these signals and the chosen profile.

## Quickstart

```bash
# Clone and start all services
docker compose up -d

# Services will be available at:
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# MinIO Console: http://localhost:9001 (minioadmin/minioadmin)
# Prometheus: http://localhost:9090
# Grafana: http://localhost:3001 (admin/admin)

# Demo API Key: demo-api-key-12345678
# (Set via NEXT_PUBLIC_DEMO_API_KEY environment variable)
```

## Authentication

The platform uses API-key based authentication for data isolation. Each API key maps to its own data namespace, ensuring users can only access their own files and jobs. This provides legitimate per-key isolation without requiring a full user management system.

**For the demo:** The frontend is configured with `demo-api-key-12345678` as the default API key.

**For production:** Replace the `get_current_owner` function in `backend/app/core/auth.py` with proper OAuth/JWT authentication and a real users table.

## Known Limitations

- **Rate limiting:** In-memory per process; behind multiple replicas this would need Redis-backed counters
- **No user accounts:** Uses API-key based isolation instead of full user management
- **Single-region deployment:** Not designed for multi-region or CDN distribution
- **Rules-based optimization:** Uses predetermined rules rather than ML models
- **Chunked processing:** Large files are processed in chunks, which may not be optimal for all media types

## Test Coverage

```bash
# Backend tests
cd backend
pytest

# Worker tests  
cd worker
pytest
```

## Tech Stack

- **Frontend:** Next.js 16, React 19, Tailwind CSS, shadcn/ui, framer-motion
- **Backend:** FastAPI, SQLAlchemy, PostgreSQL
- **Queue:** Celery + Redis
- **Storage:** MinIO (S3-compatible)
- **Processing:** FFmpeg
- **Monitoring:** Prometheus + Grafana
- **Containerization:** Docker Compose
