# Current Docker deployment

The GitHub Actions workflow deploys to the OVHcloud VPS at `/opt/platter` and
invokes `deploy/docker-compose.prod.yml` with `--env-file /opt/platter/.env`.
Keep that host-only environment file outside source control, mode `0600`, and
owned by the deployment user. It holds the application credentials, including
the pooled `DATABASE_URL` and direct `DATABASE_URL_UNPOOLED`. Note that the
current `migrate.py` reads `DATABASE_URL` only, so the migration command must
explicitly override that variable with the direct URL; adding
`DATABASE_URL_UNPOOLED` alone does not change its connection.

Build the frontend image in CI with an empty `VITE_API_URL` build argument. An
empty value makes the browser use relative `/api/...` URLs, so Nginx can proxy
them at the single public origin.

```sh
docker build --build-arg VITE_API_URL= -t ghcr.io/ORG/platter-frontend:SHA frontend
```

Each CI image also includes `/build.json`, containing the commit SHA. The
deployment checks this marker both inside the frontend container and at the
public origin. Set the repository variable `PUBLIC_ORIGIN` if production moves
away from `https://useplatter.ca`.

Set `BACKEND_IMAGE` and `FRONTEND_IMAGE` to the matching immutable commit-SHA
tags and pin `CLOUDFLARED_VERSION` to a tested release. Before starting the
stack, configure the Tunnel's public hostname in Cloudflare to point to:

```text
http://frontend:80
```

On the OVHcloud VPS, render and start the stack with the current deployment
contract:

```sh
docker compose --env-file /opt/platter/.env -f /opt/platter/deploy/docker-compose.prod.yml config --quiet
docker compose --env-file /opt/platter/.env -f /opt/platter/deploy/docker-compose.prod.yml up -d
```

The production Compose file runs the backend, frontend, and Cloudflare Tunnel
together; the Tunnel's public hostname should point to `http://frontend:80`.

## CI/CD

On pushes to `main`, GitHub Actions builds both images, pushes immutable
commit-SHA tags to GHCR, then connects to the VM over SSH and runs the Compose
deployment. Configure these repository secrets:

- `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, and `DEPLOY_KNOWN_HOSTS` for
  the deployment user's SSH connection.

Before enabling the workflow, authenticate Docker on the VM to GHCR with an
account or token that has `read:packages` access to the private images. This
keeps registry credentials host-local rather than sending them through the
deployment job.

Set the workflow's `DEPLOY_PATH` environment variable to the directory on the
OVHcloud VPS containing this repository (default: `/opt/platter`).
The deployment supplies the new image tags only for that Compose invocation;
the host-only production environment file remains unchanged.
