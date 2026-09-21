# Production migration runbook

## Goal and boundaries

Move Platter's deployment from AWS/EKS to one Docker host behind Cloudflare,
while keeping Neon Postgres, private Cloudflare R2, Anthropic, and USDA as
managed dependencies. This is a deployment migration, not an M1 feature
dependency.

The target public shape is:

```text
Browser
  -> Cloudflare DNS, TLS, WAF, and rate limits
  -> Cloudflare Tunnel
  -> Docker host
       -> Nginx/frontend container (useplatter.ca)
            -> /api/* to FastAPI backend container
       -> cloudflared container
       -> FastAPI backend container (no public port)
  -> Neon Postgres, private R2, Anthropic, USDA
```

The frontend and API will share `https://useplatter.ca`; Nginx will forward
`/api/*` to FastAPI. `api.useplatter.ca` should be removed after cutover unless
a real external integration requires it.

Do not decommission AWS until the new path has passed the validation and
rollback window in this document.

## 1. Establish the operating envelope

**Owner:** application team  
**Exit criterion:** a written capacity decision for the initial host and worker
count.

1. Choose a representative upload set: valid meals, rejected/non-food images,
   HEIC files, and files near the 15 MB limit. Use the M1 evaluation set once
   available.
2. Run the *current public production path* at 1, 2, and 5 simultaneous
   uploads. Run enough requests at each level to calculate p50 and p95, and
   retain the raw results.
3. For every request, record total upload time and time spent in R2, image
   processing/OpenCV, each model call, and Neon reads/writes. Also record HTTP
   status, timeout, and error reason.
4. During each run, record host CPU/RAM, backend process count, container
   restarts, Neon connection waits, R2 errors, and model cost/latency.
5. Agree on release limits before building production infrastructure:

   - p95 end-to-end upload latency no greater than 30 seconds;
   - maximum accepted concurrent analyses for the host;
   - acceptable timeout and 5xx error budget;
   - Cloudflare and application rate limits per user and IP.

6. Make and record one decision:

   | Result | Initial deployment choice |
   | --- | --- |
   | Limits pass with synchronous analysis | Deploy 2 Uvicorn workers, then retest at 4 if CPU and memory allow. |
   | 4 workers pass and 2 does not | Deploy 4 workers and reduce each process's database-pool limit. |
   | The 30-second target or proxy timeout is missed | Do not increase public M1 traffic; make analysis durable/asynchronous first. |

## 2. Prepare the application for the target topology

**Owner:** application team  
**Exit criterion:** the app works when served at one origin with no public
backend port.

1. Change the production frontend API base URL from the separate
   `https://api.useplatter.ca` host to a same-origin relative URL. Local
   development may continue to use `http://127.0.0.1:8000`.
2. Confirm every browser call uses the shared API-base helper; no frontend file
   may hard-code the old API hostname.
3. Keep the existing `/health` endpoint and add a container health check that
   calls it from inside the Docker network.
4. Preserve the private-R2 design: buckets must not be public and images must
   remain available only through the authenticated
   `/api/meals/{meal_id}/image` route.
5. Set the production `DATABASE_URL` to the Neon pooled endpoint. Set
   `DB_POOL_MAX_SIZE` per Uvicorn process, not per host. Verify that
   `workers * DB_POOL_MAX_SIZE`, plus migration/admin connections, stays below
   the Neon connection budget. Keep `DB_POOL_MIN_SIZE=0` unless steady traffic
   justifies holding connections open.
6. Keep CORS entries for localhost in development. The same-origin production
   path does not require a separate API origin.

## 3. Add production deployment assets

**Owner:** application team  
**Exit criterion:** the stack can be started from immutable images using a
host-only environment file.

1. Keep `docker-compose.yml` for local development. Add a distinct production
   Compose file (for example `docker-compose.prod.yml`) rather than changing
   local defaults.
2. In that file define three services:

   - `backend`: FastAPI/Uvicorn, connected only to an internal network; do not
     publish port 8000 to the host.
   - `frontend`: Nginx serving the built React bundle and proxying `/api/` and
     `/health` to `backend:8000`.
   - `cloudflared`: connected to the frontend service and configured with the
     tunnel token stored only on the host.

3. Add a production Nginx configuration that serves the SPA correctly
   (including client-side route fallback), proxies API requests without
   buffering valid file uploads into an unexpectedly small limit, and passes
   the original host/protocol headers to FastAPI.
4. Configure health checks, `restart: unless-stopped`, JSON or bounded local
   logs, resource limits/reservations, and explicitly tagged backend and
   frontend images. Do not use `latest` in a deploy command.
5. Pass the Uvicorn worker count through a production environment value set
   from the benchmark decision. Ensure the image command actually consumes
   that value.
6. Create a host-only production environment file containing `DATABASE_URL`,
   `JWT_SECRET`, R2 credentials, `USDA_API_KEY`, model credentials, worker
   count, pool settings, and Cloudflare tunnel token. Keep it outside the
   repository and restrict it to the deployment user.
7. Add a preflight command that checks required variables are present without
   printing their values. Test `docker compose ... config` before deploying.

## 4. Provision staging and the production host

**Owner:** infrastructure owner  
**Exit criterion:** staging is reachable through Cloudflare and production is
ready but has no public traffic.

1. Provision one Linux VM initially. If M1 remains synchronous, start at about
   4 vCPU and 8 GB RAM; revise this after the benchmark.
