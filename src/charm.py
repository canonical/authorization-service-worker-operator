#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed Operator for Authorization Service Worker."""

import logging

import ops
from authorization_service_operator_shared.cli import CommandLine
from authorization_service_operator_shared.configs import CharmConfig
from authorization_service_operator_shared.constants import PEBBLE_SERVICE_NAME
from authorization_service_operator_shared.database import DatabaseConfig
from authorization_service_operator_shared.exceptions import WorkloadError
from authorization_service_operator_shared.info import AuthorizationServiceInfoRequirer
from authorization_service_operator_shared.observability import (
    GrafanaDashboardHandler,
    MetricsRelationHandler,
)
from authorization_service_operator_shared.openfga import (
    OpenFGAConfig,
    OpenFGARelationHandler,
)
from authorization_service_operator_shared.services import PebbleService, WorkloadService
from authorization_service_operator_shared.utils import container_connectivity
from charms.observability_libs.v0.kubernetes_compute_resources_patch import (
    KubernetesComputeResourcesPatch,
    ResourceRequirements,
    adjust_resource_requirements,
)
from charms.openfga_k8s.v1.openfga import (
    OpenFGARequires,
    OpenFGAStoreRemovedEvent,
)

from constants import (
    AUTHORIZATION_SERVICE_INFO_INTEGRATION_NAME,
    CONTAINER_NAME,
    GRAFANA_INTEGRATION_NAME,
    METRICS_INTEGRATION_NAME,
    OPENFGA_INTEGRATION_NAME,
)

logger = logging.getLogger(__name__)


