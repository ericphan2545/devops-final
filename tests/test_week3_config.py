"""Offline static and isolated unit checks for Week 3 Steps 1-3 (no DB, Docker, sudo, Git, or network calls)."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import psycopg
import pytest
import app.app as app_module
from app.app import app

REPO_ROOT = Path(__file__).resolve().parents[1]

FAKE_WEBHOOK_1 = (
    "https://discord.com/api/webhooks/123456789012345678/"
    "FakeWebhookTokenAlpha_0123456789abcdefghijklmnopqrstuvwxyz"
)
FAKE_WEBHOOK_2 = (
    "https://discordapp.com/api/webhooks/987654321098765432/"
    "FakeWebhookTokenBeta_9876543210zyxwvutsrqponmlkjihgfedcba"
)


def _extract_metric(body, name):
    match = re.search(rf"^{re.escape(name)}\s+([-+]?[0-9]*\.?[0-9]+)$", body, re.M)
    assert match is not None, f"Metric {name} missing from /metrics"
    return float(match.group(1))


def _get_usable_bash():
    candidates = []
    if os.name == "nt":
        for git_bash in (
            Path(r"C:\Program Files\Git\bin\bash.exe"),
            Path(r"C:\Program Files\Git\usr\bin\bash.exe"),
        ):
            if git_bash.exists():
                candidates.append(str(git_bash))
    which_bash = shutil.which("bash")
    if which_bash:
        norm = which_bash.replace("/", "\\").lower()
        # Exclude Windows WSL launcher stub (C:\Windows\System32\bash.exe), which strips
        # non-WSLENV environment variables and expects /mnt/c paths instead of C:/ paths.
        if not (os.name == "nt" and norm.endswith(r"\system32\bash.exe")):
            if which_bash not in candidates:
                candidates.append(which_bash)

    last_err = ""
    for candidate in candidates:
        try:
            probe = subprocess.run(
                [candidate, "-c", "exit 0"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if probe.returncode == 0:
                return candidate
            last_err = (probe.stderr or probe.stdout or "").strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            last_err = str(exc)

    if os.name == "nt" and ("NtCreateDirectoryObject" in last_err or "0xC0000022" in last_err):
        pytest.skip("Git Bash MSYS2 shared memory is blocked inside Windows sandbox")
    pytest.fail(f"Usable bash interpreter is required for shell branch tests (last error: {last_err})")


class _DummyConn:
    def __init__(self):
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query):
        self.queries.append(query)
        return self


def test_mocked_db_ok_and_metrics_gauge_when_connected_and_failed(monkeypatch):
    app.config["TESTING"] = True
    dummy = _DummyConn()
    monkeypatch.setattr(app_module, "get_db", lambda: dummy)

    with app.test_client() as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.get_json() == {"status": "ok"}
        assert health.headers["Cache-Control"] == "no-store"

        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        text = metrics.get_data(as_text=True)
        assert _extract_metric(text, "todo_db_up") == 1.0
        assert "flask_http_request_total" in text
        assert "SELECT 1" in dummy.queries

    def fail_db():
        raise psycopg.OperationalError("simulated db outage")

    monkeypatch.setattr(app_module, "get_db", fail_db)
    with app.test_client() as client:
        health = client.get("/health")
        assert health.status_code == 500
        assert health.get_json() == {"status": "error", "detail": "cannot connect to database"}
        assert health.headers["Cache-Control"] == "no-store"

        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert _extract_metric(metrics.get_data(as_text=True), "todo_db_up") == 0.0


def test_entrypoint_runs_only_single_worker_gunicorn_without_migration():
    entrypoint = (REPO_ROOT / "app" / "entrypoint.sh").read_text(encoding="utf-8")
    assert "migrate.py" not in entrypoint
    assert "exec gunicorn" in entrypoint
    assert "--workers 1" in entrypoint


def test_compose_has_seven_services_directory_mounts_and_single_public_port():
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    expected_services = ("db", "app", "prometheus", "alertmanager", "node-exporter", "grafana", "nginx")
    # Slice strictly inside top-level 'services:' block (between 'services:' and 'volumes:').
    services_section = compose.split("\nservices:\n", 1)[1].split("\nvolumes:\n", 1)[0]
    found_services = re.findall(r"^  ([a-z0-9-]+):\s*$", services_section, re.M)
    assert tuple(found_services) == expected_services

    assert 'max-size: "10m"' in compose
    assert 'max-file: "3"' in compose
    assert compose.count("logging: *default-logging") == 7

    # Only nginx may declare 'ports:'.
    assert services_section.count("    ports:\n") == 1
    nginx_block = services_section.split("  nginx:\n", 1)[1]
    assert '      - "80:80"' in nginx_block

    # App service must receive least-privilege credentials, never admin POSTGRES_USER/PASSWORD.
    app_block = services_section.split("  app:\n", 1)[1].split("\n  prometheus:\n", 1)[0]
    assert "DB_USER: ${APP_DB_USER}" in app_block
    assert "DB_PASSWORD: ${APP_DB_PASSWORD}" in app_block
    assert "POSTGRES_USER" not in app_block
    assert "POSTGRES_PASSWORD" not in app_block

    # Directory mounts (read-only) to avoid stale single-file bind-mount inodes after git pull.
    assert "./monitoring/prometheus:/etc/prometheus:ro" in compose
    assert "./monitoring/alertmanager:/etc/alertmanager:ro" in compose
    assert "./secrets:/etc/alertmanager-secrets:ro" in compose
    assert "./monitoring/grafana/provisioning:/etc/grafana/provisioning:ro" in compose
    assert "./monitoring/grafana/dashboards:/etc/grafana/dashboards:ro" in compose
    assert "./nginx:/etc/nginx/conf.d:ro" in compose

    # Preserve existing db-data volume and ordered bootstrap scripts for fresh DB.
    assert "db-data:/var/lib/postgresql/data" in compose
    assert "./db/init.sql:/docker-entrypoint-initdb.d/10-init.sql:ro" in compose
    assert "./db/app-user.sh:/docker-entrypoint-initdb.d/20-app-user.sh:ro" in compose


def test_monitoring_and_nginx_paths_are_consistent():
    prom_cfg = (REPO_ROOT / "monitoring" / "prometheus" / "prometheus.yml").read_text(encoding="utf-8")
    alerts_cfg = (REPO_ROOT / "monitoring" / "prometheus" / "alerts.yml").read_text(encoding="utf-8")
    am_cfg = (REPO_ROOT / "monitoring" / "alertmanager" / "alertmanager.yml").read_text(encoding="utf-8")
    nginx_cfg = (REPO_ROOT / "nginx" / "default.conf").read_text(encoding="utf-8")
    deploy_sh = (REPO_ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    prep_sh = (REPO_ROOT / "scripts" / "prepare-step1.sh").read_text(encoding="utf-8")
    ci_cfg = (REPO_ROOT / ".github" / "workflows" / "ci-cd.yml").read_text(encoding="utf-8")

    assert "scrape_interval: 15s" in prom_cfg
    assert "evaluation_interval: 15s" in prom_cfg
    assert "/etc/prometheus/alerts.yml" in prom_cfg
    for job in ("job_name: prometheus", "job_name: app", "job_name: node"):
        assert job in prom_cfg

    for alert in ("alert: AppDown", "alert: DatabaseDown", "alert: HighMemory"):
        assert alert in alerts_cfg
    assert 'up{job="app"} == 0' in alerts_cfg
    assert 'todo_db_up{job="app"} == 0' in alerts_cfg

    webhook_container_path = "/etc/alertmanager-secrets/discord_webhook_url"
    assert f"webhook_url_file: {webhook_container_path}" in am_cfg
    assert "send_resolved: true" in am_cfg
    assert webhook_container_path in deploy_sh
    assert webhook_container_path in prep_sh

    # CI must validate using directory mounts matching Compose.
    assert "$PWD/monitoring/prometheus:/etc/prometheus:ro" in ci_cfg
    assert "$PWD/monitoring/alertmanager:/etc/alertmanager:ro" in ci_cfg

    # Nginx must block /metrics, proxy /grafana/ + Grafana Live WS without stripping subpath, and keep / -> app:8000.
    assert "location = /metrics" in nginx_cfg and "deny all;" in nginx_cfg
    assert "location /grafana/api/live/" in nginx_cfg
    assert "proxy_set_header Upgrade $http_upgrade;" in nginx_cfg
    assert "location /grafana/" in nginx_cfg
    assert "proxy_pass http://grafana:3000;" in nginx_cfg
    assert "proxy_pass http://grafana:3000/;" not in nginx_cfg
    assert "proxy_pass http://app:8000;" in nginx_cfg


def test_grafana_provisioning_and_dashboards_match_metrics_and_nodata_rules():
    ds_cfg = (REPO_ROOT / "monitoring" / "grafana" / "provisioning" / "datasources" / "prometheus.yml").read_text(encoding="utf-8")
    db_prov = (REPO_ROOT / "monitoring" / "grafana" / "provisioning" / "dashboards" / "dashboards.yml").read_text(encoding="utf-8")

    assert "uid: prometheus" in ds_cfg
    assert "url: http://prometheus:9090" in ds_cfg
    assert "path: /etc/grafana/dashboards" in db_prov

    todo_dash = json.loads((REPO_ROOT / "monitoring" / "grafana" / "dashboards" / "todo-app.json").read_text(encoding="utf-8"))
    panels = {panel["title"]: panel for panel in todo_dash["panels"]}
    assert set(panels) == {"App", "Database", "Request/giây"}

    for title, expected_expr in (("App", 'up{job="app"}'), ("Database", 'todo_db_up{job="app"}')):
        panel = panels[title]
        assert panel["datasource"]["uid"] == "prometheus"
        target = panel["targets"][0]
        assert target["expr"] == expected_expr
        assert target["instant"] is True
        assert panel["options"]["reduceOptions"]["calcs"] == ["last"]
        defaults = panel["fieldConfig"]["defaults"]
        assert defaults["noValue"] == "No data"
        # Base threshold for null/missing values must NOT be green (avoid faking UP on missing scrape).
        assert defaults["thresholds"]["steps"][0]["color"] != "green"

    req_panel = panels["Request/giây"]
    assert req_panel["datasource"]["uid"] == "prometheus"
    assert req_panel["targets"][0]["expr"] == 'sum(rate(flask_http_request_total{job="app"}[1m]))'
    assert req_panel["fieldConfig"]["defaults"]["noValue"] == "No data"

    host_dash = json.loads((REPO_ROOT / "monitoring" / "grafana" / "dashboards" / "server-host.json").read_text(encoding="utf-8"))
    host_exprs = "\n".join(t["expr"] for p in host_dash["panels"] for t in p["targets"])
    assert all(p["datasource"]["uid"] == "prometheus" for p in host_dash["panels"])
    assert "node_cpu_seconds_total" in host_exprs
    assert "node_memory_MemAvailable_bytes" in host_exprs
    assert 'node_filesystem_avail_bytes{job="node",mountpoint="/"' in host_exprs


def test_scripts_preserve_lf_secret_safety_and_branch_independence():
    script_paths = [
        REPO_ROOT / "app" / "entrypoint.sh",
        REPO_ROOT / "db" / "app-user.sh",
        REPO_ROOT / "scripts" / "prepare-step1.sh",
        REPO_ROOT / "scripts" / "deploy.sh",
        REPO_ROOT / "scripts" / "setup-server.sh",
    ]
    for path in script_paths:
        raw = path.read_bytes()
        assert b"\r" not in raw, f"CRLF line ending found in {path}"
        non_comment = "\n".join(
            line for line in path.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
        assert "`" not in non_comment, f"Backtick found in executable shell code of {path}"
        assert "777" not in non_comment, f"Overly permissive mode 777 found in {path}"

    prep = (REPO_ROOT / "scripts" / "prepare-step1.sh").read_text(encoding="utf-8")
    deploy = (REPO_ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    setup = (REPO_ROOT / "scripts" / "setup-server.sh").read_text(encoding="utf-8")
    app_user = (REPO_ROOT / "db" / "app-user.sh").read_text(encoding="utf-8")

    # No hardcoded temporary branch name in scripts.
    assert "week-3-monitoring" not in prep
    assert "week-3-monitoring" not in deploy
    assert "week-3-monitoring" not in setup

    # Secret tracing must be explicitly disabled.
    for content in (prep, deploy, setup, app_user):
        assert "set +x" in content
        assert "set -eux" not in content

    # Required DML grants in db/app-user.sh must match current application schema (including UPDATE on todos).
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE %I.todos TO %I" in app_user
    assert "GRANT USAGE ON SEQUENCE %I.todos_id_seq TO %I" in app_user
    assert "GRANT SELECT, INSERT ON TABLE %I.todo_operations TO %I" in app_user
    assert "GRANT SELECT, INSERT ON TABLE %I.todo_tombstones TO %I" in app_user
    assert "GRANT SELECT, INSERT, DELETE ON TABLE %I.todo_categories TO %I" in app_user
    assert "GRANT SELECT, INSERT ON TABLE %I.todo_category_tombstones TO %I" in app_user

    # Deploy script must verify reload synchronously via /-/reload and *_config_last_reload_successful, not just SIGHUP.
    assert "kill -s HUP" not in deploy
    assert "/-/reload" in deploy
    assert "prometheus_config_last_reload_successful" in deploy
    assert "alertmanager_config_last_reload_successful" in deploy


def test_ci_workflow_checks_each_shell_script_individually_without_execution():
    ci_cfg = (REPO_ROOT / ".github" / "workflows" / "ci-cd.yml").read_text(encoding="utf-8")
    match = re.search(
        r"- name: Check shell script syntax\s+run: \|\n((?:          .*\n)+)",
        ci_cfg,
    )
    assert match is not None, "Missing 'Check shell script syntax' step in ci-cd.yml"
    step_lines = [
        line.strip()
        for line in match.group(1).splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    invocations = []
    for line in step_lines:
        if line.startswith("set "):
            assert "-e" in line
            continue
        tokens = line.split()
        # Every shell invocation in the syntax-check step must pass -n and exactly ONE script file
        # (because POSIX `sh -n file1 file2` only checks file1 and treats file2 as $1).
        assert len(tokens) == 3, f"Expected single-file `<shell> -n <script>`, got: {line}"
        shell_bin, flag, script_target = tokens
        assert shell_bin in {"sh", "bash"}, f"Unexpected command in syntax check step: {line}"
        assert flag == "-n", f"Syntax check must use -n (no execution), got: {line}"
        assert (REPO_ROOT / script_target).is_file(), f"Referenced script missing: {script_target}"
        invocations.append((shell_bin, script_target))

    assert invocations == [
        ("sh", "app/entrypoint.sh"),
        ("sh", "db/app-user.sh"),
        ("bash", "scripts/deploy.sh"),
        ("bash", "scripts/prepare-step1.sh"),
        ("bash", "scripts/setup-server.sh"),
    ]


def test_shell_scripts_pass_per_file_sh_and_bash_syntax_check(tmp_path):
    bash_bin = _get_usable_bash()
    checks = [
        ("sh", "app/entrypoint.sh"),
        ("sh", "db/app-user.sh"),
        ("bash", "scripts/deploy.sh"),
        ("bash", "scripts/prepare-step1.sh"),
        ("bash", "scripts/setup-server.sh"),
    ]
    for shell_name, rel_path in checks:
        script_posix = (REPO_ROOT / rel_path).as_posix()
        proc = subprocess.run(
            [bash_bin, "-c", f'{shell_name} -n "$1"', "_", script_posix],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        assert proc.returncode == 0, f"{shell_name} -n {rel_path} failed: {proc.stderr}"

    # Verify per-file checking catches a syntax error in a non-first file without executing it.
    marker = tmp_path / "never_executed"
    broken_script = tmp_path / "broken_second.sh"
    broken_script.write_text(
        f'touch "{marker.as_posix()}"\nif [ 1 -eq 1 ]; then\n  echo missing_fi\n',
        encoding="utf-8",
    )
    proc_broken = subprocess.run(
        [bash_bin, "-c", 'sh -n "$1"', "_", broken_script.as_posix()],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert proc_broken.returncode != 0
    assert not marker.exists(), "Syntax check (-n) must not execute script body"


def _run_prepare_step1_webhook_harness(bash_bin, work_dir, extra_env=None):
    perm_log = work_dir / "perm.log"
    if perm_log.exists():
        perm_log.unlink()

    harness = r"""
