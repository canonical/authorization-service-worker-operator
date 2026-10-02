# Charmed Authorization Service Worker Operator

A Charmed Operator managing background queue processing and periodic cleanup/reaper tasks for the Charmed Authorization Service.

## Description

The Authorization Service Worker Operator runs as a Kubernetes workload executing `/usr/bin/app worker`. On the leader unit, it executes background reaper duties alongside standard worker processing. On non-leader units, it executes in worker-only mode (`/usr/bin/app worker --no-reaper`).

## Usage

### Deployment

To deploy the worker operator on Kubernetes using Juju:

```bash
juju deploy ./authorization-service-worker*.charm authorization-service-worker --resource oci-image=$(yq eval '.resources.oci-image.upstream-source' charmcraft.yaml) --trust
```

### Integrations

The worker charm requires relations with OpenFGA and the Authorization Service server charm:

```bash
# Relate to OpenFGA
juju integrate authorization-service-worker openfga-k8s:openfga

# Relate to Authorization Service Server (for migration/version tracking)
juju integrate authorization-service-worker authorization-service:authorization-service-info

# Optionally, relate to COS Observability Stack
juju integrate authorization-service-worker prometheus-k8s:metrics-endpoint
juju integrate authorization-service-worker grafana-k8s:grafana-dashboard
```

### Server Migration Synchronization

The worker charm tracks server migration status via the `authorization-service-info` relation. When the server has not yet executed migrations for the matching workload version, the worker unit enters `WaitingStatus("Waiting for the server to run migration")` and defers workload startup until the server completes migration.

## License

The Charmed Authorization Service Worker Operator is free software, distributed under the Apache Software License, version 2.0. See [LICENSE](LICENSE) for more details.
