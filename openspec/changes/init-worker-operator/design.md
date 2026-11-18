## Context

The Charmed Authorization Service architecture includes a dedicated background processing component (`authorization-service-worker-operator`). This operator runs as a Kubernetes workload executing `/usr/bin/app worker`. It requires PostgreSQL for persistent state and OpenFGA for authorization evaluations, but does not consume Kafka events or expose public ingress endpoints.

To maintain architectural consistency across all Authorization Service charms, the worker operator leverages the `authorization-service-operator-shared` library for configuration management, CLI execution, Pebble container orchestration, version info verification (`authorization_service_operator_shared.info`), and relation integrations, following patterns established in Canonical operator repositories.

## Goals / Non-Goals

**Goals:**
- Initialize the `authorization-service-worker-operator` repository using `charmcraft.yaml` configured with the `uv` build plugin and `build-packages: [git]`.
- Define standard Juju charm configurations in `charmcraft.yaml` (`log_level`, `http_proxy`, `https_proxy`, `no_proxy`, `cpu`, `memory`).
- Consume `AuthorizationServiceInfoRequirer` from `authorization_service_operator_shared.info` to receive server workload/migration version and database connection parameters (`POSTGRES_*`).
- Implement Kubernetes Resource Patching using `KubernetesComputeResourcesPatch` to dynamically apply `cpu` and `memory` limits to the workload container spec.
- Consume the `authorization-service-operator-shared` library for core framework utilities (`CharmConfig`, `CommandLine`, `PebbleService`, `WorkloadService`) and relation handlers.
- Manage Pebble container layers to execute `/usr/bin/app worker` with service name `authorization-service` (overriding default OCI image service definition) and stripping HTTP health probes.
- Implement leader-dependent reaper execution:
  - Non-leader units run `/usr/bin/app worker --no-reaper`.
  - Leader unit runs `/usr/bin/app worker` (reaper enabled).
  - Handle leadership transition events (`leader_elected`) so the former leader unit stops running the reaper process and the newly elected leader unit starts running it.
- Wire relation integrations for OpenFGA (`openfga`), Authorization Service Info (`authorization-service-info`), and COS Observability.
- Enforce explicit status evaluation rules:
  - `BlockedStatus("Missing required relation: authorization-service-info")` when authorization service info relation is missing.
  - `WaitingStatus("Waiting for database credentials")` when database credentials are missing from info relation.
  - `BlockedStatus("Missing required relation: openfga")` when OpenFGA relation is missing.
  - `WaitingStatus("OpenFGA relation is not ready yet")` / `WaitingStatus("OpenFGA store is not ready yet")` / `WaitingStatus("Waiting for OpenFGA model creation")` when OpenFGA configuration is incomplete.
  - `WaitingStatus("Waiting for the server to run migration")` when server migration version does not match worker workload version.
  - `ActiveStatus("Worker active")` / `ActiveStatus("Worker active (no-reaper)")` when workload service is running.

**Non-Goals:**
- Direct PostgreSQL (`pg-database`) relation integration (database connection details are received exclusively via `authorization-service-info`).
- Running database migrations directly inside worker operator (migrations are executed by the server charm `authorization-service`).
- Kafka relation integration (not used by worker component).
- Secure Token Service (STS) relation integration (not used by worker component).
- Istio or Ingress route exposure (worker is strictly an internal background component).

## Workload Environment Variables & Sources Matrix

All environment variables passed to the `/usr/bin/app worker` workload container process are aggregated from standard handlers in `authorization-service-operator-shared` and charm configurations:

