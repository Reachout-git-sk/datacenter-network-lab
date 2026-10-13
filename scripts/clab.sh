#!/usr/bin/env bash
# Run containerlab from its container image, so nothing has to be installed on
# the workstation. The lab directory is mounted at the same path the Docker
# engine sees, because containerlab hands bind-mount paths to the engine.
#
#   scripts/clab.sh deploy  -t topologies/dc-frr.clab.yml
#   scripts/clab.sh inspect -t topologies/dc-frr.clab.yml
#   scripts/clab.sh destroy -t topologies/dc-frr.clab.yml --cleanup
#
# On Windows (Git Bash + Docker Desktop) the engine sees drive E: as
# /run/desktop/mnt/host/e, so the path is translated.
set -euo pipefail
CLAB_IMAGE="${CLAB_IMAGE:-ghcr.io/srl-labs/clab:latest}"
LAB_DIR="$(cd "$(dirname "$0")/.." && pwd)"

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    drive="$(echo "$LAB_DIR" | cut -d/ -f2)"
    rest="$(echo "$LAB_DIR" | cut -d/ -f3-)"
    ENGINE_DIR="/run/desktop/mnt/host/${drive,,}/${rest}"
    SOCK="//var/run/docker.sock"
    export MSYS_NO_PATHCONV=1
    ;;
  *)
    ENGINE_DIR="$LAB_DIR"
    SOCK="/var/run/docker.sock"
    ;;
esac

exec docker run --rm -i \
  --privileged --network host --pid host \
  -v "${SOCK}:/var/run/docker.sock" \
  -v /var/run/netns:/var/run/netns \
  -v "${ENGINE_DIR}:${ENGINE_DIR}" \
  -w "${ENGINE_DIR}" \
  "${CLAB_IMAGE}" containerlab "$@"
