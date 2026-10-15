#!/usr/bin/env bash
#
# Ghost-Rider - native Ubuntu 22.04 LTS EC2 deployment (no Docker).
#
# Idempotent: re-running it after a git pull reinstalls dependencies, refreshes
# the model weights, rewrites the systemd unit and restarts the service.
#
# Usage
# -----
#   sudo bash backend/scripts/deploy_ec2_native.sh                 # full deploy
#   sudo bash backend/scripts/deploy_ec2_native.sh --dry-run       # show every action
#   sudo bash backend/scripts/deploy_ec2_native.sh --workers 1     # small instance (1 GB RAM)
#   sudo bash backend/scripts/deploy_ec2_native.sh --skip-apt --skip-deps   # code-only update
#
set -Eeuo pipefail
IFS=$'\n\t'

# --------------------------------------------------------------------------- #
# Defaults / derived paths
# --------------------------------------------------------------------------- #
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"                       # .../Ghost-Rider/backend
REPO_DIR="$(cd "${APP_DIR}/.." && pwd)"                         # .../Ghost-Rider
VENV_DIR="${APP_DIR}/venv"
REQUIREMENTS="${APP_DIR}/requirements.txt"
UNIT_SRC="${SCRIPT_DIR}/ghost-rider.service"
ENV_FILE="${APP_DIR}/.env"
WEIGHTS_FILE="${APP_DIR}/yolov8n-seg.pt"
WEIGHTS_URL="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n-seg.pt"
SERVICE_NAME="ghost-rider"
PORT="8000"
HOST="0.0.0.0"
WORKERS="2"
READY_RETRIES="30"
SERVICE_USER=""
PIP_INDEX_ARGS=""

DRY_RUN="false"
SKIP_APT="false"
SKIP_DEPS="false"
SKIP_MODEL="false"
NO_START="false"

# --------------------------------------------------------------------------- #
# Logging helpers
# --------------------------------------------------------------------------- #
if [[ -t 1 ]]; then
  C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_RED=$'\033[31m'
  C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_BLUE=$'\033[34m'
else
  C_RESET=""; C_BOLD=""; C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""
fi

log()  { printf '%s[%s]%s %s\n' "${C_BLUE}" "$(date +%H:%M:%S)" "${C_RESET}" "$*"; }
ok()   { printf '%s[ ok ]%s %s\n' "${C_GREEN}" "${C_RESET}" "$*"; }
warn() { printf '%s[warn]%s %s\n' "${C_YELLOW}" "${C_RESET}" "$*" >&2; }
die()  { printf '%s[fail]%s %s\n' "${C_RED}" "${C_RESET}" "$*" >&2; exit 1; }
step() { printf '\n%s==> %s%s\n' "${C_BOLD}" "$*" "${C_RESET}"; }

run() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    # Join with spaces explicitly: "$*" would join with IFS[0] (a newline here).
    local rendered
    rendered="$(printf '%s ' "$@")"
    printf '   [dry-run] %s\n' "${rendered% }"
    return 0
  fi
  "$@"
}

run_sh() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    printf '   [dry-run] bash -c %s\n' "$1"
    return 0
  fi
  bash -c "$1"
}

usage() {
  cat <<'USAGEEOF'
Ghost-Rider - native Ubuntu 22.04 LTS EC2 deployment (no Docker).

Idempotent: re-running it after a git pull reinstalls dependencies, refreshes
the model weights, rewrites the systemd unit and restarts the service.

Usage:
  sudo bash backend/scripts/deploy_ec2_native.sh                 # full deploy
  sudo bash backend/scripts/deploy_ec2_native.sh --dry-run       # show every action
  sudo bash backend/scripts/deploy_ec2_native.sh --workers 1     # 1 GB instance
  sudo bash backend/scripts/deploy_ec2_native.sh --skip-apt --skip-deps  # code-only update
USAGEEOF
  cat <<'EOF'

Options:
  --dry-run              print every action without changing the system
  --skip-apt             do not touch system packages
  --skip-deps            do not (re)install Python dependencies
  --skip-model           do not pre-download the YOLO weights
  --no-start             install/enable the unit but do not start it
  --user NAME            service user (default: owner of the backend directory)
  --port N               listen port (default 8000)
  --workers N            uvicorn workers (default 2; use 1 on a 1 GB instance)
  --weights-url URL      fallback download URL for yolov8n-seg.pt
  --index-url URL        forwarded to pip (private mirrors / VPC endpoints)
  -h, --help             this help
EOF
}

# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)         DRY_RUN="true"; shift ;;
    --skip-apt)        SKIP_APT="true"; shift ;;
    --skip-deps)       SKIP_DEPS="true"; shift ;;
    --skip-model)      SKIP_MODEL="true"; shift ;;
    --no-start)        NO_START="true"; shift ;;
    --user)            SERVICE_USER="${2:?--user needs a value}"; shift 2 ;;
    --port)            PORT="${2:?--port needs a value}"; shift 2 ;;
    --workers)         WORKERS="${2:?--workers needs a value}"; shift 2 ;;
    --weights-url)     WEIGHTS_URL="${2:?--weights-url needs a value}"; shift 2 ;;
    --index-url)       PIP_INDEX_ARGS="--index-url ${2:?--index-url needs a value}"; shift 2 ;;
    -h|--help)         usage; exit 0 ;;
    *)                 die "unknown option: $1 (use --help)" ;;
  esac
done

[[ "${PORT}" =~ ^[0-9]+$ ]] || die "--port must be numeric (got '${PORT}')"
[[ "${WORKERS}" =~ ^[1-9][0-9]*$ ]] || die "--workers must be a positive integer (got '${WORKERS}')"

# --------------------------------------------------------------------------- #
# Pre-flight
# --------------------------------------------------------------------------- #
step "Pre-flight checks"
log "repository      : ${REPO_DIR}"
log "application dir : ${APP_DIR}"
log "virtualenv      : ${VENV_DIR}"
log "service         : ${SERVICE_NAME} (port ${PORT}, ${WORKERS} worker(s))"
log "dry run         : ${DRY_RUN}"

[[ -f "${REQUIREMENTS}" ]] || die "requirements.txt not found at ${REQUIREMENTS}"
[[ -f "${UNIT_SRC}" ]] || die "systemd unit template not found at ${UNIT_SRC}"

if [[ "${DRY_RUN}" != "true" && "${EUID}" -ne 0 ]]; then
  die "run this script with sudo (it installs system packages and a systemd unit)"
fi

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  log "host OS         : ${PRETTY_NAME:-unknown}"
  if [[ "${ID:-}" != "ubuntu" ]]; then
    warn "this script targets Ubuntu 22.04 LTS; '${ID:-unknown}' detected - continuing anyway"
  elif [[ "${VERSION_ID:-}" != "22.04" ]]; then
    warn "Ubuntu ${VERSION_ID:-?} detected; the package list is tuned for 22.04"
  fi
fi

if [[ -z "${SERVICE_USER}" ]]; then
  SERVICE_USER="$(stat -c '%U' "${APP_DIR}" 2>/dev/null || true)"
  SERVICE_USER="${SERVICE_USER:-ubuntu}"
fi
if [[ "${SERVICE_USER}" =~ [[:space:]] ]]; then
  # A name with whitespace cannot be expressed in a systemd unit line.
  warn "service user '${SERVICE_USER}' contains whitespace; falling back to 'ubuntu'"
  SERVICE_USER="ubuntu"
fi
if [[ "${DRY_RUN}" != "true" ]] && ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  die "service user '${SERVICE_USER}' does not exist (pass --user NAME)"
fi
log "service user    : ${SERVICE_USER}"

# --------------------------------------------------------------------------- #
# 1. System packages (OpenCV/Boto3 runtime deps)
# --------------------------------------------------------------------------- #
step "1/8 System packages"
# Kept as a single space separated string on purpose: IFS is narrowed above, so
# "${array[*]}" would join elements with newlines and break apt-get.
APT_PACKAGES="python3-pip python3-venv python3-dev build-essential libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender1 curl ca-certificates unzip"
if [[ "${SKIP_APT}" == "true" ]]; then
  log "skipped (--skip-apt)"
