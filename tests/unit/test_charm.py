# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for Authorization Service Worker Operator."""

import dataclasses

from authorization_service_operator_shared.constants import PEBBLE_SERVICE_NAME
from authorization_service_operator_shared.exceptions import WorkloadError
from authorization_service_operator_shared.openfga import OpenFGAConfig
from conftest import create_state
from ops import ActiveStatus, BlockedStatus, WaitingStatus, testing


def test_cannot_connect_status(ctx: testing.Context) -> None:
    """Test unit status when container cannot connect."""
    state = create_state(can_connect=False)
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == WaitingStatus("Waiting for container")


def test_missing_database_relation_status(
    ctx: testing.Context,
    openfga_relation: testing.Relation,
) -> None:
    """Test unit status when database connection details are missing from info relation."""
    empty_info_relation = testing.Relation(
        endpoint="authorization-service-info",
        interface="authorization_service_info",
        remote_app_name="authorization-service",
        remote_app_data={},
    )
    state = create_state(relations=[openfga_relation, empty_info_relation])
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == WaitingStatus("Waiting for database credentials")


def test_database_config_provided_by_authz_info_relation(
    ctx: testing.Context,
    mocker,
    openfga_relation: testing.Relation,
    authz_info_relation: testing.Relation,
) -> None:
    """Test unit status is active when database credentials are provided by authz_info_relation."""
    mocker.patch(
        "authorization_service_operator_shared.cli.CommandLine.migrate_status",
        return_value=False,
    )
    state = create_state(
        leader=True,
        relations=[openfga_relation, authz_info_relation],
    )
    out_plan = ctx.run(ctx.on.config_changed(), state)
    out_status = ctx.run(ctx.on.collect_unit_status(), out_plan)

    assert out_status.unit_status == ActiveStatus("Worker active")


def test_missing_openfga_relation_status(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
) -> None:
    """Test unit status when OpenFGA relation is missing."""
    state = create_state(relations=[authz_info_relation])
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == BlockedStatus("Missing required relation: openfga")


def test_missing_info_relation_status(
    ctx: testing.Context,
    openfga_relation: testing.Relation,
) -> None:
    """Test unit status when authorization-service-info relation is missing."""
    state = create_state(
        leader=True,
        relations=[openfga_relation],
    )
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == BlockedStatus(
        "Missing required relation: authorization-service-info"
    )


def test_waiting_migration_status_when_data_missing(
    ctx: testing.Context,
    openfga_relation: testing.Relation,
) -> None:
    """Test unit status waiting for database credentials when authorization-service-info relation exists but data is empty."""
    empty_info_relation = testing.Relation(
        endpoint="authorization-service-info",
        interface="authorization_service_info",
        remote_app_name="authorization-service",
        remote_app_data={},
    )
    state = create_state(
        leader=True,
        relations=[openfga_relation, empty_info_relation],
    )
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == WaitingStatus("Waiting for database credentials")


def test_waiting_migration_status_when_migration_pending(
    ctx: testing.Context,
    mocker,
    openfga_relation: testing.Relation,
    authz_info_relation: testing.Relation,
) -> None:
    """Test unit status waiting for migration when migrate_status returns True."""
    mocker.patch(
        "authorization_service_operator_shared.cli.CommandLine.migrate_status",
        return_value=True,
    )
    state = create_state(
        leader=True,
        relations=[openfga_relation, authz_info_relation],
    )
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == WaitingStatus("Waiting for the server to run migration")


def test_waiting_migration_status_when_migrate_status_raises_workload_error(
    ctx: testing.Context,
    mocker,
    openfga_relation: testing.Relation,
    authz_info_relation: testing.Relation,
) -> None:
    """Test unit status waiting for migration when migrate_status raises WorkloadError."""
    mocker.patch(
        "authorization_service_operator_shared.cli.CommandLine.migrate_status",
        side_effect=WorkloadError("Failed to check migration status"),
    )
    state = create_state(
        leader=True,
        relations=[openfga_relation, authz_info_relation],
    )
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == WaitingStatus("Waiting for the server to run migration")


