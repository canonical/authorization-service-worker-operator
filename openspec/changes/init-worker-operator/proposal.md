## Why

The Charmed Authorization Service architecture requires a dedicated worker operator (`authorization-service-worker-operator`) to run background processing and execute periodic cleanup/reaper tasks. Establishing this worker operator using standard Canonical Charmed Operator patterns and leveraging the shared operator library ensures consistent integration handling across the entire Authorization Service component family.

## What Changes

- Initialize the `authorization-service-worker-operator` charm repository using the `uv` build plugin in `charmcraft.yaml`.
- Define standard Juju charm configurations in `charmcraft.yaml` (`log_level`, `http_proxy`, `https_proxy`, `no_proxy`, `cpu`, `memory`).
- Consume `AuthorizationServiceInfoRequirer` from `authorization_service_operator_shared.info` to receive database connection parameters (`POSTGRES_*`) and deployment/model version info from the server charm (`authorization-service`).
- Implement workload version verification comparing worker's workload version against server info, setting `WaitingStatus("Waiting for the server to run migration")` on version mismatch or missing info relation data.
- Observe `authorization_service_info_updated` event to automatically reconcile when database migrations are completed by the server charm.
- Implement Kubernetes Resource Patching for `cpu` and `memory` limits using `KubernetesComputeResourcesPatch`.
- Integrate the `authorization-service-operator-shared` library to handle common core configurations (`CharmConfig`), Pebble services, CLI commands, info sharing, exceptions, and relation integrations (`openfga`, `metrics-endpoint`, `grafana-dashboard`).
- Implement workload service management for running the `/usr/bin/app worker` command inside Pebble containers with Pebble service name `authorization-service` (overriding default OCI image definition) and stripping HTTP probes.
- Implement leader unit side-service orchestration:
  - Leader unit runs the `worker` workload with reaper capabilities enabled (`/usr/bin/app worker`).
  - Non-leader units execute the worker command with the `--no-reaper` flag (`/usr/bin/app worker --no-reaper`).
  - On leader transition events, the demoted unit stops its reaper process and the newly elected leader starts the reaper process.
- Wire relation handlers for OpenFGA (`openfga`), Authorization Service Info (`authorization-service-info`), and COS Observability (Metrics & Dashboards).
- Enforce explicit charm statuses:
  - `BlockedStatus("Missing required relation: authorization-service-info")` when authorization-service-info relation is missing.
  - `BlockedStatus("Missing required relation: openfga")` when OpenFGA relation is missing.
  - `WaitingStatus("Waiting for database credentials")` when database connection details are missing from info relation.
  - `WaitingStatus("OpenFGA relation is not ready yet")` / `WaitingStatus("OpenFGA store is not ready yet")` / `WaitingStatus("Waiting for OpenFGA model creation")` when OpenFGA configuration is incomplete.
  - `WaitingStatus("Waiting for the server to run migration")` when server migration version does not match worker workload version.

## Capabilities

### New Capabilities
- `worker-charm-architecture`: Defines worker charm orchestration, Pebble container layer definitions, Juju charm configs (`log_level`, proxy settings, resource limits), Kubernetes Resource Patching, leader transition reaper handling, `uv` packaging configuration, unit status reporting, and server migration version check handling.
- `worker-integrations`: Connects worker charm with required relations (PostgreSQL `pg-database`, OpenFGA, Authorization Service Info, Metrics, Grafana Dashboards) using shared library handlers.

### Modified Capabilities
<!-- None -->

## Impact

- Affected Repository: `authorization-service-worker-operator`
- Dependencies: `ops>=2.0.0`, `authorization-service-operator-shared`, `lightkube`
- Infrastructure: Kubernetes container workloads running `/usr/bin/app worker`