else
  run_sh "DEBIAN_FRONTEND=noninteractive apt-get update -y"
  run_sh "DEBIAN_FRONTEND=noninteractive apt-get install -y ${APT_PACKAGES[*]}"
  ok "installed: ${APT_PACKAGES[*]}"
fi

# python3 must be >= 3.10 (the code uses PEP 604 unions and match-free 3.10 syntax)
if command -v python3 >/dev/null 2>&1; then
  PY_VERSION="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo unknown)"
  log "python3         : ${PY_VERSION}"
  set +e
  python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null
  PY_CHECK_RC=$?
  set -e
  if [[ ${PY_CHECK_RC} -eq 1 ]]; then
    die "python3 >= 3.10 is required (found ${PY_VERSION})"
  elif [[ ${PY_CHECK_RC} -ne 0 ]]; then
    warn "could not run python3 (exit ${PY_CHECK_RC}); continuing - verify the interpreter manually"
  fi
else
  warn "python3 is not on PATH"
fi

# --------------------------------------------------------------------------- #
# 2. Virtual environment
# --------------------------------------------------------------------------- #
step "2/8 Python virtual environment"
if [[ -d "${VENV_DIR}" && -x "${VENV_DIR}/bin/python" ]]; then
  log "existing virtualenv reused: ${VENV_DIR}"
else
  run python3 -m venv "${VENV_DIR}"
  ok "created ${VENV_DIR}"
fi

# --------------------------------------------------------------------------- #
# 3. Dependencies
# --------------------------------------------------------------------------- #
step "3/8 Python dependencies"
if [[ "${SKIP_DEPS}" == "true" ]]; then
  log "skipped (--skip-deps)"
else
  run_sh "'${VENV_DIR}/bin/python' -m pip install --upgrade ${PIP_INDEX_ARGS} pip setuptools wheel"
  run_sh "'${VENV_DIR}/bin/python' -m pip install ${PIP_INDEX_ARGS} -r '${REQUIREMENTS}'"
  ok "dependencies installed from ${REQUIREMENTS}"
  # ultralytics pulls torch (CPU wheel is ~200 MB) - surface the versions for support tickets
  run_sh "'${VENV_DIR}/bin/python' -c \"import fastapi, uvicorn, boto3, cv2, torch; print('  fastapi', fastapi.__version__, '| uvicorn', uvicorn.__version__, '| boto3', boto3.__version__, '| opencv', cv2.__version__, '| torch', torch.__version__)\"" || \
    warn "could not import every dependency - check the log above"
fi

# --------------------------------------------------------------------------- #
# 4. Model weights (zero-latency first request)
# --------------------------------------------------------------------------- #
step "4/8 YOLOv8 segmentation weights"
if [[ -f "${WEIGHTS_FILE}" ]]; then
  log "weights already present: ${WEIGHTS_FILE} ($(du -h "${WEIGHTS_FILE}" | cut -f1))"
elif [[ "${SKIP_MODEL}" == "true" ]]; then
  log "skipped (--skip-model); ultralytics will download on first use"
else
  if ! run_sh "cd '${APP_DIR}' && '${VENV_DIR}/bin/python' -c \"from ultralytics import YOLO; YOLO('yolov8n-seg.pt'); print('downloaded via ultralytics')\""; then
    warn "ultralytics download failed - falling back to ${WEIGHTS_URL}"
    run_sh "curl -fL --retry 3 --retry-delay 2 -o '${WEIGHTS_FILE}' '${WEIGHTS_URL}'" \
      || warn "weight download failed; the API still starts and downloads on first request"
  fi
  if [[ -f "${WEIGHTS_FILE}" ]]; then
    ok "weights ready: ${WEIGHTS_FILE} ($(du -h "${WEIGHTS_FILE}" | cut -f1))"
  else
    warn "weights missing after deploy - first inference request will be slower"
  fi
fi

