#!/usr/bin/env bash

set -euo pipefail

MAX_REMEDIATION_ATTEMPTS="${MAX_REMEDIATION_ATTEMPTS:-2}"

log() {
  printf '[self-heal] %s\n' "$*"
}

bootstrap_dependencies() {
  log "Bootstrapping backend dependencies"
  python -m pip install --upgrade pip
  pip install -e ".[dev]"

  log "Attempting optional scientific dependencies (best effort)"
  pip install gemmi mdanalysis freesasa || true

  if [[ -d frontend ]]; then
    log "Bootstrapping frontend dependencies"
    pushd frontend >/dev/null
    npm ci --no-audit --no-fund
    popd >/dev/null
  fi
}

run_checks() {
  log "Running Python lint"
  ruff check .

  log "Running backend tests"
  pytest -q

  if [[ -d frontend ]]; then
    log "Running frontend build"
    pushd frontend >/dev/null
    npm run build
    popd >/dev/null
  fi
}

apply_auto_fixes() {
  log "Applying safe auto-fixes"
  ruff check . --fix || true
  ruff format . || true

  if [[ -d frontend ]]; then
    pushd frontend >/dev/null
    npm ci --no-audit --no-fund || true
    popd >/dev/null
  fi
}

main() {
  bootstrap_dependencies

  local remediation_count=0
  while true; do
    if run_checks; then
      log "CI checks passed"
      return 0
    fi

    if (( remediation_count >= MAX_REMEDIATION_ATTEMPTS )); then
      log "CI checks still failing after ${MAX_REMEDIATION_ATTEMPTS} remediation attempts"
      return 1
    fi

    remediation_count=$((remediation_count + 1))
    log "Attempting remediation ${remediation_count}/${MAX_REMEDIATION_ATTEMPTS}"
    apply_auto_fixes
  done
}

main "$@"
