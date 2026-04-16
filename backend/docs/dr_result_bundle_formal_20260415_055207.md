# DR Formal Result Bundle

## Bundle Summary

```json
{
  "status": "packaged",
  "exercise_id": "dr-formal-001"
}
```

## Gate

```json
{
  "status": "passed",
  "failed_steps": [],
  "checks": [
    {
      "key": "required_reports_present",
      "ok": true,
      "details": {
        "expected": [
          "precheck",
          "prepare",
          "post_verify",
          "recovery"
        ],
        "missing": {},
        "resolved": {
          "precheck": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/dr_precheck_fixture.json",
          "prepare": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/failover_prepare_fixture.json",
          "post_verify": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/post_failover_verify_fixture.json",
          "recovery": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/external_tentacle_recovery_fixture.json"
        }
      }
    },
    {
      "key": "rto_rpo_fields_present",
      "ok": true,
      "details": {
        "required_fields": [
          "measurements.rto_seconds",
          "measurements.estimated_rpo_seconds"
        ],
        "post_verify_report": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/post_failover_verify_fixture.json"
      }
    },
    {
      "key": "failed_manual_intervention_stats_present",
      "ok": true,
      "details": {
        "required_fields": [
          "gate_stats.failed",
          "gate_stats.manual_intervention"
        ]
      }
    },
    {
      "key": "formal_drill_kind_required",
      "ok": true,
      "details": {
        "allow_smoke": false,
        "required_kind": "formal",
        "report_drill_kinds": {
          "precheck": "formal",
          "prepare": "formal",
          "post_verify": "formal",
          "recovery": "formal"
        },
        "non_formal_reports": {}
      }
    }
  ],
  "gate_stats": {
    "failed": 0,
    "manual_intervention": 10
  },
  "report_drill_kinds": {
    "precheck": "formal",
    "prepare": "formal",
    "post_verify": "formal",
    "recovery": "formal"
  }
}
```

## Bundle Reports

```json
{
  "reports": [
    {
      "name": "dr_precheck_fixture.json",
      "path": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/dr_precheck_fixture.json",
      "markdown_path": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/dr_precheck_fixture.md",
      "drill_kind": "formal",
      "gate_stats": {
        "failed": 0,
        "manual_intervention": 5
      }
    },
    {
      "name": "failover_prepare_fixture.json",
      "path": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/failover_prepare_fixture.json",
      "markdown_path": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/failover_prepare_fixture.md",
      "drill_kind": "formal",
      "gate_stats": {
        "failed": 0,
        "manual_intervention": 5
      }
    },
    {
      "name": "post_failover_verify_fixture.json",
      "path": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/post_failover_verify_fixture.json",
      "markdown_path": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/post_failover_verify_fixture.md",
      "drill_kind": "formal",
      "gate_stats": {
        "failed": 0,
        "manual_intervention": 0
      }
    },
    {
      "name": "external_tentacle_recovery_fixture.json",
      "path": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/external_tentacle_recovery_fixture.json",
      "markdown_path": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/external_tentacle_recovery_fixture.md",
      "drill_kind": "formal",
      "gate_stats": {
        "failed": 0,
        "manual_intervention": 0
      }
    }
  ],
  "report_count": 4
}
```

## Archive Manifest

```json
{
  "archive_dir": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/archives/dr-formal-001",
  "archive_complete": true,
  "items": [
    {
      "name": "dr_precheck_fixture.json",
      "source": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/dr_precheck_fixture.json",
      "archived": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/archives/dr-formal-001/dr_precheck_fixture.json",
      "size_bytes": 175,
      "sha256": "b8bccf241ac3c3daacceeb0b2d0990f630b427b81cc3def50d789f493f9ab552"
    },
    {
      "name": "dr_precheck_fixture.md",
      "source": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/dr_precheck_fixture.md",
      "archived": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/archives/dr-formal-001/dr_precheck_fixture.md",
      "size_bytes": 14,
      "sha256": "41db591267bd3042f9222d86688c9e0b56b907795b36f55eee3eccfb60ab4694"
    },
    {
      "name": "failover_prepare_fixture.json",
      "source": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/failover_prepare_fixture.json",
      "archived": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/archives/dr-formal-001/failover_prepare_fixture.json",
      "size_bytes": 175,
      "sha256": "b8bccf241ac3c3daacceeb0b2d0990f630b427b81cc3def50d789f493f9ab552"
    },
    {
      "name": "failover_prepare_fixture.md",
      "source": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/failover_prepare_fixture.md",
      "archived": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/archives/dr-formal-001/failover_prepare_fixture.md",
      "size_bytes": 19,
      "sha256": "1972cc1c12f79d70694109c34e728539a118902cbbab952baf2834eb4167bd45"
    },
    {
      "name": "post_failover_verify_fixture.json",
      "source": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/post_failover_verify_fixture.json",
      "archived": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/archives/dr-formal-001/post_failover_verify_fixture.json",
      "size_bytes": 259,
      "sha256": "3acd9b07cb7b1c5d06c77e9e96474aaa660bd9e021e81856ebc238911e871847"
    },
    {
      "name": "post_failover_verify_fixture.md",
      "source": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/post_failover_verify_fixture.md",
      "archived": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/archives/dr-formal-001/post_failover_verify_fixture.md",
      "size_bytes": 23,
      "sha256": "2e2346aa8eaaa4ff3f02c7c46d16280d25caaf18f28a60f158d06f1bfaa016a0"
    },
    {
      "name": "external_tentacle_recovery_fixture.json",
      "source": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/external_tentacle_recovery_fixture.json",
      "archived": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/archives/dr-formal-001/external_tentacle_recovery_fixture.json",
      "size_bytes": 175,
      "sha256": "10dc38f87d2dc20fdf85c6014eff836dfe158bd802f1f1f8c922da5e2cd85ae2"
    },
    {
      "name": "external_tentacle_recovery_fixture.md",
      "source": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/external_tentacle_recovery_fixture.md",
      "archived": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/archives/dr-formal-001/external_tentacle_recovery_fixture.md",
      "size_bytes": 29,
      "sha256": "c0c0da886596bfa0e2cb1d4f4d930e152a7937d8f8219ca2a42f7c308aeca53e"
    },
    {
      "name": "dr_result_gate_formal_20260415_055207.json",
      "source": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_result_gate_formal_20260415_055207.json",
      "archived": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/archives/dr-formal-001/dr_result_gate_formal_20260415_055207.json",
      "size_bytes": 3014,
      "sha256": "4550cf702fd715c2d1dd97ada5cc35110621debb08ba87f1e4ef77bcd4ae7581"
    },
    {
      "name": "dr_result_gate_formal_20260415_055207.md",
      "source": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_result_gate_formal_20260415_055207.md",
      "archived": "/private/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/pytest-of-xiaoyuge/pytest-85/test_run_package_dr_result_bun0/archives/dr-formal-001/dr_result_gate_formal_20260415_055207.md",
      "size_bytes": 2897,
      "sha256": "14633bee4bbce0368613f3f6c88bb62f8bb436eb4c6c379e5526e55494e83a65"
    }
  ]
}
```
