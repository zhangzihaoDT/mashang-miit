#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8790}"
RUN_DIR="$ROOT/runs/workbench"
PID_FILE="$RUN_DIR/miit.pid"
LOG_FILE="$RUN_DIR/server.log"

pid_of() { [[ -f "$PID_FILE" ]] && read -r pid < "$PID_FILE" && printf '%s' "$pid" || true; }
listening() { lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; }
canonical_listener_pid() {
  local candidate
  for candidate in $(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true); do
    if command_matches "$candidate"; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  return 1
}
command_matches() {
  local pid="$1" command
  command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  [[ "$command" == *"scripts/workbench_server.py --port $PORT"* ]]
}
running() {
  local pid
  pid="$(pid_of)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null && command_matches "$pid"
}
pick_python() {
  for candidate in "$ROOT/.venv/bin/python" "$ROOT/venv/bin/python"; do
    [[ -x "$candidate" ]] && { printf '%s' "$candidate"; return; }
  done
  command -v python3 || true
}

start() {
  if running; then
    printf 'MIIT workbench already running (pid %s) → http://127.0.0.1:%s\n' "$(pid_of)" "$PORT"
    return 0
  fi
  local external_pid
  external_pid="$(canonical_listener_pid || true)"
  if [[ -n "$external_pid" ]]; then
    printf 'MIIT workbench already running outside this launcher (pid %s) → http://127.0.0.1:%s\n' "$external_pid" "$PORT"
    return 0
  fi
  if listening; then
    printf 'Port %s is occupied by an unmanaged process; refusing to replace it.\n' "$PORT" >&2
    return 1
  fi
  local python
  python="$(pick_python)"
  if [[ -z "$python" ]]; then
    printf 'Python 3 is not available.\n' >&2
    return 1
  fi
  mkdir -p "$RUN_DIR"
  (cd "$ROOT" && exec "$python" "$ROOT/scripts/workbench_server.py" --port "$PORT") >"$LOG_FILE" 2>&1 &
  local pid=$!
  printf '%s\n' "$pid" > "$PID_FILE"
  for _ in $(seq 1 50); do
    if curl -fsS --max-time 1 "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
      printf 'MIIT workbench started (pid %s) → http://127.0.0.1:%s\n' "$pid" "$PORT"
      return 0
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$PID_FILE"
      printf 'MIIT workbench failed to start; see %s\n' "$LOG_FILE" >&2
      return 1
    fi
    sleep 0.2
  done
  printf 'MIIT workbench did not become ready; see %s\n' "$LOG_FILE" >&2
  return 1
}

stop() {
  local pid
  pid="$(pid_of)"
  if ! { [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null && command_matches "$pid"; }; then
    pid="$(canonical_listener_pid || true)"
  fi
  if [[ -n "$pid" ]]; then
    kill -TERM "$pid" 2>/dev/null || true
    for _ in $(seq 1 40); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.2
    done
    if kill -0 "$pid" 2>/dev/null && command_matches "$pid"; then
      kill -KILL "$pid" 2>/dev/null || true
    fi
    printf 'MIIT workbench stopped (pid %s).\n' "$pid"
  elif listening; then
    printf 'Port %s is occupied by an unmanaged process; refusing to stop it.\n' "$PORT" >&2
    return 1
  else
    printf 'MIIT workbench is not running.\n'
  fi
  rm -f "$PID_FILE"
  if listening; then
    printf 'Port %s is still occupied.\n' "$PORT" >&2
    return 1
  fi
}

status() {
  if running; then
    printf 'ONLINE · MIIT workbench pid %s · http://127.0.0.1:%s\n' "$(pid_of)" "$PORT"
  elif [[ -n "$(canonical_listener_pid || true)" ]]; then
    printf 'ONLINE · canonical MIIT process is not tracked by this launcher · http://127.0.0.1:%s\n' "$PORT"
  elif listening; then
    printf 'ONLINE · unmanaged process on port %s\n' "$PORT"
    return 2
  else
    printf 'OFFLINE · http://127.0.0.1:%s\n' "$PORT"
  fi
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  restart) stop && start ;;
  status) status ;;
  logs) [[ -f "$LOG_FILE" ]] && tail -n 80 "$LOG_FILE" || printf 'No MIIT workbench log yet.\n' ;;
  *) printf 'Usage: %s {start|stop|restart|status|logs}\n' "$0" >&2; exit 2 ;;
esac
