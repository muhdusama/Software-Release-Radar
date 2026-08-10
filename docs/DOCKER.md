# 🐳 Docker deployment

Docker Compose is the intended primary deployment method for Software Release Radar.

> [!WARNING]
> The repository is still in publication staging. `docker-compose.yml` and `.env.example` are now present, but the sanitised application source and `Dockerfile` have not yet been imported into this GitHub repository. The commands below describe the target public workflow and must pass a clean-host validation before the repository is made public.

## What Docker is doing here

Software Release Radar is a Python 3.13 application. Docker is simply the packaging and deployment layer.

```text
Python application
      │
      ▼
Docker image
      │
      ▼
Docker Compose
      │
      ▼
Browser access + persistent data
```

The aim is that a self-hoster does not need to install or manage Python directly on the host.

## Target quick start

Once the public source and Dockerfile are staged and validated, the normal install path will be:

```bash
git clone https://github.com/muhdusama/Software-Release-Radar.git
cd Software-Release-Radar
cp .env.example .env
docker compose config
docker compose up -d --build
```

Then open the service on the port configured by `SRR_HOST_PORT` in `.env`.

The current default is:

```text
http://localhost:9120
```

## Files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Defines the Release Radar container, port mapping and persistent data mount |
| `.env.example` | Safe template containing non-secret Docker defaults |
| `.env` | Your local configuration. This file is deliberately ignored by Git |
| `Dockerfile` | Builds the Python application image. This will be added with the sanitised source |
| `data/` | Local persistent application data. This directory is ignored by Git |

## Environment file

Create your local environment file with:

```bash
cp .env.example .env
```

Do not commit `.env`. It may later contain API keys, passwords, private URLs or other deployment-specific settings.

The staging template currently exposes only the Docker-level settings that are safe to publish:

```dotenv
SRR_VERSION=dev
SRR_HOST_PORT=9120
SRR_CONTAINER_PORT=9120
SRR_DATA_DIR=./data
```

Application-specific variables will be added after the public configuration surface has been checked against the sanitised v2.6.3 source.

## Useful commands

Validate the Compose file:

```bash
docker compose config
```

Build and start:

```bash
docker compose up -d --build
```

See container state:

```bash
docker compose ps
```

Follow logs:

```bash
docker compose logs -f software-release-radar
```

Stop the stack:

```bash
docker compose down
```

Rebuild after an update:

```bash
docker compose pull
docker compose up -d --build
```

The final release process may change the update command if a published container image is introduced.

## Publication validation

Before Docker deployment is described as production-ready, the following must pass on a clean Linux host:

- [ ] `cp .env.example .env`
- [ ] `docker compose config`
- [ ] fresh image build from the public source tree
- [ ] first start with an empty `data/` directory
- [ ] browser access on the documented port
- [ ] restart with persistent state retained
- [ ] application health and release checks
- [ ] upgrade from one public release to the next
- [ ] backup and restore of persistent state
- [ ] no dependency on private hostnames, paths, credentials or infrastructure

Until those checks pass, the Compose files are a public deployment scaffold rather than a final release artefact.