set -euo pipefail
set +x
cd "$WORK_DIR"
PREPARE_STEP1_LIB_ONLY=1 source "$PREPARE_SCRIPT"

docker() { echo "FORBIDDEN docker call" >&2; return 99; }
git() { echo "FORBIDDEN git call" >&2; return 99; }
curl() { echo "FORBIDDEN curl call" >&2; return 99; }

sudo() {
  local subcmd="$1"
  shift
  case "$subcmd" in
    install)
      # Expected: install -d -m 750 -o root -g 65534 <dir>
      local mode="" owner="" group="" target=""
      while [ "$#" -gt 0 ]; do
        case "$1" in
          -d) shift ;;
          -m) mode="$2"; shift 2 ;;
          -o) owner="$2"; shift 2 ;;
          -g) group="$2"; shift 2 ;;
          *) target="$1"; shift ;;
        esac
      done
      mkdir -p "$target"
      printf 'INSTALL_DIR|%s|%s:%s|%s\n' "$mode" "$owner" "$group" "$target" >> "$PERM_LOG"
      ;;
    test)
      test "$@"
      ;;
    cat)
      cat "$@"
      ;;
    tee)
      cat > "$1"
      ;;
    chown)
      printf 'CHOWN|%s\n' "$*" >> "$PERM_LOG"
      ;;
    chmod)
      printf 'CHMOD|%s\n' "$*" >> "$PERM_LOG"
      ;;
    ls)
      printf 'LS|%s\n' "$*" >> "$PERM_LOG"
      ;;
    sh)
      sh "$@"
      ;;
    *)
      echo "UNEXPECTED sudo subcommand: $subcmd" >&2
      return 98
      ;;
  esac
}

