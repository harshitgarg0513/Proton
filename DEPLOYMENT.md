# Proton Deployment Guide

This guide will help you deploy Proton to production using the following architecture:

```
Users
   │
   ▼
Vercel (Frontend)
   │
   ▼
Render (FastAPI Backend)
   │
   ├──────────────► Neon (PostgreSQL)
   │
   ├──────────────► Upstash (Redis)
   │
   ├──────────────► Cloudflare R2 (Object Storage)
   │
   └──────────────► Render Worker (Celery)
```

## Prerequisites

You should have accounts set up for:
- **Vercel** (Frontend hosting)
- **Render** (Backend API & Worker)
- **Neon** (PostgreSQL database)
- **Upstash** (Redis for Celery)
- **Cloudflare** (R2 for object storage)

---

## Step 1: Cloudflare R2 Setup

1. Go to Cloudflare Dashboard → R2 → Create Bucket
2. Create a bucket named `proton` (already created)
3. Go to R2 → Overview → Manage R2 API Tokens
4. Create an API token with:
   - Permissions: Object Read & Write
   - TTL: Use your preference
5. **Save these credentials:**
   - **Account ID**: `e66f3df41676f7a9fe1669951e3c2213`
   - **Access Key ID**: `26e87984293cc979e6c425a6ca9b5851`
   - **Secret Access Key**: `f0478f1c1446d773568f9be9af39c59386a26542eb6268522cf30b6ceb3101e2`
   - **Bucket Name**: `proton`

Your R2 endpoint will be: `https://e66f3df41676f7a9fe1669951e3c2213.r2.cloudflarestorage.com`

**Important:** Enable CORS policy for your bucket with:
```json
[
  {
    "AllowedOrigins": ["https://your-vercel-domain.vercel.app"],
    "AllowedMethods": ["GET", "PUT", "POST", "DELETE"],
    "AllowedHeaders": ["*"],
    "MaxAgeSeconds": 3600
  }
]
```

---

## Step 2: Neon PostgreSQL Setup

✅ **Already configured**
- Connection string: `postgresql://neondb_owner:npg_WAcSB9L8FmaP@ep-proud-leaf-aznsnifo.c-3.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`

---

## Step 3: Upstash Redis Setup

✅ **Already configured**
- Connection string: `redis://default:gQAAAAAAAqnFAAIgcDFkZWYzOTM1OGI2NDE0MTY4YmU0NzhkMjFmNTk4NWMyNQ@still-adder-174533.upstash.io:6379`

---

## Step 4: Render Backend Deployment

### Option A: Using render.yaml (Recommended)

1. Push your code to GitHub
2. Go to Render Dashboard → New → Blueprint
3. Connect your GitHub repository
4. Render will detect `render.yaml` and propose the following resources:
   - Web Service (FastAPI Backend)
   - PostgreSQL Database
   - Redis Instance
   - Worker (Celery)

5. **Configure the following environment variables in Render:**

For the **Backend Service** (`proton-backend`):
```bash
# Storage (Cloudflare R2)
STORAGE_ENDPOINT=e66f3df41676f7a9fe1669951e3c2213.r2.cloudflarestorage.com
STORAGE_ACCESS_KEY=26e87984293cc979e6c425a6ca9b5851
STORAGE_SECRET_KEY=f0478f1c1446d773568f9be9af39c59386a26542eb6268522cf30b6ceb3101e2
STORAGE_BUCKET=proton
STORAGE_SECURE=true
STORAGE_REGION=auto

# CORS (add your Vercel domain later)
CORS_ORIGINS=https://your-vercel-domain.vercel.app,https://your-custom-domain.com
```

For the **Worker** (`proton-worker`):
```bash
# Same storage configuration as backend
STORAGE_ENDPOINT=e66f3df41676f7a9fe1669951e3c2213.r2.cloudflarestorage.com
STORAGE_ACCESS_KEY=26e87984293cc979e6c425a6ca9b5851
STORAGE_SECRET_KEY=f0478f1c1446d773568f9be9af39c59386a26542eb6268522cf30b6ceb3101e2
STORAGE_BUCKET=proton
STORAGE_SECURE=true
STORAGE_REGION=auto
```

### Option B: Manual Setup

**Skip this step** - We're using external Neon and Upstash, so use Option A with render.yaml instead.

---

## Step 5: Vercel Frontend Deployment

1. Go to Vercel → Add New Project
2. Import your GitHub repository
3. Configure the project:
   - Framework Preset: Next.js
   - Root Directory: `frontend`
   - Build Command: `npm run build`
   - Output Directory: `.next`

4. **Add Environment Variables:**
   ```bash
   NEXT_PUBLIC_API_BASE_URL=https://your-render-backend-url.onrender.com
   NEXT_PUBLIC_DEMO_API_KEY=demo-api-key-12345678
   ```

5. Deploy!

---

## Step 6: Update CORS Origins