| Environment Variable | Source Handler / Origin | Category | Description | Example / Default Value |
| :--- | :--- | :--- | :--- | :--- |
| `LOG_LEVEL` | `CharmConfig` | Charm Config | Logging verbosity level | `"info"`, `"debug"` |
| `DEV` | `CharmConfig` | Charm Config | Developer mode flag | `"false"`, `"true"` |
| `HTTP_PROXY` | `CharmConfig` | Proxy Config | Outbound HTTP proxy URL | `"http://proxy:3128"` / `None` |
| `HTTPS_PROXY` | `CharmConfig` | Proxy Config | Outbound HTTPS proxy URL | `"http://proxy:3128"` / `None` |
| `NO_PROXY` | `CharmConfig` | Proxy Config | Proxy exclusion list | `"localhost,127.0.0.1"` / `None` |
| `POSTGRES_HOST` | `AuthorizationServiceInfoRequirer` | Relation (`authorization-service-info`) | PostgreSQL server host | `"postgresql-k8s-0.postgresql-k8s-endpoints"` |
| `POSTGRES_PORT` | `AuthorizationServiceInfoRequirer` | Relation (`authorization-service-info`) | PostgreSQL server port | `"5432"` |
| `POSTGRES_USER` | `AuthorizationServiceInfoRequirer` | Relation (`authorization-service-info`) | Database username | `"relation-user"` |
| `POSTGRES_PASSWORD` | `AuthorizationServiceInfoRequirer` | Relation (`authorization-service-info`) | Database password | `"secret-password"` |
| `POSTGRES_DB` | `AuthorizationServiceInfoRequirer` | Relation (`authorization-service-info`) | Target database name | `"authorization_service"` |
| `POSTGRES_SSL_MODE` | `AuthorizationServiceInfoRequirer` | Relation (`authorization-service-info`) | SSL connection mode | `"require"`, `"disable"` |
| `OPENFGA_ADDRESS` | `OpenFGARelationHandler` | Relation (`openfga`) | OpenFGA API server endpoint | `"http://openfga:8080"` |
| `OPENFGA_STORE_ID` | `AuthorizationServiceInfoRequirer` / `OpenFGARelationHandler` | Relation (`authorization-service-info` / `openfga`) | OpenFGA store identifier | `"01H1234567890ABCDEF"` |
| `OPENFGA_API_KEY` | `OpenFGARelationHandler` | Relation (`openfga`) | OpenFGA authentication token | `"openfga-token"` |
| `OPENFGA_AUTHORIZATION_MODEL_ID` | `AuthorizationServiceInfoRequirer` | Relation (`authorization-service-info`) | Authorization model ID created by server | `"01H9876543210FEDCBA"` |
| `METRICS_ENABLED` | `MetricsRelationHandler` | Observability | Enable Prometheus metrics export | `"true"` |
| `METRICS_PORT` | `MetricsRelationHandler` | Observability | Metrics scraping port | `"9090"` / `"9100"` |
| `METRICS_PATH` | `MetricsRelationHandler` | Observability | Metrics HTTP endpoint path | `"/metrics"` |

## Juju Status Mapping Matrix

The worker operator evaluates unit status deterministically during each reconciliation loop pass in strict priority order:

| Priority | Evaluation Condition | Juju Status Type | Status Message | Rationale / Operator Action |
| :---: | :--- | :--- | :--- | :--- |
| **1** | Workload container not connected / Pebble unavailable | `WaitingStatus` | `"Waiting for container"` | Initial pod/container startup phase |
| **2** | `authorization-service-info` relation missing | `BlockedStatus` | `"Missing required relation: authorization-service-info"` | Execute `juju relate authorization-service-worker authorization-service:authorization-service-info` |
| **3** | Database connection credentials missing in info relation | `WaitingStatus` | `"Waiting for database credentials"` | Waiting for server charm to populate database connection data |
| **4** | OpenFGA relation missing | `BlockedStatus` | `"Missing required relation: openfga"` | Execute `juju relate authorization-service-worker openfga-k8s:openfga` |
| **5** | OpenFGA relation address/token not ready | `WaitingStatus` | `"OpenFGA relation is not ready yet"` | Waiting for OpenFGA relation provider data |
| **6** | Server migration version mismatch or data empty | `WaitingStatus` | `"Waiting for the server to run migration"` | Wait for server migration execution |
| **7** | OpenFGA store ID missing | `WaitingStatus` | `"OpenFGA store is not ready yet"` | Waiting for OpenFGA store creation by server/provider |
| **8** | OpenFGA authorization model ID missing in authorization info | `WaitingStatus` | `"Waiting for OpenFGA model creation"` | Waiting for server to create and publish OpenFGA authorization model ID |
| **9** | Container connected, layer planned & service running | `ActiveStatus` | `"Worker active"` (Leader)<br>`"Worker active (no-reaper)"` (Non-leader) | Workload operating normally |


