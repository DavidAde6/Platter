# Production Docker deployment

Keep the real environment file outside the repository, for example
`/etc/platter/production.env`, mode `0600`, owned by the deployment user. Copy
[`.env.example`](../.env.example) there as `production.env` and replace every
placeholder.

Build the frontend image in CI with an empty `VITE_API_URL` build argument. An
empty value makes the browser use relative `/api/...` URLs, so Nginx can proxy
them at the single public origin.

```sh
docker build --build-arg VITE_API_URL= -t ghcr.io/ORG/platter-frontend:SHA frontend
```

Set `BACKEND_IMAGE` and `FRONTEND_IMAGE` to the matching immutable commit-SHA
tags and pin `CLOUDFLARED_VERSION` to a tested release. Before starting the
stack, configure the Tunnel's public hostname in Cloudflare to point to:

```text
http://frontend:80
```

On the VM, render and start the stack with the host-only file:

```sh
docker compose --env-file /etc/platter/production.env -f deploy/docker-compose.prod.yml config --quiet
docker compose --env-file /etc/platter/production.env -f deploy/docker-compose.prod.yml up -d
```

This Compose stack publishes no host ports. `cloudflared` is the sole ingress;
the backend is reachable only by Nginx on the Docker network.

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
VM containing this repository's `deploy/` directory (default: `/opt/platter`).
The deployment supplies the new image tags only for that Compose invocation;
the host-only production environment file remains unchanged.
