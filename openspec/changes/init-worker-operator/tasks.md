## 1. Project Scaffolding & Packaging Setup

- [x] 1.1 Create `charmcraft.yaml` declaring charm metadata, container resource `oci-image`, `uv` build plugin, config options, and requires relations.
- [x] 1.2 Create `pyproject.toml` declaring dependencies (`ops>=2.0.0`, `authorization-service-operator-shared`, `lightkube`) pinned to git branch `IAM-2310-authorization-service-shared-lib`.
- [x] 1.3 Create project `README.md` documenting worker charm deployment.

## 2. Core Worker Charm Implementation

- [x] 2.1 Implement `src/charm.py` initializing charm hooks and consuming shared relation handlers (`OpenFGARelationHandler`, `AuthorizationServiceInfoRequirer`, `MetricsRelationHandler`, `GrafanaDashboardHandler`).
- [x] 2.2 Configure `KubernetesComputeResourcesPatch` using `cpu` and `memory` charm options to patch workload container specs.
- [x] 2.3 Implement Pebble container layer setup running `/usr/bin/app worker`, dynamically injecting `--no-reaper` flag on non-leader units and omitting it on the leader unit.
- [x] 2.4 Implement `AuthorizationServiceInfoRequirer` version checking and observer for `authorization_service_info_updated` events.
- [x] 2.5 Implement leadership transition handling (`on.leader_elected`) to update Pebble service layer so demoted units stop reaper execution and newly elected leaders start reaper execution.
- [x] 2.6 Implement status evaluation reconciliation handling `BlockedStatus` (missing `authorization-service-info` or `openfga` relation), `WaitingStatus` (missing database credentials, unready OpenFGA relation/store/model, or waiting for server migration via info lib), and `ActiveStatus`.

## 3. Testing & Verification

- [x] 3.1 Configure `pytest` testing harness with Scenario testing framework for charm unit testing.
- [x] 3.2 Write unit tests verifying leader vs non-leader reaper command flag generation and leader transition behavior.
- [x] 3.3 Write unit tests verifying `authorization-service-info` relation version comparison and status reporting.
- [x] 3.4 Write unit tests verifying `CharmConfig` proxy/log-level mappings and Kubernetes Resource Patching logic.
- [x] 3.5 Write unit tests verifying status reconciliation for blocked, waiting, and active states.
- [x] 3.6 Run `ruff` lint and formatting checks across the worker charm repository.
