#!/bin/bash
# ==============================================================================
# HistorySnooze Ephemeral Host Launcher Script (run.sh)
# Permissions: chmod +x (755) | Authority: 03_SECURE_ISOLATION_VAULT.md
# Mandates: Non-root 1000:1000, --rm auto-destruct, tmpfs /dev/shm, read-only secrets
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="${HSNOOZE_IMAGE:-historysnooze-sandbox:latest}"
COMPOSE_FILE="${SCRIPT_DIR}/docker/docker-compose.yml"
DOCKERFILE="${SCRIPT_DIR}/docker/Dockerfile"

# 1. Resolve Host Workspace & Secrets Profile Directories
WORKSPACE_DIR="${HSNOOZE_WORKSPACE:-$SCRIPT_DIR}"
[ -d "$WORKSPACE_DIR" ] || WORKSPACE_DIR="$SCRIPT_DIR"

PROFILE="${HSNOOZE_PROFILE:-historysnooze}"
DEFAULT_PROFILE_DIR="${HOME}/.cloud-profiles/${PROFILE}"
SECRETS_HOST_DIR=""

if [ -n "${HSNOOZE_SECRETS_DIR:-}" ] && [ -d "$HSNOOZE_SECRETS_DIR" ]; then
    SECRETS_HOST_DIR="$HSNOOZE_SECRETS_DIR"
elif [ -d "$DEFAULT_PROFILE_DIR" ]; then
    SECRETS_HOST_DIR="$DEFAULT_PROFILE_DIR"
elif [ -d "${WORKSPACE_DIR}/credentials" ]; then
    SECRETS_HOST_DIR="${WORKSPACE_DIR}/credentials"
elif [ -d "${SCRIPT_DIR}/credentials" ]; then
    SECRETS_HOST_DIR="${SCRIPT_DIR}/credentials"
fi

show_help() {
    cat <<EOF
Usage: ./run.sh [OPTIONS] [COMMAND...]
HistorySnooze Ephemeral Container Launcher (UID 1000, --rm, tmpfs /dev/shm)

Options:
  --build              Build or rebuild Docker sandbox image before execution
  --smoke-test, test   Execute in-container smoke verification suite
  --shell              Launch interactive bash shell inside container
  --help, -h           Display this help message
EOF
}

build_image() {
    echo "[+] Building Docker Sandbox Image: ${IMAGE_NAME}..."
    if [ -f "$COMPOSE_FILE" ]; then
        docker compose -f "$COMPOSE_FILE" build
    else
        docker build -f "$DOCKERFILE" -t "$IMAGE_NAME" "$WORKSPACE_DIR"
    fi
    echo "[✓] Image ${IMAGE_NAME} built successfully."
}

# 2. Parse CLI Subcommands & Flags
DO_BUILD=0
EXEC_CMD=()

while [ $# -gt 0 ]; do
    case "$1" in
        --help|-h) show_help; exit 0 ;;
        --build) DO_BUILD=1; shift ;;
        --smoke-test|test)
            EXEC_CMD=(bash -c "
                set -e
                echo '[1/4] User: UID 1000' && [ \"\$(id -u)\" -eq 1000 ]
                echo '[2/4] Python Bytecode' && python3 -m py_compile \$(find . -maxdepth 2 -name '*.py' -not -path '*/.*')
                echo '[3/4] Runtimes' && node -v && npm -v && ffmpeg -version | head -n 1
                echo '[4/4] Pytest' && pytest tests/test_hitl_and_dimming.py tests/test_phase1_remediation.py tests/test_dual_operation_parity.py -q
                echo '[✓] Smoke verification passed!'
            ")
            shift ;;
        --shell) EXEC_CMD=(/bin/bash); shift ;;
        *) EXEC_CMD=("$@"); break ;;
    esac
done

[ "$DO_BUILD" -eq 1 ] && { build_image; [ ${#EXEC_CMD[@]} -eq 0 ] && exit 0; }

# Ensure Image Exists
docker image inspect "$IMAGE_NAME" >/dev/null 2>&1 || {
    echo "[!] Image ${IMAGE_NAME} missing locally. Building..."; build_image;
}

# 3. Configure TTY & Volume Mounts
DOCKER_TTY="-i"
[ -t 0 ] && [ -t 1 ] && DOCKER_TTY="-it"

MOUNT_FLAGS=("-v" "${WORKSPACE_DIR}:/workspace:rw")
PARENT_MEDIA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)/02. Media Generation"
if [ -d "$PARENT_MEDIA_DIR" ] && [ ! -d "${WORKSPACE_DIR}/02. Media Generation" ]; then
    MOUNT_FLAGS+=("-v" "${PARENT_MEDIA_DIR}:/workspace/02. Media Generation:rw")
fi
if [ -n "$SECRETS_HOST_DIR" ] && [ -d "$SECRETS_HOST_DIR" ]; then
    echo "[+] Mounting secrets from: ${SECRETS_HOST_DIR} (:ro)"
    MOUNT_FLAGS+=("-v" "${SECRETS_HOST_DIR}:/workspace/credentials:ro" "-v" "${SECRETS_HOST_DIR}:/workspace/.secrets:ro")
else
    echo "[!] [NOTICE] No secrets directory found. Running without credentials mount."
fi

# 4. Ephemeral Container Launch (--rm, 1000:1000, tmpfs 512m, cap-drop ALL)
if [ ${#EXEC_CMD[@]} -eq 0 ]; then
    if [ -t 0 ] && [ -t 1 ]; then
        EXEC_CMD=(/bin/bash)
    else
        EXEC_CMD=(python3 pipeline_orchestrator.py --help)
    fi
fi

CONTAINER_NAME="hsnooze-sandbox-$$-$(date +%s)"
echo "[+] Launching Ephemeral Sandbox: ${CONTAINER_NAME} (UID 1000, --rm, tmpfs /dev/shm)"

exec docker run ${DOCKER_TTY} --rm \
    --name "${CONTAINER_NAME}" \
    --user "1000:1000" \
    --security-opt "no-new-privileges:true" \
    --cap-drop ALL \
    --tmpfs "/dev/shm:rw,noexec,nosuid,size=512m" \
    "${MOUNT_FLAGS[@]}" \
    -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/workspace \
    ${MASTER_VAULT_PASS:+-e MASTER_VAULT_PASS="$MASTER_VAULT_PASS"} \
    "${IMAGE_NAME}" "${EXEC_CMD[@]}"
