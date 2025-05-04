
# stack-back

[![docs](https://readthedocs.org/projects/stack-back/badge/?version=latest)](https://stack-back.readthedocs.io)

Automated incremental backups using [restic] for any docker-compose setup.

* Backup docker volumes or host binds
* Backup postgres, mariadb, and mysql databases
* Notifications over SMTP or Discord webhooks

# Usage

### Just add it to your services

```yaml
services:
  backup:
    image: ghcr.io/lawndoc/stack-back:<version>
    env_file:
      - stack-back.env
    volumes:
      - /var/run/docker.sock:/tmp/docker.sock:ro
      - cache:/cache # Persistent restic cache (greatly speeds up all restic operations)
```

### And add a label to the containers you want backed up

```yaml
  web:
    image: some_image
    labels:
      stack-back.volumes: true # Enables backup of the volumes below
    volumes:
      - media:/srv/media
      - /srv/files:/srv/files
  mysql:
    image: mysql:9
    labels:
      stack-back.mysql: true # Enables stateful backup using mysqldump
    volumes:
      - mysql:/var/lib/mysql
```

[Documentation](https://stack-back.readthedocs.io)

Please report issus on [github](https://github.com/lawndoc/stack-back/issues).

## Configuration (environment variables)

Minimum configuration

```bash
RESTIC_REPOSITORY
RESTIC_PASSWORD
```

All config options can be found in the [template env file](./stack-back.env.template)

Restic-specific environment variables can be found in the [restic documentation](https://restic.readthedocs.io/en/stable/040_backup.html#environment-variables)

### Example config: S3 bucket

stack-back.env

```bash
RESTIC_REPOSITORY=s3:s3.us-east-1.amazonaws.com/bucket_name
RESTIC_PASSWORD=thisdecryptsyourbackupsdontloseit
AWS_ACCESS_KEY_ID=<your access key id>
AWS_SECRET_ACCESS_KEY=<your access key id>
CHECK_WITH_CACHE=true
# snapshot prune rules
RESTIC_KEEP_DAILY=7
RESTIC_KEEP_WEEKLY=4
RESTIC_KEEP_MONTHLY=12
RESTIC_KEEP_YEARLY=3
# Cron schedule. Run every day at 1am
CRON_SCHEDULE="0 1 * * *"
```

## The `rcb` command

Everything is controlled using the [`rcb` command line tool](./src/) from this repo.

You can use the `rcb status` command to verify the configuration.

```bash
$ docker-compose exec -it backup rcb status
INFO: Status for compose project 'myproject'
INFO: Repository: '<restic repository>'
INFO: Backup currently running?: False
INFO: --------------- Detected Config ---------------
INFO: service: mysql
INFO:  - mysql (is_ready=True)
INFO: service: mariadb
INFO:  - mariadb (is_ready=True)
INFO: service: postgres
INFO:  - postgres (is_ready=True)
INFO: service: web
INFO:  - volume: media
INFO:  - volume: /srv/files
```

The `status` subcommand lists what will be backed up and even pings the database services checking their availability.

More `rcb` commands can be found in the [documentation].

# Contributing

Contributions are welcome regardless of experience level.

## Python environment

Use [`uv`](https://docs.astral.sh/uv/) within the `src/` directory to manage your development environment.

```bash
git clone https://github.com/lawndoc/stack-back.git
cd stack-back
uv sync --directory src/
```

## Running unit tests

Make sure `uv` is already set up as shown above.

```bash
uv run --directory src/ pytest
```

## Docker Compose testing

The git repository contains a simple local setup for development

```bash
# Create an overlay network to link the compose project and stack
docker network create --driver overlay --attachable global
# Start the compose project
docker-compose up -d
# Deploy the stack
docker stack deploy -c swarm-stack.yml test
```

Remember to enable swarm mode with `docker swarm init/join` and disable swarm
mode with `docker swarm leave --force` when needed in development (single node setup).

## Building Docs

```bash
pip install -r docs/requirements.txt
python src/setup.py build_sphinx
```

[restic]: https://restic.net/
[documentation]: https://stack-back.readthedocs.io

---
This project is an actively maintained fork of [restic-compose-backup](https://github.com/ZettaIO/restic-compose-backup) by [Zetta.IO](https://www.zetta.io).

Huge thanks to them for creating this project.

[![Zetta.IO](https://raw.githubusercontent.com/lawndoc/stack-back/main/.github/logo.png)](https://www.zetta.io)
