# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

/**
 * # Terraform module for the authorization-service-worker charm
 *
 * This is a Terraform module facilitating the deployment of the authorization-service-worker
 * charm using the Juju Terraform provider.
 */

resource "juju_application" "authorization_service_worker" {
  name        = var.app_name
  model_uuid  = var.model_uuid
  config      = var.config
  constraints = var.constraints
  resources   = var.resources
  units       = var.units
  trust       = true

  charm {
    name     = "authorization-service-worker"
    base     = var.base
    channel  = var.channel
    revision = var.revision
  }
}