## Design Pattern: Coding Conventions

- **File Headers**: Every source file must begin with `# Copyright 2026 Canonical Ltd.\n# See LICENSE file for licensing details.`. Executable entrypoints (e.g., `src/charm.py`) additionally require `#!/usr/bin/env python3` as the first line.
- **Holistic Handler**: Use a two-level reconciliation pattern in `charm.py`. `_on_holistic_handler(event: ops.HookEvent)` is the shared event handler entry point; it calls a chain of checks then applies the Pebble layer via `PebbleService.plan(self._pebble_layer)`.
- **Status Reporting**: Reported exclusively via `_on_collect_status(event: ops.CollectStatusEvent)` (`collect-unit-status` hook) using `event.add_status()`. Handlers do not set `self.unit.status = ...` directly.
- **Limit `event.defer()`**: Prefer holistic idempotent reconciliation. Deferral is a last resort.
- **Type Hinting**: Strict type annotations without `from __future__ import annotations` (Python >= 3.10).
- **Logging**: Lazy formatting — `logger.info("key: %s", value)`. Do not use f-strings in log calls.
- **Docstrings**: Google-style docstrings for all classes and public methods.

## Decisions

### Decision 1: Charmcraft Packaging with `uv` Plugin and Git Build Packages
- **Choice**: Configure `charmcraft.yaml` to use the `uv` plugin and include `build-packages: [git]`. Define `authorization-service-operator-shared` dependency in `pyproject.toml` using `[tool.uv.sources]`.
- **Rationale**: Ensures `charmcraft pack` build environments can clone git dependencies during package assembly while maintaining fast, reproducible virtualenv builds.

### Decision 2: Reuse `authorization-service-operator-shared` Library & Juju Configs
- **Choice**: Define options in `charmcraft.yaml` (`log_level`, `http_proxy`, `https_proxy`, `no_proxy`, `cpu`, `memory`) and import `authorization-service-operator-shared` modules (`CharmConfig`, `CommandLine`, `PebbleService`, `WorkloadService`, `DatabaseRelationHandler`, `OpenFGARelationHandler`, `MetricsRelationHandler`, `GrafanaDashboardHandler`).
- **Rationale**: Standardizes configuration handling across all Authorization Service operator repositories.

### Decision 3: Kubernetes Resource Patching
- **Choice**: Integrate `KubernetesComputeResourcesPatch` from `charms.observability_libs.v0.kubernetes_compute_resources_patch` to dynamically apply `cpu` and `memory` resource limits from charm configuration to the workload container specification.
- **Rationale**: Allows Juju operators to dynamically adjust compute resource allocations without changing code.

### Decision 4: Authorization Service Info Integration for Migration Tracking
- **Choice**: Integrate `AuthorizationServiceInfoRequirer` from `authorization_service_operator_shared.info` to track server migration status. The worker compares its own workload version against the published migration/workload version from `authorization-service`. If they do not match or info is missing, the worker enters `WaitingStatus("Waiting for the server to run migration")`.
- **Rationale**: Ensures worker workloads do not run against outdated database schemas, deferring schema migration responsibility entirely to the server charm.

### Decision 5: Leader-Dependent Reaper Execution Pattern
- **Choice**: Render Pebble service command dynamically based on `self.unit.is_leader()`:
  - Leader: `/usr/bin/app worker`
  - Non-leader: `/usr/bin/app worker --no-reaper`
  On leadership transition events (`leader_elected`), trigger a charm reconciliation that updates the Pebble layer and calls `container.replan()` to seamlessly migrate reaper responsibility to the new leader.
- **Rationale**: Guarantees single-leader reaper execution without requiring a separate sidecar container binary while ensuring seamless failover on leader changes.

### Decision 6: Priority-Based Status Reconciliation Loop
- **Choice**: Reconcile unit status in a clear, deterministic priority sequence as defined in the Juju Status Mapping Matrix above.
- **Rationale**: Gives operators clear, unambiguous status messages indicating exactly why the charm is blocked or waiting.

## Risks / Trade-offs

- **[Risk]**: Brief dual-reaper execution or delayed transition during leadership re-election.
  - **Mitigation**: Pebble layer re-plan is triggered directly on `leader_elected` events, updating the service command flags immediately.
