#!/usr/bin/env bash

# This script is copied to the VPS and invoked by GitHub Actions for every
# production release. Image names come from the workflow's current commit SHA;
# do not put a release SHA in this file or in the host environment.
set -Eeuo pipefail
trap 'echo "Deployment failed at remote-deploy.sh line $LINENO." >&2' ERR

: "${DEPLOY_PATH:=/opt/platter}"
: "${BACKEND_IMAGE:?BACKEND_IMAGE must be the immutable backend image for this release}"
: "${FRONTEND_IMAGE:?FRONTEND_IMAGE must be the immutable frontend image for this release}"

compose=(
  docker compose
  --project-name platter
  --env-file "$DEPLOY_PATH/.env"
  -f "$DEPLOY_PATH/deploy/docker-compose.prod.yml"
)

echo "Deploying to host: $(hostname)"
echo "Release frontend image: $FRONTEND_IMAGE"

# The root Compose file was a legacy source-build setup and must not return to
# the production host.
rm -f "$DEPLOY_PATH/docker-compose.yml"

echo "Checking Docker Compose configuration..."
BACKEND_IMAGE="$BACKEND_IMAGE" FRONTEND_IMAGE="$FRONTEND_IMAGE" "${compose[@]}" config -q

echo "Pulling immutable images..."
BACKEND_IMAGE="$BACKEND_IMAGE" FRONTEND_IMAGE="$FRONTEND_IMAGE" "${compose[@]}" pull

echo "Running database migrations..."
BACKEND_IMAGE="$BACKEND_IMAGE" FRONTEND_IMAGE="$FRONTEND_IMAGE" "${compose[@]}" run --rm backend python migrate.py

echo "Starting updated application..."
BACKEND_IMAGE="$BACKEND_IMAGE" FRONTEND_IMAGE="$FRONTEND_IMAGE" "${compose[@]}" up -d --force-recreate --wait --remove-orphans

echo "Verifying deployed containers..."
backend_id=$("${compose[@]}" ps -q backend)
frontend_id=$("${compose[@]}" ps -q frontend)
test -n "$backend_id"
test -n "$frontend_id"

test "$(docker inspect "$backend_id" --format '{{.Config.Image}}')" = "$BACKEND_IMAGE"
test "$(docker inspect "$frontend_id" --format '{{.Config.Image}}')" = "$FRONTEND_IMAGE"

build_sha=${FRONTEND_IMAGE##*:}
expected_build="{\"git_sha\":\"$build_sha\"}"
actual_build=$(docker exec "$frontend_id" cat /usr/share/nginx/html/build.json)
test "$actual_build" = "$expected_build"

actual_config=$(docker inspect "$backend_id" --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}')
test "$actual_config" = "$DEPLOY_PATH/deploy/docker-compose.prod.yml"

docker exec "$backend_id" python -c \
  'from graph.builder import PIPELINE_VERSION; assert PIPELINE_VERSION == "m1-visible-foods", PIPELINE_VERSION'

echo "Deployment status:"
"${compose[@]}" ps
