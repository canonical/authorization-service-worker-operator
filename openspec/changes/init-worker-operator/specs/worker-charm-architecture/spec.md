## ADDED Requirements

### Requirement: Worker Workload Service Command
The worker operator SHALL define a Pebble layer service running the workload binary `/usr/bin/app worker`.

#### Scenario: Worker service execution
- **WHEN** Pebble container starts and layer is rendered
- **THEN** the workload service command is set to `/usr/bin/app worker` with appropriate runtime flags

### Requirement: Worker Workload Configuration
The worker operator SHALL configure `WorkerConfig` to set `WORKER_ENABLED=true` in the Pebble layer workload environment.

#### Scenario: Worker enabled configuration
- **WHEN** Pebble layer is rendered for the worker container
- **THEN** the workload environment contains `WORKER_ENABLED=true`

### Requirement: Juju Charm Configuration
The worker operator SHALL define standard charm options in `charmcraft.yaml` including `log_level`, `http_proxy`, `https_proxy`, `no_proxy`, `cpu`, and `memory`.

#### Scenario: Configuration parsing
- **WHEN** user updates charm config via `juju config`
- **THEN** `CharmConfig` from `authorization-service-operator-shared` parses logging levels and proxy environment variables for the workload

### Requirement: Kubernetes Resource Patching
The worker operator SHALL apply Kubernetes resource limits and requests for workload containers based on `cpu` and `memory` charm configurations using `KubernetesComputeResourcesPatch`.

#### Scenario: Resource limits updated
- **WHEN** user updates `cpu` or `memory` configuration options
- **THEN** `KubernetesComputeResourcesPatch` applies updated container resource limits to the workload pod specification

### Requirement: Authorization Service Info Version Verification
The worker operator SHALL compare its workload version with the version provided by `authorization_service_info` lib and set `WaitingStatus("Waiting for the server to run migration")` if they do not match or databag is empty.

#### Scenario: Version mismatch or info data empty
- **WHEN** `authorization-service-info` relation is joined but server info is empty or server migration version does not match worker workload version
- **THEN** the worker charm enters `WaitingStatus("Waiting for the server to run migration")` and defers workload service planning

#### Scenario: Version match
- **WHEN** `authorization-service-info` relation returns a migration version matching worker workload version
- **THEN** the worker charm proceeds with workload service planning and transitions to active status

### Requirement: Leader-Dependent Reaper Execution
The worker operator SHALL configure the worker service command with the `--no-reaper` flag on non-leader units, and without `--no-reaper` on the leader unit.

#### Scenario: Leader unit service execution
- **WHEN** the unit is elected leader
- **THEN** the worker service command runs without `--no-reaper` flag so that background reaper tasks execute on the leader

#### Scenario: Non-leader unit service execution
- **WHEN** the unit is not the leader
- **THEN** the worker service command runs with `--no-reaper` flag to prevent duplicate reaper execution

### Requirement: Leader Transition Reaper Management
The worker operator SHALL handle leadership transition events such that when leadership changes, any demoted unit stops running the reaper process and the newly elected leader starts running the reaper process.

#### Scenario: Leadership transition event
- **WHEN** leadership status changes across units
- **THEN** the previous leader stops the reaper execution (re-planning worker with `--no-reaper`) and the new leader re-plans worker without `--no-reaper` to start the reaper process

### Requirement: Packaging with UV Plugin
The worker operator SHALL configure `charmcraft.yaml` to build using the `uv` plugin for fast, reliable dependency resolution and packaging.

#### Scenario: Charmcraft build
- **WHEN** `charmcraft pack` is executed on the charm directory
- **THEN** charmcraft builds the charm package using the `uv` plugin