configure_discord_webhook_secret "secrets"
"""
    env = {
        **os.environ,
        "PREPARE_SCRIPT": (REPO_ROOT / "scripts" / "prepare-step1.sh").as_posix(),
        "WORK_DIR": work_dir.as_posix(),
        "PERM_LOG": perm_log.as_posix(),
    }
    for key in ("DISCORD_WEBHOOK_URL", "FORCE_ROTATE_WEBHOOK"):
        env.pop(key, None)
    if extra_env:
        env.update(extra_env)

    proc = subprocess.run(
        [bash_bin, "-c", harness],
        input="",
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=10,
    )
    logged = perm_log.read_text(encoding="utf-8").splitlines() if perm_log.exists() else []
    return proc, logged


def test_prepare_step1_existing_webhook_branches_isolated(tmp_path):
    bash_bin = _get_usable_bash()

    # 1. Valid existing webhook is preserved even if DISCORD_WEBHOOK_URL is passed without FORCE_ROTATE_WEBHOOK=1.
    case_keep = tmp_path / "keep_valid"
    (case_keep / "secrets").mkdir(parents=True)
    webhook_file = case_keep / "secrets" / "discord_webhook_url"
    webhook_file.write_text(FAKE_WEBHOOK_1 + "\n", encoding="utf-8")

    proc, perm_ops = _run_prepare_step1_webhook_harness(
        bash_bin,
        case_keep,
        extra_env={"DISCORD_WEBHOOK_URL": FAKE_WEBHOOK_2},
    )
    combined_out = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined_out
    assert webhook_file.read_text(encoding="utf-8").strip() == FAKE_WEBHOOK_1
    assert FAKE_WEBHOOK_1 not in combined_out
    assert FAKE_WEBHOOK_2 not in combined_out
    assert "FakeWebhookToken" not in combined_out
    assert "INSTALL_DIR|750|root:65534|secrets" in perm_ops
    assert "CHOWN|root:65534 secrets secrets/discord_webhook_url" in perm_ops
    assert "CHMOD|750 secrets" in perm_ops
    assert "CHMOD|640 secrets/discord_webhook_url" in perm_ops
    assert not any("777" in op for op in perm_ops)

    # 2. Valid existing webhook IS rotated when FORCE_ROTATE_WEBHOOK=1 is set explicitly.
    proc_rot, perm_ops_rot = _run_prepare_step1_webhook_harness(
        bash_bin,
        case_keep,
        extra_env={"FORCE_ROTATE_WEBHOOK": "1", "DISCORD_WEBHOOK_URL": FAKE_WEBHOOK_2},
    )
    combined_rot = proc_rot.stdout + proc_rot.stderr
    assert proc_rot.returncode == 0, combined_rot
    assert webhook_file.read_text(encoding="utf-8") == FAKE_WEBHOOK_2
    assert FAKE_WEBHOOK_1 not in combined_rot
    assert FAKE_WEBHOOK_2 not in combined_rot
    assert "FakeWebhookToken" not in combined_rot
    assert "CHMOD|640 secrets/discord_webhook_url" in perm_ops_rot

    # 3. Empty existing webhook file fails with clear error.
    case_empty = tmp_path / "empty_file"
    (case_empty / "secrets").mkdir(parents=True)
    (case_empty / "secrets" / "discord_webhook_url").write_text("", encoding="utf-8")
    proc_empty, _ = _run_prepare_step1_webhook_harness(bash_bin, case_empty)
    assert proc_empty.returncode != 0
    assert "rỗng hoặc sai định dạng" in proc_empty.stderr

    # 4. Malformed existing webhook containing backticks / command-substitution attempt fails safely
    #    without executing embedded commands or leaking file contents.
    case_bad = tmp_path / "bad_backtick"
    (case_bad / "secrets").mkdir(parents=True)
    marker = case_bad / "command_executed_marker"
    malicious_value = f"https://evil.example/`touch {marker.as_posix()}`/SecretLeakCheckToken999"
    (case_bad / "secrets" / "discord_webhook_url").write_text(malicious_value, encoding="utf-8")

    proc_bad, _ = _run_prepare_step1_webhook_harness(bash_bin, case_bad)
    combined_bad = proc_bad.stdout + proc_bad.stderr
    assert proc_bad.returncode != 0
    assert not marker.exists(), "Embedded backtick inside webhook file was executed!"
    assert "SecretLeakCheckToken999" not in combined_bad
    assert "rỗng hoặc sai định dạng" in proc_bad.stderr

    # 5. Malformed existing webhook can be replaced when FORCE_ROTATE_WEBHOOK=1 + valid webhook are given.
    proc_recover, _ = _run_prepare_step1_webhook_harness(
        bash_bin,
        case_bad,
        extra_env={"FORCE_ROTATE_WEBHOOK": "1", "DISCORD_WEBHOOK_URL": FAKE_WEBHOOK_1},
    )
    assert proc_recover.returncode == 0
    assert (case_bad / "secrets" / "discord_webhook_url").read_text(encoding="utf-8") == FAKE_WEBHOOK_1

    # 6. Directory at secrets/discord_webhook_url is rejected clearly.
    case_dir = tmp_path / "webhook_is_dir"
    (case_dir / "secrets" / "discord_webhook_url").mkdir(parents=True)
    proc_dir, _ = _run_prepare_step1_webhook_harness(bash_bin, case_dir)
    assert proc_dir.returncode != 0
    assert "đang là thư mục" in proc_dir.stderr


def _replay_permissions(app_dir, perm_ops, initial_owners=None, initial_modes=None):
    owners = dict(initial_owners or {})
    modes = dict(initial_modes or {})

    for op in perm_ops:
        parts = op.split("|")
        kind = parts[0]
        if kind == "CHOWN":
            recursive = parts[1] == "1"
            owner = parts[2]
            for raw_target in parts[3:]:
                target = Path(raw_target)
                owners[target.resolve()] = owner
                if recursive and target.is_dir():
                    for child in target.rglob("*"):
                        owners[child.resolve()] = owner
        elif kind == "CHMOD":
            mode = parts[1]
            assert mode != "777", f"Forbidden 777 permission detected: {op}"
            for raw_target in parts[2:]:
                modes[Path(raw_target).resolve()] = mode
    return owners, modes


def _run_setup_server_secrets_harness(bash_bin, app_dir, webhook_env=""):
    perm_log = app_dir.parent / f"{app_dir.name}_perm.log"
    if perm_log.exists():
        perm_log.unlink()

    harness = r"""
