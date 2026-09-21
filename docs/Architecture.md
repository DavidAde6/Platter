# Platter production architecture

## Decision

Platter is a cost-first, single-host application. It does not use AWS for
runtime infrastructure. Cloudflare provides the public edge, Neon provides the
database, and one small Linux VM runs the application in Docker. This is the
smallest production setup that still keeps the backend private and the uploaded
images protected.

`useplatter.ca` is registered with Namecheap. AWS currently carries the DNS
and/or application traffic, but is not the registrar. Domain registration is
independent of DNS hosting: leave the registration at Namecheap and point its
nameservers to Cloudflare for the cutover. Once the rollback window is over,
remove the Route 53 hosted zone and the old AWS traffic path.

## Production request path

```text
User browser
  -> Cloudflare DNS + TLS + WAF + rate limiting
  -> Cloudflare Tunnel (outbound connection only)
  -> Small Linux VM
       -> cloudflared container
       -> Nginx/frontend container (useplatter.ca)
            -> /api/* -> FastAPI backend container
  -> Neon Postgres (pooled connection)
  -> Private Cloudflare R2 bucket (meal originals and thumbnails)
  -> Anthropic (meal analysis)
  -> USDA FoodData Central (nutrition data)
```

The browser uses one origin, `https://useplatter.ca`. Nginx serves the React
application and proxies `/api/*` to FastAPI over Docker's internal network.
FastAPI has no public port and the VM has no application ingress port open.

## Components and ownership

| Component | Service | Responsibility |
| --- | --- | --- |
| Domain registration | Namecheap | Holds registration, renewal, and the authoritative-nameserver setting. It does not serve application traffic. |
| Legacy DNS/traffic path | AWS Route 53 and current AWS deployment | Present only until cutover. Retire the Route 53 hosted zone and old AWS resources after the rollback window. |
| DNS, HTTPS, edge protection | Cloudflare | Authoritative DNS, browser TLS certificate, WAF, rate limits, and Tunnel public hostname. |
| Application host | One low-cost Linux VM | Runs Docker Compose. Start around 4 vCPU / 8 GB RAM only if upload benchmarks require it; otherwise choose the smallest host that passes them. |
| Private ingress | Cloudflare Tunnel / `cloudflared` | Makes an outbound connection from the VM. No public IP, ALB, or inbound app firewall rule is needed. |
| Web server | Nginx container | Serves the built frontend, SPA fallback, and proxies API requests. |
| API and analysis | FastAPI container | Authentication, uploads, meal analysis orchestration, database access, and authenticated image delivery. |
| Database | Neon Postgres | Production database via the pooled `DATABASE_URL`; a separate Neon branch or database is used for staging. |
| Image storage | Cloudflare R2 | Private originals and thumbnails. The API authorizes image access; buckets are never public. |
| AI and nutrition | Anthropic and USDA | External services called only by the backend; their API keys never reach the browser. |
| Source and images | GitHub + GHCR | Stores source, CI workflow, and immutable Docker images tagged with the commit SHA. |

## Deliberately not included

Do not add EKS, ECS, Kubernetes, ALB, CloudFront, AWS WAF, ACM, NAT Gateway,
ECR, or an AWS database to this first production architecture. They overlap
with the components above, increase the monthly floor, and add operations work
without solving a current measured requirement.

Likewise, do not introduce Redis, a queue, multiple hosts, or Kubernetes until
the upload benchmark shows that synchronous analysis cannot meet the latency
and concurrency target. At that point, add a durable queue and separate worker
processes before considering more orchestration.

## Minimal environments

| Environment | Domain and compute | Data isolation |
| --- | --- | --- |
| Local | Docker Compose on a developer machine | Local/dev credentials only. |
| Staging | Separate Cloudflare hostname and Tunnel, using the same simple Compose topology | Separate Neon branch/database, R2 bucket or isolated prefix, and non-production credentials. |
| Production | `useplatter.ca`, one Tunnel, one VM, one Compose stack | Production Neon database and private production R2 bucket. |

## Deployment and recovery

1. GitHub Actions builds backend and frontend images, tags them with the commit
   SHA, and pushes them to GHCR.
2. The VM pulls the selected immutable tags, runs `python migrate.py`, and
   updates the Compose stack.
3. Health checks cover the backend internally and `/health` through the
   Cloudflare hostname. Smoke tests cover login, upload, meal list, and an
   authenticated image.
4. Roll back application code by redeploying the last known-good image tags.
   Database migrations are forward-only and must remain compatible with both
   image versions during the rollback window.

Keep production secrets in a root-readable, host-only environment file outside
the repository. It contains the Neon pooled URL, JWT secret, R2 credentials,
Cloudflare Tunnel token, Anthropic key, USDA key, and worker/pool settings.

## Cost controls

- Start with one VM and only increase its size or worker count after measuring
  CPU, RAM, latency, and connection-pool waits.
- Use Neon's pooled endpoint and set a small database pool per Uvicorn worker.
- Store images in private R2; serve them through the authenticated API rather
  than making storage public.
- Set Cloudflare upload rate limits and file-size limits before the API.
- Retain only bounded container logs on the VM and keep a simple off-host VM
  backup/snapshot schedule.
- Review Anthropic usage and upload/error rates regularly; model calls are the
  main variable cost.

## When this architecture changes

Keep this design until one of these is observed in production: a single-host
outage is unacceptable, accepted-upload demand exceeds the measured limit,
analysis regularly misses the latency target, or API and analysis work need to
scale independently. The next change is a durable job queue and separate worker
processes—not a premature move to Kubernetes.