2. Create a non-root deployment user. Install Docker/Compose, enable automatic
   security updates, allow SSH only from approved administration sources, and
   retain a documented break-glass access method.
3. Create separate staging resources:

   - a Neon branch or separate staging database;
   - a separate R2 bucket or a rigorously isolated prefix with staging-only
     credentials;
   - separate model/API credentials where practical;
   - a staging hostname and Cloudflare Tunnel.

4. Create a production Cloudflare Tunnel on the host. Map
   `useplatter.ca` to the frontend service, enable Cloudflare TLS, and set WAF
   and upload rate-limit rules to the limits established in step 1.
5. Define expected request/upload timeouts in Cloudflare, Nginx, and FastAPI.
   They must leave enough time for the measured p95 upload while still failing
   stuck requests predictably.
6. Do not create an inbound firewall opening for FastAPI. The public route is
   Cloudflare Tunnel to Nginx; SSH is the only expected host administration
   ingress.

## 5. Make deployments repeatable and reversible

**Owner:** application team  
**Exit criterion:** staging deployment and rollback are rehearsed successfully.

1. Replace the EKS-specific CI workflow with a build-and-publish workflow for
   backend and frontend images. Tag both with the commit SHA and retain the
   previous successful tag.
2. Choose the container registry before deleting ECR. If it is not ECR, move
   the images and update host credentials first.
3. Add a host deploy script/runbook that performs this exact order:

   ```text
   record currently running image tags
   pull the requested immutable tags
   run `python migrate.py` with the target environment
   start/update the Compose stack
   wait for internal and public /health checks
   smoke-test login, upload, meal list, and authenticated image retrieval
   ```

4. Run `python migrate.py --status` before every deployment. Apply migrations
   before an application version that depends on them.
5. Treat migrations as forward-only. A rollback redeploys the previous image
   tag; it must not attempt to reverse schema changes. New migrations must
   remain compatible with both the current and immediately previous app image
   for the rollback window.
6. Rehearse a staging rollback: deploy a new tagged version, verify it, then
   redeploy the previous tag and verify that core flows still work.

## 6. Validate through the real edge path

**Owner:** application and infrastructure owners  
**Exit criterion:** staging meets the release limits from step 1.

1. Run migrations and the application test suite against the staging database.
   `TEST_DATABASE_URL` must point to a disposable database/branch, never the
   staging or production database.
2. Run the evaluation set and the 1/2/5-concurrency test through the staging
   Cloudflare hostname, not localhost or direct container ports.
3. Verify these outcomes manually and in automated smoke tests:

   - valid uploads complete and their originals/thumbnails persist in R2;
   - rejected and degraded-model cases produce the documented user outcome;
   - R2/model failures degrade cleanly and preserve the recorded upload state;
   - authenticated image URLs work and unauthenticated/cross-user access is
     denied;
   - files near the allowed size and supported HEIC uploads survive all proxy
     layers;
   - Cloudflare, Nginx, and application timeouts do not terminate valid p95
     requests.

4. Monitor and retain dashboards/logs for CPU, RAM, disk, container restarts,
   database-pool waits, R2 failures, model latency/cost, and 4xx/5xx/timeout
   rates.
5. Do not proceed if a release limit fails. Reduce concurrency, add workers if
   the host has measured headroom, or move analysis to a durable async workflow
   before retrying.

## 7. Cut over safely

**Owner:** infrastructure owner  
**Exit criterion:** production traffic is stable on the new host and AWS can be
retired after the rollback window.

1. Schedule the change and publish the on-call owner, deployment tag,
   rollback tag, expected duration, and success criteria.
2. Lower the DNS TTL ahead of the cutover. Deploy the already-validated image
   tags to production, apply any pending migration, and complete the smoke
   tests through the production Cloudflare route before moving broad traffic.
3. Switch `useplatter.ca` to the Tunnel. Keep the old AWS/EKS route available
   but idle for a defined rollback window (for example, seven days).
4. During the window, watch the metrics from step 6 and compare p95 latency,
   error rate, and model/R2 behavior with the staging baseline.
5. Roll back immediately by restoring the former route if the new stack cannot
   serve core traffic. For an application-only regression, redeploy the
   recorded previous image tags; do not reverse migrations.
6. After the window, confirm there are no remaining dependencies on AWS DNS,
   ACM certificates, ECR, ALB, EKS, IAM, or CI secrets. Archive `k8s/` and
   `cluster.yml` as future-scale reference with a note that they are inactive.
7. Remove AWS resources only after the dependency review has been signed off.
   Record what was removed, its owner, and any cost/billing confirmation.

## 8. Return-to-scale triggers

The single-host architecture is the default until evidence says otherwise.
Open a scaling project when any one of the following occurs:

- p95 upload latency exceeds 30 seconds or edge/proxy timeouts appear;
- sustained accepted-upload demand exceeds the measured operating envelope;
- segmentation or additional model stages make synchronous processing too slow;
- a single-host outage is no longer acceptable; or
- API and worker workloads need to scale independently.

The next step is then a durable queue and independently scalable worker
processes. Add multiple hosts or Kubernetes only when that architecture has a
measured need for orchestration, availability, or horizontal scaling.

## Execution order

1. Benchmark the current public upload path and make the worker/async
   decision.
2. Implement same-origin API access and the production Compose/Nginx/Tunnel
   assets.
3. Provision isolated staging and rehearse deploy, validation, rollback.
4. Provision production, validate through its Cloudflare path, and cut over.
5. Observe through the rollback window; only then archive and remove AWS/EKS
   dependencies.
