#!/usr/bin/env bash
# Run the automation CLI in the dclab/automation container, attached to the
# lab management network so it can SSH to every node.
#
#   scripts/automation.sh backup -i inventory/frr-lab.yml
#   scripts/automation.sh check  -i inventory/frr-lab.yml
#   scripts/automation.sh pytest -q automation/tests
set -euo pipefail
LAB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
NET="${MGMT_NET:-dclab-mgmt}"
IMAGE="${AUTOMATION_IMAGE:-dclab/automation:1.0}"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) SRC="$(cygpath -m "$LAB_DIR")"; export MSYS_NO_PATHCONV=1 ;;
  *) SRC="$LAB_DIR" ;;
esac
if [ "${1:-}" = "pytest" ] || [ "${1:-}" = "yamllint" ]; then
  exec docker run --rm -v "${SRC}:/lab" -w /lab "$IMAGE" "$@"
fi
exec docker run --rm --network "$NET" -v "${SRC}:/lab" -w /lab "$IMAGE" python -m automation "$@"