def test_leader_worker_command(
    ctx: testing.Context,
    openfga_relation: testing.Relation,
    authz_info_relation: testing.Relation,
) -> None:
    """Test leader unit Pebble layer service command does not include --no-reaper."""
    state = create_state(
        leader=True,
        relations=[openfga_relation, authz_info_relation],
    )
    out = ctx.run(ctx.on.config_changed(), state)

    container = out.get_container("worker")
    service = container.plan.services[PEBBLE_SERVICE_NAME]
    assert service.command == "/usr/bin/app worker"


def test_non_leader_worker_command(
    ctx: testing.Context,
    openfga_relation: testing.Relation,
    authz_info_relation: testing.Relation,
) -> None:
    """Test non-leader unit Pebble layer service command includes --no-reaper flag."""
    state = create_state(
        leader=False,
        relations=[openfga_relation, authz_info_relation],
    )
    out = ctx.run(ctx.on.config_changed(), state)

    container = out.get_container("worker")
    service = container.plan.services[PEBBLE_SERVICE_NAME]
    assert service.command == "/usr/bin/app worker --no-reaper"


def test_leader_elected_transition(
    ctx: testing.Context,
    openfga_relation: testing.Relation,
    authz_info_relation: testing.Relation,
) -> None:
    """Test leader transition updates Pebble layer service command dynamically."""
    state = create_state(
        leader=False,
        relations=[openfga_relation, authz_info_relation],
    )
    out_non_leader = ctx.run(ctx.on.config_changed(), state)

    container = out_non_leader.get_container("worker")
    assert (
        container.plan.services[PEBBLE_SERVICE_NAME].command == "/usr/bin/app worker --no-reaper"
    )

    # Simulate unit elected as leader
    state_leader = dataclasses.replace(out_non_leader, leader=True)
    out_leader = ctx.run(ctx.on.leader_elected(), state_leader)

    container_updated = out_leader.get_container("worker")
    assert container_updated.plan.services[PEBBLE_SERVICE_NAME].command == "/usr/bin/app worker"


def test_leader_demoted_transition(
    ctx: testing.Context,
    openfga_relation: testing.Relation,
    authz_info_relation: testing.Relation,
) -> None:
    """Test that when a leader unit is demoted, updating status updates service command to --no-reaper."""
    state_leader = create_state(
        leader=True,
        relations=[openfga_relation, authz_info_relation],
    )
    out_leader = ctx.run(ctx.on.config_changed(), state_leader)

    container_leader = out_leader.get_container("worker")
    assert container_leader.plan.services[PEBBLE_SERVICE_NAME].command == "/usr/bin/app worker"

    # Simulate unit losing leadership and status being updated
    state_demoted = dataclasses.replace(out_leader, leader=False)
    out_demoted = ctx.run(ctx.on.update_status(), state_demoted)

    container_demoted = out_demoted.get_container("worker")
    assert (
        container_demoted.plan.services[PEBBLE_SERVICE_NAME].command
        == "/usr/bin/app worker --no-reaper"
    )


def test_active_status_leader(
    ctx: testing.Context,
    mocker,
    openfga_relation: testing.Relation,
    authz_info_relation: testing.Relation,
) -> None:
    """Test active status message on leader unit."""
    mocker.patch(
        "authorization_service_operator_shared.cli.CommandLine.migrate_status",
        return_value=False,
    )
    state = create_state(
        leader=True,
        relations=[openfga_relation, authz_info_relation],
    )
    out_plan = ctx.run(ctx.on.config_changed(), state)
    out_status = ctx.run(ctx.on.collect_unit_status(), out_plan)

    assert out_status.unit_status == ActiveStatus("Worker active")


