# Retired Duplicati recovery artifacts

Duplicati was retired on 2026-07-14 after the replacement Syncthing Restic
backup completed, passed `check --read-data`, and restored successfully into an
isolated disposable volume.

Only `storage.yaml` remains reconciled. It preserves the `duplicati-config`
Longhorn PVC. The unused `duplicati-backups` NFS PV/PVC and its dedicated
writable export were removed, while the empty underlying directory remains on
the Pi. The Deployment, Services, route, NetworkPolicy, access-proxy ConfigMap,
and live Secret are not active resources. Their manifests and the
SOPS-encrypted settings key remain in this directory solely for recovery
analysis.

The retained PVC explicitly disables membership in Longhorn's default
recurring-job group. Its data is frozen and already has named final recovery
points; attaching and backing it up nightly creates no useful new recovery
state and can leave snapshot cleanup pending after the detached engine stops.
Do not remove that opt-out unless the archive is deliberately mounted and made
writable again.

Do not re-add the retired resources to `kustomization.yaml` as a routine
rollback. First preserve the config volume, old native-B2 repository, AES
passphrase dependency, and local database; then follow the recovery cautions in
`docs/runbook.md`. Never point Restic at the Duplicati bucket or modify that
repository with Restic.
