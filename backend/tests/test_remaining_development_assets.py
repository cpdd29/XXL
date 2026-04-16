from __future__ import annotations

import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_multi_instance_compose_declares_dispatchers_and_workers() -> None:
    compose_path = REPO_ROOT / "deploy" / "multi-instance" / "docker-compose.multi-instance.yml"
    payload = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    services = payload["services"]
    assert {"dispatcher-a", "dispatcher-b", "workflow-worker-a", "workflow-worker-b", "agent-worker-a", "agent-worker-b"}.issubset(
        set(services.keys())
    )
    assert "run_dispatcher_runtime.py" in " ".join(services["dispatcher-a"]["command"])
    assert "run_workflow_execution_worker_runtime.py" in " ".join(services["workflow-worker-a"]["command"])
    assert "run_agent_execution_worker_runtime.py" in " ".join(services["agent-worker-a"]["command"])


def test_monitoring_assets_declare_prometheus_grafana_and_dashboard() -> None:
    compose_path = REPO_ROOT / "deploy" / "monitoring" / "docker-compose.monitoring.yml"
    payload = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    services = payload["services"]
    assert {"prometheus", "grafana"} == set(services.keys())

    prom_template = (REPO_ROOT / "deploy" / "monitoring" / "prometheus" / "prometheus.yml.tpl").read_text(
        encoding="utf-8"
    )
    assert "/api/dashboard/metrics" in prom_template
    assert "__WORKBOT_METRICS_SCRAPE_TOKEN__" in prom_template

    dashboard_payload = json.loads(
        (REPO_ROOT / "deploy" / "monitoring" / "grafana" / "dashboards" / "brain-runtime-overview.json").read_text(
            encoding="utf-8"
        )
    )
    assert dashboard_payload["uid"] == "brain-runtime-overview"
    assert dashboard_payload["title"] == "Brain Runtime Overview"


def test_acceptance_templates_exist_for_package_a_d_e() -> None:
    expected = {
        "backend/docs/PACKAGE_A_MULTI_INSTANCE_ACCEPTANCE_TEMPLATE.md": (
            "Package A Multi-Instance Acceptance Template",
            "dispatch claim 排他",
            "NATS 恢复",
        ),
        "backend/docs/PACKAGE_D_EXTERNAL_ACCEPTANCE_TEMPLATE.md": (
            "Package D External Acceptance Template",
            "Agent 注册成功",
            "Header / 签名链",
        ),
        "backend/docs/PACKAGE_E_SECURITY_ACCEPTANCE_TEMPLATE.md": (
            "Package E Security Acceptance Template",
            "allow / rewrite / block",
            "Bypass / Manual Review Closure",
        ),
    }

    for relative_path, keywords in expected.items():
        content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for keyword in keywords:
            assert keyword in content


def test_run_scripts_are_present_and_reference_extra_compose_files() -> None:
    run_brain = (REPO_ROOT / "run-brain.sh").read_text(encoding="utf-8")
    run_monitoring = (REPO_ROOT / "run-monitoring-stack.sh").read_text(encoding="utf-8")
    run_multi = (REPO_ROOT / "run-multi-instance-acceptance.sh").read_text(encoding="utf-8")
    package_release = (REPO_ROOT / "package-release-evidence.sh").read_text(encoding="utf-8")
    check_release_runtime = (REPO_ROOT / "check-release-runtime.sh").read_text(encoding="utf-8")

    assert "WORKBOT_EXTRA_COMPOSE_FILES" in run_brain
    assert "deploy/monitoring/docker-compose.monitoring.yml" in run_monitoring
    assert "deploy/multi-instance/docker-compose.multi-instance.yml" in run_multi
    assert "python scripts/package_release_evidence_bundle.py" in package_release
    assert "python scripts/check_release_runtime.py" in check_release_runtime