set -euo pipefail
set +x
SETUP_SERVER_LIB_ONLY=1 source "$SETUP_SCRIPT"

docker() { echo "FORBIDDEN docker call" >&2; return 99; }
git() { echo "FORBIDDEN git call" >&2; return 99; }
curl() { echo "FORBIDDEN curl call" >&2; return 99; }
sudo() { echo "FORBIDDEN sudo call" >&2; return 99; }
apt-get() { echo "FORBIDDEN apt-get call" >&2; return 99; }

chown() {
  local recursive=0
  if [ "${1:-}" = "-R" ]; then
    recursive=1
    shift
  fi
  local owner="$1"
  shift
  local line="CHOWN|${recursive}|${owner}"
  local target
  for target in "$@"; do
    line="${line}|${target}"
  done
  printf '%s\n' "$line" >> "$PERM_LOG"
}

chmod() {
  local mode="$1"
  shift
  local line="CHMOD|${mode}"
  local target
  for target in "$@"; do
    line="${line}|${target}"
  done
  printf '%s\n' "$line" >> "$PERM_LOG"
}

prepare_setup_secrets "$APP_DIR_ARG" "$WEBHOOK_ENV_ARG"
"""
    env = {
        **os.environ,
        "SETUP_SCRIPT": (REPO_ROOT / "scripts" / "setup-server.sh").as_posix(),
        "APP_DIR_ARG": app_dir.as_posix(),
        "WEBHOOK_ENV_ARG": webhook_env,
        "PERM_LOG": perm_log.as_posix(),
    }
    proc = subprocess.run(
        [bash_bin, "-c", harness],
        input="",
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=10,
    )
    logged = perm_log.read_text(encoding="utf-8").splitlines() if perm_log.exists() else []
    return proc, logged


def test_setup_server_rerun_with_existing_webhook_preserves_content_and_restores_permissions(tmp_path):
    bash_bin = _get_usable_bash()

    # 1. Re-run with existing valid webhook and empty DISCORD_WEBHOOK_URL (simulating second run after chown -R).
    app_dir = tmp_path / "app_rerun"
    secrets_dir = app_dir / "secrets"
    secrets_dir.mkdir(parents=True)
    env_file = app_dir / ".env"
    env_file.write_text("POSTGRES_USER=todo\n", encoding="utf-8")
    webhook_file = secrets_dir / "discord_webhook_url"
    webhook_file.write_text(FAKE_WEBHOOK_1, encoding="utf-8")

    proc, perm_ops = _run_setup_server_secrets_harness(bash_bin, app_dir, webhook_env="")
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert webhook_file.read_text(encoding="utf-8") == FAKE_WEBHOOK_1
    assert FAKE_WEBHOOK_1 not in combined
    assert "FakeWebhookToken" not in combined

    owners, modes = _replay_permissions(app_dir, perm_ops)
    assert owners[env_file.resolve()] == "ubuntu:ubuntu"
    assert modes[env_file.resolve()] == "600"
    assert owners[secrets_dir.resolve()] == "root:65534"
    assert modes[secrets_dir.resolve()] == "750"
    assert owners[webhook_file.resolve()] == "root:65534"
    assert modes[webhook_file.resolve()] == "640"

    # 2. Re-run with existing valid webhook does NOT overwrite it even if DISCORD_WEBHOOK_URL has a different URL.
    proc2, perm_ops2 = _run_setup_server_secrets_harness(bash_bin, app_dir, webhook_env=FAKE_WEBHOOK_2)
    combined2 = proc2.stdout + proc2.stderr
    assert proc2.returncode == 0, combined2
    assert webhook_file.read_text(encoding="utf-8") == FAKE_WEBHOOK_1
    assert FAKE_WEBHOOK_1 not in combined2
    assert FAKE_WEBHOOK_2 not in combined2
    owners2, modes2 = _replay_permissions(app_dir, perm_ops2)
    assert owners2[secrets_dir.resolve()] == "root:65534"
    assert modes2[secrets_dir.resolve()] == "750"
    assert owners2[webhook_file.resolve()] == "root:65534"
    assert modes2[webhook_file.resolve()] == "640"

    # 3. Re-run when secrets/discord_webhook_url is a directory fails clearly.
    app_dir_is_dir = tmp_path / "app_webhook_dir"
    (app_dir_is_dir / "secrets" / "discord_webhook_url").mkdir(parents=True)
    proc_dir, _ = _run_setup_server_secrets_harness(bash_bin, app_dir_is_dir, webhook_env=FAKE_WEBHOOK_1)
    assert proc_dir.returncode != 0
    assert "đang là thư mục" in proc_dir.stderr

    # 4. Re-run when secrets/discord_webhook_url exists as an empty file and no env webhook is provided stops cleanly.
    app_dir_empty = tmp_path / "app_webhook_empty"
    (app_dir_empty / "secrets").mkdir(parents=True)
    empty_wf = app_dir_empty / "secrets" / "discord_webhook_url"
    empty_wf.write_text("", encoding="utf-8")
    proc_empty, perm_ops_empty = _run_setup_server_secrets_harness(bash_bin, app_dir_empty, webhook_env="")
    assert proc_empty.returncode != 0
    assert "CHƯA HOÀN TẤT SETUP" in proc_empty.stderr
    owners_empty, modes_empty = _replay_permissions(app_dir_empty, perm_ops_empty)
    assert owners_empty[(app_dir_empty / "secrets").resolve()] == "root:65534"
    assert modes_empty[(app_dir_empty / "secrets").resolve()] == "750"
    assert owners_empty[empty_wf.resolve()] == "root:65534"
    assert modes_empty[empty_wf.resolve()] == "640"

    # 5. Re-run when existing webhook file contains invalid/malformed content stops with error,
    #    still restores root:65534 640 permissions, and never leaks or executes content.
    app_dir_bad = tmp_path / "app_webhook_bad"
    (app_dir_bad / "secrets").mkdir(parents=True)
    bad_marker = app_dir_bad / "pwned_marker"
    bad_wf = app_dir_bad / "secrets" / "discord_webhook_url"
    bad_wf.write_text(f"https://invalid.example/`touch {bad_marker.as_posix()}`/BadSecretToken777", encoding="utf-8")
    proc_bad, perm_ops_bad = _run_setup_server_secrets_harness(bash_bin, app_dir_bad, webhook_env="")
    combined_bad = proc_bad.stdout + proc_bad.stderr
    assert proc_bad.returncode != 0
    assert not bad_marker.exists()
    assert "BadSecretToken777" not in combined_bad
    assert "sai định dạng" in proc_bad.stderr
    owners_bad, modes_bad = _replay_permissions(app_dir_bad, perm_ops_bad)
    assert owners_bad[bad_wf.resolve()] == "root:65534"
    assert modes_bad[bad_wf.resolve()] == "640"
