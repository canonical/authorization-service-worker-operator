## ADDED Requirements

### Requirement: Database Credentials via Authorization Service Info Relation
The worker operator SHALL receive PostgreSQL database connection parameters (`POSTGRES_*`) from `authorization-service-info` relation using `AuthorizationServiceInfoRequirer` from `authorization_service_operator_shared.info` and set appropriate status based on credential availability.

#### Scenario: Database credentials missing
- **WHEN** `authorization-service-info` relation is connected but database connection parameters are missing or empty
- **THEN** the charm enters `WaitingStatus("Waiting for database credentials")`

#### Scenario: Database credentials ready
- **WHEN** database connection details are available in `authorization-service-info` relation data
- **THEN** worker workload environment is populated with database connection variables (`POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_SSL_MODE`)

### Requirement: Authorization Service Info Relation Integration
The worker operator SHALL integrate with `authorization-service-info` relation using `AuthorizationServiceInfoRequirer` from `authorization_service_operator_shared.info` to track server migration status.

#### Scenario: Authorization service info relation missing
- **WHEN** `authorization-service-info` relation is missing or not joined
- **THEN** the charm enters `BlockedStatus("Missing required relation: authorization-service-info")`

#### Scenario: Server migration pending or version mismatch
- **WHEN** `authorization-service-info` relation is joined but server info is missing, empty, or published migration version does not match worker workload version
- **THEN** the charm enters `WaitingStatus("Waiting for the server to run migration")`

#### Scenario: Server migration updated event
- **WHEN** `authorization_service_info_updated` event is emitted on relation update
- **THEN** the charm re-triggers reconciliation to evaluate version parity and start worker service if matched

### Requirement: OpenFGA Relation Integration and Status Rules
The worker operator SHALL integrate with OpenFGA relation using `OpenFGARelationHandler` from `authorization-service-operator-shared` and set appropriate charm status based on relation, store, and model state.

#### Scenario: OpenFGA relation missing
- **WHEN** OpenFGA relation is missing or not joined
- **THEN** the charm enters `BlockedStatus("Missing required relation: openfga")`

#### Scenario: OpenFGA relation not ready
- **WHEN** OpenFGA relation exists but address or token details are not yet populated
- **THEN** the charm enters `WaitingStatus("OpenFGA relation is not ready yet")`

#### Scenario: OpenFGA store not ready
- **WHEN** OpenFGA relation exists but the OpenFGA store is not yet created or ready
- **THEN** the charm enters `WaitingStatus("OpenFGA store is not ready yet")`

#### Scenario: OpenFGA model not ready
- **WHEN** OpenFGA store is ready but OpenFGA model ID has not yet been published by the server via `authorization-service-info`
- **THEN** the charm enters `WaitingStatus("Waiting for OpenFGA model creation")`

#### Scenario: OpenFGA store and model ready
- **WHEN** OpenFGA relation exists, OpenFGA store is ready, and OpenFGA model ID is populated from `authorization-service-info`
- **THEN** worker workload environment is populated with OpenFGA connection variables and `OPENFGA_AUTHORIZATION_MODEL_ID`

### Requirement: COS Observability Integration
The worker operator SHALL integrate with Prometheus metrics scrape target and Grafana dashboard registration using `MetricsRelationHandler` and `GrafanaDashboardHandler` from `authorization-service-operator-shared`.

#### Scenario: Metrics relation connected
- **WHEN** `metrics-endpoint` relation is established
- **THEN** Prometheus scrape endpoint is published and metrics environment variables are passed to the workload

