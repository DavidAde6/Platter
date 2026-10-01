🔲 Tighten UFW
🔲 Move docker-compose.yml / nginx.conf into the repo so config deploys with code
🔲 Add automated Docker image cleanup
🔲 Add monitoring/alerts
🔲 Build a nicer one-command rollback process
🔲 Before public M1 rollout: measure second-model-call cost, set a spend alert/cap, and add per-user/IP upload rate limiting

## M1 synchronous analysis: private-MVP operating note

**Decision:** M1 will keep analysis synchronous during private MVP development.
An accepted upload runs the existing quality gate and then exactly one
visible-foods model call in the request. Rejected photos must skip the second
call. This preserves the current simple upload/response loop while the food-ID
prompt and schema are being iterated.

**Known constraints:** the current service has one Uvicorn worker with a 400m
CPU limit, and the async upload route directly performs blocking OpenCV, R2,
and model work. A second vision call can therefore increase both upload latency
and interference with concurrent requests. The deployed request deadline is
not yet verified: Kubernetes points to an AWS ALB; the manifest does not set
its idle timeout, so 60 seconds is only the AWS default, not an established
fact about the live path.

**Before public rollout, record evidence for:**

- DNS/certificate, ALB listener and target health, and authenticated
  `GET /health` through the public path.
- The actual ALB idle timeout plus every upstream and client timeout.
- Current and M1-enabled authenticated upload p50/p95, timeout/error rates,
  and per-stage model latency.
- A small one-, two-, and five-concurrent-upload test: upload latency,
  timeout/errors, health latency, pod CPU/memory, and model failures.
- A M1 operating envelope: allowed concurrency, maximum p95, remediation
  trigger, representative second-call token/cost samples, a budget owner, and
  an alert/cap or monitored rate limit.

**Switch to durable async analysis** (queue + worker, durable processing
state, retries/idempotency, and client polling or push) before public rollout,
or sooner if the real request deadline is approached, public-path timeouts
occur, concurrency harms health/latency, or a future stage adds enough model
work that the synchronous envelope is exceeded. FastAPI `BackgroundTasks` is
not a production alternative: it reduces client wait time but neither adds
capacity nor survives a pod restart.