def test_active_status_non_leader(
    ctx: testing.Context,
    mocker,
    openfga_relation: testing.Relation,
    authz_info_relation: testing.Relation,
) -> None:
    """Test active status message on non-leader unit."""
    mocker.patch(
        "authorization_service_operator_shared.cli.CommandLine.migrate_status",
        return_value=False,
    )
    state = create_state(
        leader=False,
        relations=[openfga_relation, authz_info_relation],
    )
    out_plan = ctx.run(ctx.on.config_changed(), state)
    out_status = ctx.run(ctx.on.collect_unit_status(), out_plan)

    assert out_status.unit_status == ActiveStatus("Worker active (no-reaper)")


def test_waiting_openfga_store_status_when_store_missing(
    ctx: testing.Context,
    mocker,
    openfga_relation: testing.Relation,
) -> None:
    """Test unit status waiting for OpenFGA store when store ID is missing from info relation and OpenFGA relation."""
    mocker.patch("charm.OpenFGARelationHandler.is_ready", return_value=True)
    mocker.patch(
        "charm.OpenFGARelationHandler.config",
        OpenFGAConfig(address="http://openfga.internal:8080", store_id="", token="api-key"),
    )
    mocker.patch(
        "authorization_service_operator_shared.cli.CommandLine.migrate_status",
        return_value=False,
    )
    missing_store_info_relation = testing.Relation(
        endpoint="authorization-service-info",
        interface="authorization_service_info",
        remote_app_name="authorization-service",
        remote_app_data={
            "openfga_store_id": "",
            "openfga_model_id": "",
            "db_host": "pg.internal",
            "db_port": "5432",
            "db_name": "authorization_service",
            "db_user": "authz_user",
            "db_secret_id": "secret:123",
        },
    )
    state = create_state(
        leader=True,
        relations=[openfga_relation, missing_store_info_relation],
    )
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == WaitingStatus("OpenFGA store is not ready yet")


def test_waiting_openfga_model_status_when_model_missing(
    ctx: testing.Context,
    mocker,
    openfga_relation: testing.Relation,
) -> None:
    """Test unit status waiting for OpenFGA model when model ID is missing from info relation."""
    mocker.patch(
        "authorization_service_operator_shared.cli.CommandLine.migrate_status",
        return_value=False,
    )
    missing_model_info_relation = testing.Relation(
        endpoint="authorization-service-info",
        interface="authorization_service_info",
        remote_app_name="authorization-service",
        remote_app_data={
            "workload_version": "0.2.1",
            "migration_version": "0.2.1",
            "openfga_store_id": "store-abc",
            "openfga_model_id": "",
            "db_host": "pg.internal",
            "db_port": "5432",
            "db_name": "authorization_service",
            "db_user": "authz_user",
            "db_secret_id": "secret:123",
        },
    )
    state = create_state(
        leader=True,
        relations=[openfga_relation, missing_model_info_relation],
    )
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == WaitingStatus("Waiting for OpenFGA model creation")


def test_pebble_layer_contains_shared_openfga_model_id(
    ctx: testing.Context,
    openfga_relation: testing.Relation,
    authz_info_relation: testing.Relation,
) -> None:
    """Test that the Pebble layer environment contains OPENFGA_AUTHORIZATION_MODEL_ID from info relation."""
    state = create_state(
        leader=True,
        relations=[openfga_relation, authz_info_relation],
    )
    out = ctx.run(ctx.on.config_changed(), state)

    container = out.get_container("worker")
    service = container.plan.services[PEBBLE_SERVICE_NAME]
    assert service.environment.get("OPENFGA_AUTHORIZATION_MODEL_ID") == "model-xyz"


def test_openfga_config_exception_handling(
    ctx: testing.Context,
    mocker,
    openfga_relation: testing.Relation,
    authz_info_relation: testing.Relation,
) -> None:
    """Test that charm handles exceptions from openfga_handler.config gracefully without crashing."""
    mocker.patch(
        "authorization_service_operator_shared.openfga.OpenFGARelationHandler.config",
        new_callable=mocker.PropertyMock,
        side_effect=Exception("Secret not found yet"),
    )
    state = create_state(
        leader=False,
        relations=[openfga_relation, authz_info_relation],
    )
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == WaitingStatus("OpenFGA relation is not ready yet")
