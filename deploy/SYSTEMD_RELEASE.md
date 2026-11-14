# Systemd user release inputs

The shared VPS uses `systemd --user`, an immutable `current` symlink, and
runtime data below `/home/kripta/apps/vexplorer/shared`. It does not consume
the Docker-oriented `production.env.example`: names such as
`VEXPLORER_USERS_FILE_HOST`, `VEXPLORER_COST_CATALOG_HOST`, and
`VEXPLORER_DATA_VOLUME` belong to Compose interpolation and are not read by
`create_app`.

Start from `deploy/systemd-production.env.example`, copy it outside the
release to `shared/production.env`, replace the provider placeholder in the
protected copy, and keep mode `0600`. Preserve the existing users file,
catalog, origin, public-auth decision, and all secret values during an
upgrade. Apply changes through an atomic temporary-file rename; never source
or print the env in an operator transcript.

Before changing `current`, stop only `vexplorer.service` and create a backup
with `tools.backup create --quiescent`. Quiescent mode opens source databases
read-only and immutable, and fails if a non-empty `-wal` or `-journal` exists;
it must never ignore committed WAL rows. Verify and restore the archive to a
new directory, then run the exact candidate against that restored data on a
loopback-only port. Activation requires the external candidate gate, an
atomic symlink swap, and restart of only `vexplorer.service`.

The optional backup timer is installed only after explicit operator approval.
It checks for queued/running jobs, briefly quiesces only Vexplorer, verifies
the new archive, retains at most 2 GiB of `scheduled-*` archives, and leaves
manual, accepted, and predeploy backups untouched.