# --------------------------------------------------------------------------- #
# 5. .env (systemd EnvironmentFile must exist)
# --------------------------------------------------------------------------- #
step "5/8 Environment file"
if [[ -f "${ENV_FILE}" ]]; then
  log "kept existing ${ENV_FILE}"
  if ! grep -qE '^[[:space:]]*AWS_ACCESS_KEY_ID=[^[:space:]]' "${ENV_FILE}" 2>/dev/null; then
    warn "AWS_ACCESS_KEY_ID looks unset in ${ENV_FILE}: S3 and Bedrock will run in fallback mode"
  fi
else
  if [[ "${DRY_RUN}" == "true" ]]; then
    log "[dry-run] would create ${ENV_FILE} with AWS placeholders"
  else
    umask 077
    cat > "${ENV_FILE}" <<'ENVEOF'
# Ghost-Rider backend configuration (systemd EnvironmentFile)
# Fill in real credentials, then: sudo systemctl restart ghost-rider
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=ap-south-1
AWS_S3_BUCKET_NAME=ghost-rider-road-storage
BEDROCK_MODEL_ID=amazon.nova-micro-v1:0
YOLO_WEIGHTS_PATH=yolov8n-seg.pt
# CAMERA_MOUNT_PITCH_DEG is the NOMINAL mounting angle. The imu.pitch_deg sent
# with each upload must be the DEVIATION from that nominal angle (the pipeline
# adds the two to get the absolute tilt used by the ground-plane physics, and
# scores the deviation). If your device reports ABSOLUTE pitch instead, set
# CAMERA_MOUNT_PITCH_DEG=0.0 so the value is not counted twice.
CAMERA_MOUNT_PITCH_DEG=25.0
CAMERA_HEIGHT_M=1.3
PORT=8000
LOG_LEVEL=INFO
ENVEOF
    chmod 600 "${ENV_FILE}"
    chown "${SERVICE_USER}:${SERVICE_USER}" "${ENV_FILE}" 2>/dev/null || true
    ok "created ${ENV_FILE} (mode 600) - add your AWS credentials before going live"
  fi
fi

# Ensure the uploads directory exists and is owned by the service user.
run_sh "mkdir -p '${APP_DIR}/uploads'"
run_sh "chown -R '${SERVICE_USER}:${SERVICE_USER}' '${APP_DIR}/uploads'" || true

# --------------------------------------------------------------------------- #
# 6. systemd unit
# --------------------------------------------------------------------------- #
step "6/8 systemd unit"
UNIT_DEST="/etc/systemd/system/${SERVICE_NAME}.service"
if [[ "${DRY_RUN}" == "true" ]]; then
  log "[dry-run] would install ${UNIT_SRC} -> ${UNIT_DEST} for user=${SERVICE_USER} port=${PORT} workers=${WORKERS}"
else
  install -m 0644 "${UNIT_SRC}" "${UNIT_DEST}"
  # Rewrite the canonical /home/ubuntu paths so the unit works wherever the repo lives.
  sed -i \
    -e "s|^User=.*|User=${SERVICE_USER}|" \
    -e "s|^WorkingDirectory=.*|WorkingDirectory=${APP_DIR}|" \
    -e "s|^EnvironmentFile=.*|EnvironmentFile=-${ENV_FILE}|" \
    -e "s|^ExecStart=.*|ExecStart=${VENV_DIR}/bin/uvicorn main:app --host ${HOST} --port ${PORT} --workers ${WORKERS}|" \
    "${UNIT_DEST}"
  ok "installed ${UNIT_DEST}"
  run systemctl daemon-reload
  log "unit contents:"
  sed 's/^/    /' "${UNIT_DEST}"
fi

# --------------------------------------------------------------------------- #
# 7. Enable + (re)start
# --------------------------------------------------------------------------- #
step "7/8 Enable and start the service"
if [[ "${NO_START}" == "true" ]]; then
  run systemctl enable "${SERVICE_NAME}" || warn "could not enable ${SERVICE_NAME}"
  log "not started (--no-start)"
else
  run systemctl enable "${SERVICE_NAME}" || warn "could not enable ${SERVICE_NAME}"
  # restart is idempotent for both a fresh install and a code update
  run systemctl restart "${SERVICE_NAME}" || die "could not start ${SERVICE_NAME} (see: journalctl -u ${SERVICE_NAME} -n 50)"