class AuthorizationServiceWorkerCharm(ops.CharmBase):
    """Worker charm for Canonical Authorization Service."""

    def __init__(self, framework: ops.Framework) -> None:
        """Initialize the charm worker."""
        super().__init__(framework)

        container = self.unit.get_container(CONTAINER_NAME)
        self._cli = CommandLine(container)
        self._pebble_service = PebbleService(
            container,
            service_name=PEBBLE_SERVICE_NAME,
            command=self._worker_command,
        )
        self._workload_service = WorkloadService(
            self.unit,
            self._cli,
            container,
            service_name=PEBBLE_SERVICE_NAME,
        )

        self._charm_config = CharmConfig(self.model.config)

        # Kubernetes resource patch
        self.resources_patch = KubernetesComputeResourcesPatch(
            self,
            CONTAINER_NAME,
            resource_reqs_func=self._resource_reqs_from_config,
        )

        # Relation handlers
        self._openfga_requires = OpenFGARequires(
            self,
            store_name="authorization-service",
            relation_name=OPENFGA_INTEGRATION_NAME,
        )
        self.openfga_handler = OpenFGARelationHandler(self._openfga_requires)
        self.authz_info = AuthorizationServiceInfoRequirer(
            self,
            relation_name=AUTHORIZATION_SERVICE_INFO_INTEGRATION_NAME,
        )
        self.metrics_handler = MetricsRelationHandler(
            self,
            relation_name=METRICS_INTEGRATION_NAME,
        )
        self.grafana_handler = GrafanaDashboardHandler(
            self,
            relation_name=GRAFANA_INTEGRATION_NAME,
        )

        # Register event observers
        self.framework.observe(self.on.collect_unit_status, self._on_collect_status)
        self.framework.observe(self.on.leader_elected, self._on_holistic_handler)
        self.framework.observe(self.on.leader_settings_changed, self._on_holistic_handler)
        self.framework.observe(self.on.update_status, self._on_holistic_handler)

        self.framework.observe(self.on.config_changed, self._on_holistic_handler)
        self.framework.observe(self.on.worker_pebble_ready, self._on_pebble_ready)
        self.framework.observe(
            self._openfga_requires.on.openfga_store_created, self._on_holistic_handler
        )
        self.framework.observe(
            self._openfga_requires.on.openfga_store_removed, self._on_openfga_store_removed
        )
        self.framework.observe(
            self.authz_info.on.authorization_service_info_updated,
            self._on_holistic_handler,
        )
        self.framework.observe(
            self.authz_info.on.authorization_service_info_broken,
            self._on_holistic_handler,
        )

    @property
    def _worker_command(self) -> str:
        """Return worker startup command based on unit leadership."""
        if self.unit.is_leader():
            return "/usr/bin/app worker"
        return "/usr/bin/app worker --no-reaper"

    def _resource_reqs_from_config(self) -> ResourceRequirements:
        """Build resource requirements from charm config."""
        limits = {"cpu": self.model.config.get("cpu"), "memory": self.model.config.get("memory")}
        requests = {"cpu": "100m", "memory": "200Mi"}
        return adjust_resource_requirements(limits, requests, adhere_to_requests=True)

    @property
    def _database_config(self) -> DatabaseConfig:
        """Return database config from server info relation."""
        info = self.authz_info.get_info()
        if info and info.is_db_ready:
            return DatabaseConfig.from_info(info)
        return DatabaseConfig()

    @property
    def _is_database_ready(self) -> bool:
        """True if database connection details are provided by server info relation."""
        return self._database_config.is_ready

    @property
    def _openfga_config(self) -> OpenFGAConfig:
        """Combine OpenFGA relation details (address, token) with server info (store_id, model_id)."""
        info = self.authz_info.get_info()
        try:
            fga_rel = self.openfga_handler.config
        except Exception as exc:
            logger.warning("Failed to retrieve OpenFGA relation config: %s", exc)
            fga_rel = OpenFGAConfig()

        store_id = (
            info.openfga_store_id if info and info.openfga_store_id else ""
        ) or fga_rel.store_id
        model_id = info.openfga_model_id if info else ""
        return OpenFGAConfig(
            address=fga_rel.address,
            token=fga_rel.token,
            store_id=store_id,
            authorization_model_id=model_id,
        )

    @property
    def _is_openfga_ready(self) -> bool:
        """True if OpenFGA address, token, store_id, and model_id are all non-empty."""
        cfg = self._openfga_config
        return cfg.is_ready and bool(cfg.authorization_model_id)

    @property
    def _pebble_layer(self) -> ops.pebble.Layer:
        """Render Pebble layer with updated command and env vars."""
        return self._pebble_service.render_pebble_layer(
            self._charm_config,
            self._database_config,
            self._openfga_config,
            command=self._worker_command,
            include_checks=False,
        )

    @property
    def _is_info_relation_present(self) -> bool:
        """True if authorization-service-info relation exists."""
        return bool(self.model.get_relation(AUTHORIZATION_SERVICE_INFO_INTEGRATION_NAME))

    @property
    def _server_migration_outdated(self) -> bool:
        """True if server migration is pending according to migrate_status."""
        if not container_connectivity(self, CONTAINER_NAME):
            return True
        if not self._is_database_ready:
            return True
        try:
            return self._cli.migrate_status(self._database_config.dsn)
        except WorkloadError as exc:
            logger.error("Failed to check migration status: %s", exc)
            return True

    @property
    def _is_openfga_relation_ready(self) -> bool:
        """True if OpenFGA relation details (address, token) are ready."""
        cfg = self._openfga_config
        return bool(cfg.address and cfg.token)

    def _on_holistic_handler(self, _event: ops.HookEvent) -> None:
        """Apply workload layer when all prerequisite relations are satisfied."""
        if (
            not container_connectivity(self, CONTAINER_NAME)
            or not self._is_info_relation_present
            or not self._is_database_ready
            or self._server_migration_outdated
            or not self._is_openfga_ready
        ):
            return

        self._pebble_service.plan(self._pebble_layer)

    def _on_pebble_ready(self, event: ops.PebbleReadyEvent) -> None:
        """Handle Pebble ready event."""
        self._on_holistic_handler(event)
        self._workload_service.update_workload_version()

    def _on_openfga_store_removed(self, event: OpenFGAStoreRemovedEvent) -> None:
        """Handle OpenFGA store removed — stop the workload."""
        self._pebble_service.stop()
        self._on_holistic_handler(event)

    def _on_collect_status(self, event: ops.CollectStatusEvent) -> None:  # noqa: C901
        """Collect unit status deterministically in priority order."""
        if not container_connectivity(self, CONTAINER_NAME):
            event.add_status(ops.WaitingStatus("Waiting for container"))
            return

        if not self.model.relations.get(AUTHORIZATION_SERVICE_INFO_INTEGRATION_NAME):
            event.add_status(
                ops.BlockedStatus(
                    f"Missing required relation: {AUTHORIZATION_SERVICE_INFO_INTEGRATION_NAME}"
                )
            )
            return

        if not self._is_database_ready:
            event.add_status(ops.WaitingStatus("Waiting for database credentials"))
            return

        if not self.model.relations.get(OPENFGA_INTEGRATION_NAME):
            event.add_status(
                ops.BlockedStatus(f"Missing required relation: {OPENFGA_INTEGRATION_NAME}")
            )
            return

        if not self._is_openfga_relation_ready:
            event.add_status(ops.WaitingStatus("OpenFGA relation is not ready yet"))
            return

        if self._server_migration_outdated:
            event.add_status(ops.WaitingStatus("Waiting for the server to run migration"))
            return

        if not self._openfga_config.store_id:
            event.add_status(ops.WaitingStatus("OpenFGA store is not ready yet"))
            return

        if not self._openfga_config.authorization_model_id:
            event.add_status(ops.WaitingStatus("Waiting for OpenFGA model creation"))
            return

        if not self._workload_service.is_running():
            event.add_status(ops.WaitingStatus("Waiting for workload to start"))
            return

        # Only add resource patch status if non-active to avoid overwriting worker active message
        patch_status = self.resources_patch.get_status()
        if not isinstance(patch_status, ops.ActiveStatus):
            event.add_status(patch_status)

        status_msg = "Worker active" if self.unit.is_leader() else "Worker active (no-reaper)"
        event.add_status(ops.ActiveStatus(status_msg))


if __name__ == "__main__":
    ops.main(AuthorizationServiceWorkerCharm)
