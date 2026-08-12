# GitHub development and deployment workflow

GitHub is the source of truth for Software Release Radar. Development changes should move from a writable development checkout into a branch and pull request, pass GitHub Actions, and reach production only after review and merge.

## Separation of responsibilities

| Location | Purpose | GitHub access |
|---|---|---|
| Development checkout | Edit, test, commit and push branches | Write access through a dedicated SSH key or GitHub CLI |
| GitHub Actions | Run tests, security checks and public Docker acceptance | Repository-scoped workflow token |
| Production checkout | Fetch approved source and deploy it | Read-only HTTPS access is sufficient for this public repository |
| GitHub Container Registry | Store tagged multi-architecture release images | Anonymous pull access for the public package |

Do not store a GitHub write token or a maintainer SSH key on the production host. Production should not push source changes.

Do not attach a production host as a self-hosted runner for this public repository. Pull requests and forked code must not receive an execution path into production infrastructure.

## Development setup

Clone the repository on the development machine:

```bash
git clone git@github.com:muhdusama/Software-Release-Radar.git
cd Software-Release-Radar
git remote -v
```

Create a focused branch for each change:

```bash
git switch main
git pull --ff-only
git switch -c feature/descriptive-name
```

Run the project checks before pushing:

```bash
python -m unittest discover -s tests -v
docker compose config
```

Then publish the branch and open a pull request:

```bash
git push -u origin feature/descriptive-name
gh pr create --draft --fill
```

GitHub Actions must pass before the change is merged into `main`.

## Existing installations

Do not immediately replace the remote or source tree of an installation that predates the public GitHub release. First determine whether the live directory is a Git worktree and whether it contains private deployment files, bind mounts or local configuration that are intentionally absent from the public repository.

The safe migration pattern is:

1. leave the running installation unchanged;
2. create an adjacent clean checkout from GitHub;
3. compare the clean checkout with the live deployment source;
4. preserve `.env`, database storage, SSH material, backups and deployment-only files;
5. build and test a candidate against copied or isolated state;
6. deploy through the existing backup and rollback process; and
7. change the live source relationship only after the candidate passes.

When retaining an older source remote for reference, use a separate remote name such as `gitea`. Keep `origin` pointed at GitHub in the active development checkout.

## Deploying an approved revision

Create a verified backup before changing source:

```bash
./scripts/backup.sh
```

Fetch and fast-forward the deployment checkout:

```bash
git fetch origin --prune
git switch main
git merge --ff-only origin/main
```

Embed the exact source revision in the locally built image:

```bash
export RADAR_BUILD_COMMIT="$(git rev-parse HEAD)"
docker compose config
docker compose build --pull
docker compose up -d --build
```

Confirm the application and workers are healthy:

```bash
docker compose ps
curl -fsS http://localhost:9120/healthz
```

When a build revision was supplied, the health response includes a `commit` field:

```json
{"commit":"0123456789abcdef0123456789abcdef01234567","name":"Software Release Radar","status":"ok","version":"2.8.0"}
```

The same revision is stored in the container image label:

```bash
docker image inspect \
  --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' \
  "software-release-radar:$(tr -d '[:space:]' < VERSION)"
```

This makes it possible to confirm that the running application matches the intended merged GitHub revision.

## Tagged releases and GHCR

A tag matching `v<VERSION>` runs the container publishing workflow. The workflow builds `linux/amd64` and `linux/arm64` images and records the tagged GitHub commit in both the image environment and the OCI revision label.

Example verification:

```bash
docker pull ghcr.io/muhdusama/software-release-radar:2.8.0
docker image inspect \
  --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' \
  ghcr.io/muhdusama/software-release-radar:2.8.0
```

Release tags are immutable deployment references. Normal development should use branches and pull requests rather than committing directly on a production host.

## Rollback boundary

A Git rollback is not a database rollback. Preserve a verified database backup before every upgrade and follow the restore procedure in [Docker deployment](DOCKER.md) when application state must be restored.

Review `CHANGELOG.md` and release notes before deploying a new version. A future migration that changes database compatibility must include explicit upgrade and rollback instructions.