fi

# --------------------------------------------------------------------------- #
# 8. Readiness + connection details
# --------------------------------------------------------------------------- #
step "8/8 Readiness check"
READY="false"
if [[ "${DRY_RUN}" == "true" ]]; then
  log "[dry-run] would poll http://127.0.0.1:${PORT}/health"
elif [[ "${NO_START}" == "true" ]]; then
  log "skipped (--no-start)"
else
  for attempt in $(seq 1 "${READY_RETRIES}"); do
    if curl -fsS --max-time 3 "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
      READY="true"
      ok "service answered /health after ${attempt} attempt(s)"
      break
    fi
    sleep 2
  done
  if [[ "${READY}" != "true" ]]; then
    warn "service did not answer /health within $((READY_RETRIES * 2))s"
    systemctl --no-pager -l status "${SERVICE_NAME}" || true
    journalctl -u "${SERVICE_NAME}" -n 60 --no-pager || true
    die "deployment incomplete - fix the error above and re-run the script"
  fi
fi

# Public IP: IMDSv2 (token first), then a public fallback, then the local address.
PUBLIC_IP="<ec2-public-ip>"
if [[ "${DRY_RUN}" != "true" ]]; then
  IMDS_TOKEN="$(curl -sS --max-time 2 -X PUT "http://169.254.169.254/latest/api/token" \
      -H "X-aws-ec2-metadata-token-ttl-seconds: 60" 2>/dev/null || true)"
  if [[ -n "${IMDS_TOKEN}" ]]; then
    PUBLIC_IP="$(curl -sS --max-time 2 -H "X-aws-ec2-metadata-token: ${IMDS_TOKEN}" \
        http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || true)"
  fi
  [[ -n "${PUBLIC_IP}" ]] || PUBLIC_IP="$(curl -sS --max-time 3 https://checkip.amazonaws.com 2>/dev/null | tr -d '[:space:]' || true)"
  [[ -n "${PUBLIC_IP}" ]] || PUBLIC_IP="<ec2-public-ip>"
fi

# --------------------------------------------------------------------------- #
# Summary
# --------------------------------------------------------------------------- #
printf '\n%s================================================================%s\n' "${C_BOLD}" "${C_RESET}"
if [[ "${DRY_RUN}" == "true" ]]; then
  printf '%s DRY RUN COMPLETE - nothing was changed%s\n' "${C_BOLD}" "${C_RESET}"
else
  printf '%s DEPLOYMENT COMPLETE%s\n' "${C_BOLD}" "${C_RESET}"
fi
printf '%s================================================================%s\n' "${C_BOLD}" "${C_RESET}"
printf '  app dir        : %s\n' "${APP_DIR}"
printf '  venv           : %s\n' "${VENV_DIR}"
printf '  env file       : %s\n' "${ENV_FILE}"
printf '  service        : %s (workers=%s, port=%s, user=%s)\n' "${SERVICE_NAME}" "${WORKERS}" "${PORT}" "${SERVICE_USER}"
printf '  swagger docs   : http://%s:%s/docs\n' "${PUBLIC_IP}" "${PORT}"
printf '  health (local) : http://127.0.0.1:%s/health\n' "${PORT}"
printf '  deep health    : http://127.0.0.1:%s/health/deep\n' "${PORT}"
printf '\nUseful commands\n'
printf '  systemctl status %s\n' "${SERVICE_NAME}"
printf '  journalctl -u %s -f\n' "${SERVICE_NAME}"
printf '  sudo systemctl restart %s        # after a git pull + this script\n' "${SERVICE_NAME}"
printf '  curl -s http://127.0.0.1:%s/health/deep | python3 -m json.tool\n' "${PORT}"
printf '\nSecurity reminder: open port %s in the EC2 security group only to the\n' "${PORT}"
printf 'app/mobile egress range, and prefer a reverse proxy with TLS for production.\n'

if [[ "${DRY_RUN}" != "true" ]]; then
  printf '\n--- systemctl status %s ---\n' "${SERVICE_NAME}"
  systemctl --no-pager -l status "${SERVICE_NAME}" || true
fi

exit 0
