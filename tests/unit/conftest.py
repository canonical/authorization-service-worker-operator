# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Shared fixtures for worker charm unit tests."""

from typing import Any

import ops
import pytest
from authorization_service_operator_shared.database import DatabaseConfig
from authorization_service_operator_shared.openfga import OpenFGAConfig
from ops import ActiveStatus, testing
from pytest_mock import MockerFixture

from charm import AuthorizationServiceWorkerCharm
from constants import (
    AUTHORIZATION_SERVICE_INFO_INTEGRATION_NAME,
    CONTAINER_NAME,
    OPENFGA_INTEGRATION_NAME,
)

APP_NAME = "authorization-service-worker"
MODEL_NAME = "testing"

DB_CONFIG = DatabaseConfig(
    host="pg.internal",
    port="5432",
    dbname="authorization_service",
    username="authz_user",
    password="authz_pass",
)

OPENFGA_CONFIG = OpenFGAConfig(
    address="http://openfga.internal:8080",
    store_id="store-abc",
    token="api-key",
)


@pytest.fixture(autouse=True)
def mocked_k8s_resource_patch(mocker: MockerFixture) -> None:
    """Prevent KubernetesComputeResourcesPatch from making real K8s API calls."""
    mocker.patch(
        "charms.observability_libs.v0.kubernetes_compute_resources_patch.ResourcePatcher",
        autospec=True,
    )
    mocker.patch.multiple(
        "charm.KubernetesComputeResourcesPatch",
        _namespace="testing",
        _patch=lambda *a, **kw: None,
        is_ready=lambda *a, **kw: True,
        get_status=lambda *a, **kw: ActiveStatus(),
    )


@pytest.fixture(autouse=True)
def mock_migrate_status(mocker: MockerFixture) -> None:
    """Mock CommandLine.migrate_status to return False (migrations up to date) by default."""
    mocker.patch(
        "authorization_service_operator_shared.cli.CommandLine.migrate_status",
        return_value=False,
    )


def create_state(
    *,
    leader: bool = True,
    can_connect: bool = True,
    config: dict[str, Any] | None = None,
    relations: list[testing.Relation] | None = None,
    secrets: list[testing.Secret] | None = None,
    extra_execs: list[testing.Exec] | None = None,
    service_status: dict[str, ops.pebble.ServiceStatus] | None = None,
) -> testing.State:
    """Build a testing.State with sensible defaults."""
    default_execs: list[testing.Exec] = []
    if can_connect:
        default_execs.append(
            testing.Exec(["/usr/bin/app", "version"], return_code=0, stdout="0.2.1\n")
        )

    if extra_execs:
        default_execs.extend(extra_execs)

    container = testing.Container(
        name=CONTAINER_NAME,
        can_connect=can_connect,
        execs=set(default_execs),
        service_statuses=service_status or {},
    )

    default_secrets = [
        testing.Secret(
            id="secret:123",
            tracked_content={"db-password": "authz_pass"},
            latest_content={"db-password": "authz_pass"},
        )
    ]

    return testing.State(
        containers=[container],
        config=config or {},
        leader=leader,
        model=testing.Model(name=MODEL_NAME),
        relations=relations or [],
        secrets=secrets or default_secrets,
    )


@pytest.fixture
def openfga_relation() -> testing.Relation:
    """Provide a fully-configured openfga relation."""
    return testing.Relation(
        endpoint=OPENFGA_INTEGRATION_NAME,
        interface="openfga",
        remote_app_name="openfga-k8s",
        remote_app_data={
            "grpc_api_url": "grpc://openfga.internal:8081",
            "http_api_url": "http://openfga.internal:8080",
            "store_id": "store-abc-123",
            "token": "openfga-api-key",
            "token_secret_id": "",
        },
    )


@pytest.fixture
def authz_info_relation() -> testing.Relation:
    """Provide a matching authorization-service-info relation."""
    return testing.Relation(
        endpoint=AUTHORIZATION_SERVICE_INFO_INTEGRATION_NAME,
        interface="authorization_service_info",
        remote_app_name="authorization-service",
        remote_app_data={
            "workload_version": "0.2.1",
            "migration_version": "0.2.1",
            "openfga_store_id": "store-abc",
            "openfga_model_id": "model-xyz",
            "db_host": "pg.internal",
            "db_port": "5432",
            "db_name": "authorization_service",
            "db_user": "authz_user",
            "db_secret_id": "secret:123",
        },
    )


@pytest.fixture
def ctx() -> testing.Context:
    """Context fixture for worker charm testing."""
    return testing.Context(AuthorizationServiceWorkerCharm)