After deploying:
1. Get your Vercel domain (e.g., `proton.vercel.app`)
2. Go to Render → Backend Service → Environment
3. Update `CORS_ORIGINS`:
   ```bash
   CORS_ORIGINS=https://your-vercel-domain.vercel.app,https://your-custom-domain.com
   ```
4. Redeploy the backend service

---

## Environment Variables Reference

### Backend (Render)
```bash
APP_NAME=Proton API
API_PREFIX=/api
DATABASE_URL=postgresql://neondb_owner:npg_WAcSB9L8FmaP@ep-proud-leaf-aznsnifo.c-3.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
STORAGE_ENDPOINT=e66f3df41676f7a9fe1669951e3c2213.r2.cloudflarestorage.com
STORAGE_ACCESS_KEY=26e87984293cc979e6c425a6ca9b5851
STORAGE_SECRET_KEY=f0478f1c1446d773568f9be9af39c59386a26542eb6268522cf30b6ceb3101e2
STORAGE_BUCKET=proton
STORAGE_SECURE=true
STORAGE_REGION=auto
REDIS_URL=redis://default:gQAAAAAAAqnFAAIgcDFkZWYzOTM1OGI2NDE0MTY4YmU0NzhkMjFmNTk4NWMyNQ@still-adder-174533.upstash.io:6379
CORS_ORIGINS=https://your-frontend-domain.vercel.app
```

### Worker (Render)
```bash
APP_NAME=Proton API
DATABASE_URL=postgresql://neondb_owner:npg_WAcSB9L8FmaP@ep-proud-leaf-aznsnifo.c-3.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
STORAGE_ENDPOINT=e66f3df41676f7a9fe1669951e3c2213.r2.cloudflarestorage.com
STORAGE_ACCESS_KEY=26e87984293cc979e6c425a6ca9b5851
STORAGE_SECRET_KEY=f0478f1c1446d773568f9be9af39c59386a26542eb6268522cf30b6ceb3101e2
STORAGE_BUCKET=proton
STORAGE_SECURE=true
STORAGE_REGION=auto
REDIS_URL=redis://default:gQAAAAAAAqnFAAIgcDFkZWYzOTM1OGI2NDE0MTY4YmU0NzhkMjFmNTk4NWMyNQ@still-adder-174533.upstash.io:6379
```

### Frontend (Vercel)
```bash
NEXT_PUBLIC_API_BASE_URL=https://your-backend.onrender.com
NEXT_PUBLIC_DEMO_API_KEY=demo-api-key-12345678
```

---

## Local Development (Docker)

For local development, you can still use Docker Compose:
```bash
docker-compose up --build
```

This uses local PostgreSQL, Redis, and MinIO (S3-compatible) instead of cloud services.

---

## Troubleshooting

### Backend fails to start
- Check DATABASE_URL format (Neon uses `postgresql://` not `postgresql+psycopg2://`)
- Ensure Redis URL includes `rediss://` for SSL connections

### Worker not processing tasks
- Verify REDIS_URL matches between backend and worker
- Check Render Worker logs for Celery connection errors

### File upload failures
- Verify R2 credentials are correct
- Ensure STORAGE_BUCKET exists in Cloudflare R2
- Check CORS configuration if uploads fail from frontend

### Frontend can't connect to backend
- Verify NEXT_PUBLIC_API_BASE_URL is correct
- Check CORS_ORIGINS includes your Vercel domain
- Ensure backend is deployed and running

---

## Cost Estimates (Free Tiers)

- **Vercel**: Free tier sufficient for most projects
- **Render**: Free tier includes:
  - 1 Web Service (750 hours/month)
  - 1 PostgreSQL (512MB)
  - 1 Redis (25MB)
  - 1 Worker (free tier limited)
- **Neon**: Free tier (0.5GB storage, ~300 hours compute)
- **Upstash**: Free tier (10K commands/day)
- **Cloudflare R2**: Free tier (10GB storage/month, 1M Class A operations)

---

## Next Steps

**You still need to:**

1. **Configure R2 CORS Policy:**
   - Go to your R2 bucket "proton" → CORS Policy
   - Add this configuration:
   ```json
   [
     {
       "AllowedOrigins": ["https://your-vercel-domain.vercel.app"],
       "AllowedMethods": ["GET", "PUT", "POST", "DELETE"],
       "AllowedHeaders": ["*"],
       "MaxAgeSeconds": 3600
     }
   ]
   ```

2. **Deploy to Render:**
   - Push code to GitHub
   - Go to Render → New → Blueprint
   - Connect your repository
   - Render will detect render.yaml
   - All environment variables are pre-configured

3. **Deploy to Vercel:**
   - Go to Vercel → Add New Project
   - Import your GitHub repository
   - Set root directory to `frontend`
   - Add environment variable: `NEXT_PUBLIC_API_BASE_URL` (your Render backend URL)

4. **Update CORS:**
   - After getting your Vercel domain, update Render backend's `CORS_ORIGINS` environment variable
