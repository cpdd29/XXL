# DR Formal Result Bundle

## Bundle Summary

```json
{
  "status": "packaged",
  "exercise_id": "dr-local-20260415"
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
          "precheck": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_precheck_20260415_052850.json",
          "prepare": "/Users/xiaoyuge/Documents/XXL/backend/docs/failover_prepare_20260415_052850.json",
          "post_verify": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.json",
          "recovery": "/Users/xiaoyuge/Documents/XXL/backend/docs/external_tentacle_recovery_20260415_052850.json"
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
        "post_verify_report": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.json"
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
      "name": "dr_precheck_20260415_052850.json",
      "path": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_precheck_20260415_052850.json",
      "markdown_path": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_precheck_20260415_052850.md",
      "drill_kind": "formal",
      "gate_stats": {
        "failed": 0,
        "manual_intervention": 5
      }
    },
    {
      "name": "failover_prepare_20260415_052850.json",
      "path": "/Users/xiaoyuge/Documents/XXL/backend/docs/failover_prepare_20260415_052850.json",
      "markdown_path": "/Users/xiaoyuge/Documents/XXL/backend/docs/failover_prepare_20260415_052850.md",
      "drill_kind": "formal",
      "gate_stats": {
        "failed": 0,
        "manual_intervention": 5
      }
    },
    {
      "name": "post_failover_verify_20260415_052850.json",
      "path": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.json",
      "markdown_path": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.md",
      "drill_kind": "formal",
      "gate_stats": {
        "failed": 0,
        "manual_intervention": 0
      }
    },
    {
      "name": "external_tentacle_recovery_20260415_052850.json",
      "path": "/Users/xiaoyuge/Documents/XXL/backend/docs/external_tentacle_recovery_20260415_052850.json",
      "markdown_path": "/Users/xiaoyuge/Documents/XXL/backend/docs/external_tentacle_recovery_20260415_052850.md",
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
  "archive_dir": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_result_archives/dr-local-20260415",
  "archive_complete": true,
  "items": [
    {
      "name": "dr_precheck_20260415_052850.json",
      "source": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_precheck_20260415_052850.json",
      "archived": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_result_archives/dr-local-20260415/dr_precheck_20260415_052850.json",
      "size_bytes": 6833,
      "sha256": "383ce71b4536bdd2756984708dcdf0164377d3f8f93538fc90a8c4e15b4b3486"
    },
    {
      "name": "dr_precheck_20260415_052850.md",
      "source": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_precheck_20260415_052850.md",
      "archived": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_result_archives/dr-local-20260415/dr_precheck_20260415_052850.md",
      "size_bytes": 3312,
      "sha256": "3a890ca17f941ac1fb9693f08c69787b229c9a7f6d1bac94e1b4c271a4cb1158"
    },
    {
      "name": "failover_prepare_20260415_052850.json",
      "source": "/Users/xiaoyuge/Documents/XXL/backend/docs/failover_prepare_20260415_052850.json",
      "archived": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_result_archives/dr-local-20260415/failover_prepare_20260415_052850.json",
      "size_bytes": 7478,
      "sha256": "e718ee8f91618873437416c2f25ed7e578aee80fba2b47bfd38210802ac208be"
    },
    {
      "name": "failover_prepare_20260415_052850.md",
      "source": "/Users/xiaoyuge/Documents/XXL/backend/docs/failover_prepare_20260415_052850.md",
      "archived": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_result_archives/dr-local-20260415/failover_prepare_20260415_052850.md",
      "size_bytes": 6072,
      "sha256": "53e9607f2ddafe3b30fef7b499f2eeb79cfb8eec16f2a0b5a2819fcd4bf32aa6"
    },
    {
      "name": "post_failover_verify_20260415_052850.json",
      "source": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.json",
      "archived": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_result_archives/dr-local-20260415/post_failover_verify_20260415_052850.json",
      "size_bytes": 5995,
      "sha256": "7fd809f7952df976f6242e6939ea84a42ff134960d0646fca682c0d1b82cf116"
    },
    {
      "name": "post_failover_verify_20260415_052850.md",
      "source": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.md",
      "archived": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_result_archives/dr-local-20260415/post_failover_verify_20260415_052850.md",
      "size_bytes": 2912,
      "sha256": "60be8641434b316ae9d121d18bba822d8f283a44dbf624ede8f3e6b840d82594"
    },
    {
      "name": "external_tentacle_recovery_20260415_052850.json",
      "source": "/Users/xiaoyuge/Documents/XXL/backend/docs/external_tentacle_recovery_20260415_052850.json",
      "archived": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_result_archives/dr-local-20260415/external_tentacle_recovery_20260415_052850.json",
      "size_bytes": 4373,
      "sha256": "f4acda0bda34105978c578125bc002758f7ac88cc55ddaf2cac05d0addc2d322"
    },
    {
      "name": "external_tentacle_recovery_20260415_052850.md",
      "source": "/Users/xiaoyuge/Documents/XXL/backend/docs/external_tentacle_recovery_20260415_052850.md",
      "archived": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_result_archives/dr-local-20260415/external_tentacle_recovery_20260415_052850.md",
      "size_bytes": 1630,
      "sha256": "6e9381da0ad13c1e5dcb881e186a8f3d1a866b49b1f87d1f4736eb6d8bd1e824"
    },
    {
      "name": "dr_result_gate_formal_20260415_052850.json",
      "source": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_result_gate_formal_20260415_052850.json",
      "archived": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_result_archives/dr-local-20260415/dr_result_gate_formal_20260415_052850.json",
      "size_bytes": 2411,
      "sha256": "1f38a91726fb3104b447a16a0c9cbf6539d137c938dd9af5e24590c9c33e2d02"
    },
    {
      "name": "dr_result_gate_formal_20260415_052850.md",
      "source": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_result_gate_formal_20260415_052850.md",
      "archived": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_result_archives/dr-local-20260415/dr_result_gate_formal_20260415_052850.md",
      "size_bytes": 2294,
      "sha256": "294645ebd3623ef9263c5e603fee2ed2b6f73a614b0318687827d7d68202b5af"
    }
  ]
}
```
