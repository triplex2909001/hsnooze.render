#!/bin/bash
# ==============================================================================
# HistorySnooze Sandbox Container Entrypoint
# Location: docker/entrypoint.sh (Inside Container)
# Permissions: chmod +x (755)
# Authority: /home/vpsg24gb/Documents/Structure/03_SECURE_ISOLATION_VAULT.md
# ==============================================================================
set -euo pipefail

echo "[+] Initializing HistorySnooze Container Sandbox..."

# 1. User Validation & Non-Root Enforcement
CURRENT_UID="$(id -u)"
CURRENT_GID="$(id -g)"
CURRENT_USER="$(id -un 2>/dev/null || echo "uid-${CURRENT_UID}")"

if [ "$CURRENT_UID" -eq 0 ]; then
    echo "[-] [SECURITY ALERT] Container is running as root (UID 0)!" >&2
    if [ "${STRICT_NON_ROOT:-1}" = "1" ]; then
        echo "[-] Execution aborted: Non-root UID 1000 required by 03_SECURE_ISOLATION_VAULT.md." >&2
        echo "[-] To bypass for debugging only, set STRICT_NON_ROOT=0." >&2
        exit 1
    fi
else
    echo "[✓] User identity verified: ${CURRENT_USER} (UID: ${CURRENT_UID}, GID: ${CURRENT_GID})"
fi

# 2. Shared Memory (/dev/shm) Writable & In-Memory Vault Setup
SHM_TEST_FILE="/dev/shm/.write_test_$$"
if ! touch "$SHM_TEST_FILE" 2>/dev/null; then
    echo "[-] [ERROR] /dev/shm is not writable by ${CURRENT_USER} (UID: ${CURRENT_UID})!" >&2
    exit 1
fi
rm -f "$SHM_TEST_FILE"

RAM_VAULT_DIR="/dev/shm/.vault"
mkdir -p "$RAM_VAULT_DIR" 2>/dev/null || true
chmod 700 "$RAM_VAULT_DIR" 2>/dev/null || true

# In-Memory Vault Decryption if encrypted vault file exists
VAULT_FILE=""
for candidate in "/workspace/credentials/project_vault.enc" "/workspace/.secrets/project_vault.enc"; do
    if [ -f "$candidate" ]; then
        VAULT_FILE="$candidate"
        break
    fi
done

if [ -n "$VAULT_FILE" ]; then
    if [ -n "${MASTER_VAULT_PASS:-}" ]; then
        echo "[+] Decrypting encrypted vault to RAM-Only storage (/dev/shm/.vault)..."
        openssl enc -aes-256-cbc -d -salt -pbkdf2 -in "$VAULT_FILE" \
            -out "$RAM_VAULT_DIR/secrets.json" -pass env:MASTER_VAULT_PASS
        chmod 600 "$RAM_VAULT_DIR/secrets.json"
        export VAULT_SECRETS_FILE="$RAM_VAULT_DIR/secrets.json"
        echo "[✓] In-Memory Vault decrypted successfully (Zero-Leak)."
    else
        echo "[!] [WARN] Found $VAULT_FILE but MASTER_VAULT_PASS is not set. Skipping decryption." >&2
    fi
fi

# 3. Read-Only Credentials Verification & Environment Binding
for sec_dir in "/workspace/credentials" "/workspace/.secrets"; do
    if [ -d "$sec_dir" ]; then
        PROBE_FILE="${sec_dir}/.probe_write_$$"
        if touch "$PROBE_FILE" 2>/dev/null; then
            rm -f "$PROBE_FILE"
            echo "[!] [SECURITY WARN] ${sec_dir} is WRITABLE! Mount must be strictly read-only (:ro)." >&2
        else
            echo "[✓] Verified ${sec_dir} mounted read-only (:ro)."
        fi
        
        # Auto-bind standard credential paths if unconfigured
        [ -f "${sec_dir}/gdrive/token.json" ] && [ -z "${GDRIVE_TOKEN_PATH:-}" ] && \
            export GDRIVE_TOKEN_PATH="${sec_dir}/gdrive/token.json"
        [ -f "${sec_dir}/telegram/bot_token.txt" ] && [ -z "${TELEGRAM_BOT_TOKEN_PATH:-}" ] && \
            export TELEGRAM_BOT_TOKEN_PATH="${sec_dir}/telegram/bot_token.txt"
    fi
done

# 4. Runtime Environment Standardization
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="/workspace:${PYTHONPATH:-}"
export PATH="/home/appuser/.local/bin:/usr/local/bin:${PATH:-}"
umask 027

# Headless Chrome path resolution for gflow Playwright
if [ -z "${GFLOW_CHROME_PATH:-}" ]; then
    if command -v google-chrome >/dev/null 2>&1; then
        export GFLOW_CHROME_PATH="$(command -v google-chrome)"
    elif command -v chromium >/dev/null 2>&1; then
        export GFLOW_CHROME_PATH="$(command -v chromium)"
    fi
fi

echo "[✓] Environment initialized. Executing container process..."

# 5. Signal Propagation & Clean Process Execution
if [ $# -eq 0 ]; then
    exec /bin/bash
else
    exec "$@"
fi
