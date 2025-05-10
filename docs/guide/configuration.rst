Configuration
=============

Environment Variables
---------------------

RESTIC_REPOSITORY
~~~~~~~~~~~~~~~~~

Sets the restic repository path.

This is a standard environment variable
the ``restic`` command will read making it simple for
us to enter the container and use the restic command directly.

More about this value and supported backends:
https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html

RESTIC_PASSWORD
~~~~~~~~~~~~~~~

Sets the password is used to encrypt/decrypt data.
Losing this password will make recovery impossible.

This is a standard environment variable the ``restic``
command will read making it simple for us to enter the
container running the command directly.

RESTIC_KEEP_DAILY
~~~~~~~~~~~~~~~~~

**Default value**: ``7``

How many daily snapshots (grouped by path) back in time we
want to keep. This is passed to restic in the
``forget --keep-daily`` option.

RESTIC_KEEP_WEEKLY
~~~~~~~~~~~~~~~~~~

**Default value**: ``4``

How many weeks back we should keep at least one snapshot
(grouped by path). This is passed to restic in the
``forget --keep-weekly`` option.

RESTIC_KEEP_MONTHLY
~~~~~~~~~~~~~~~~~~~

**Default value**: ``12``

How many months back we should keep at least on snapshot
(grouped by path). This is passed to restic in the
``forget --keep-monthly`` option.

The schedule parameters only accepts numeric values
and is validated when the container starts. Providing
values cron does not understand will stall all backup.

RESTIC_KEEP_YEARLY
~~~~~~~~~~~~~~~~~~

**Default value**: ``3``

How many years back we should keep at least one snapshot
(grouped by path). This is passed to restic in the
``forget --keep-yearly`` option.

CRON_SCHEDULE
~~~~~~~~~~~~~

**Default value**: ``0 2 * * *`` (daily at 02:00)

The cron schedule parameters. The crontab is generated when the
container starts from the ``CRON_SCHEDULE`` and ``CRON_COMMAND``
env variables.

.. code::

    ┌───────────── minute (0 - 59)
    │ ┌───────────── hour (0 - 23)
    │ │ ┌───────────── day of the month (1 - 31)
    │ │ │ ┌───────────── month (1 - 12)
    │ │ │ │ ┌───────────── day of the week (0 - 6) (Sunday to Saturday)
    │ │ │ │ │
    │ │ │ │ │
    │ │ │ │ │
    * * * * * command to execute

CRON_COMMAND
~~~~~~~~~~~~

**Default value**: ``source /env.sh && rcb backup > /proc/1/fd/1``

The command executed in the crontab. A single line is generated when
the container starts from the ``CRON_SCHEDULE`` and ``CRON_COMMAND``
environment variables.

The default command sources a dump of all env vars, runs the
backup command and directs output to pid 1 so it appears in
docker logs.

By default the crontab will look like this::

    0 2 * * * source /env.sh && rcb backup > /proc/1/fd/1

MAINTENANCE_SCHEDULE
~~~~~~~~~~~~~~~~~~~~~

**Default value**: null`

By default, maintenance (restic forget + prune + check) happens after
every successful backup. This can be changed by setting this
environment variable to a cron schedule. The format is the same as
the ``CRON_SCHEDULE`` variable.

This is useful if maintenance tasks are using a lot of read operations
and you want to limit them to reduce cloud costs. The tradeoff is that
the repository will be larger for a longer time as forget and prune
will not be run after every backup.

CHECK_WITH_CACHE
~~~~~~~~~~~~~~~~~~

**Default value**: ``false``

Whether restic should use the local cache when checking for integrity
of the repository. This is useful for reducing remote read operations,
which may be charged by your cloud provider.

The tradeoff is that there is a small risk of not detecting corrupted 
data in the repository if the remote is corrupted but the local cache is not.

LOG_LEVEL
~~~~~~~~~

**Default value**: ``info``

Log level for the ``rcb`` command. Valid values are
``debug``, ``info``, ``warning``, ``error``.

EMAIL_HOST
~~~~~~~~~~

The email host to use.

Alerts can be tested using the ``rcb alerts`` command.
This will send a test message to all configured alert
backends.

EMAIL_PORT
~~~~~~~~~~

The port to connect to

Alerts can be tested using the ``rcb alerts`` command.
This will send a test message to all configured alert
backends.

EMAIL_HOST_USER
~~~~~~~~~~~~~~~

The user of the sender account

Alerts can be tested using the ``rcb alerts`` command.
This will send a test message to all configured alert
backends.

EMAIL_HOST_PASSWORD
~~~~~~~~~~~~~~~~~~~

The password for the sender account

Alerts can be tested using the ``rcb alerts`` command.
This will send a test message to all configured alert
backends.

EMAIL_SEND_TO
~~~~~~~~~~~~~

The email address to send alerts

Alerts can be tested using the ``rcb alerts`` command.
This will send a test message to all configured alert
backends.

DISCORD_WEBHOOK
~~~~~~~~~~~~~~~

The discord webhook url. And administrator can quickly set this up
by going to server settings in the discord client and create
a webhook that will post embedded messages to a specific channel.

The url usually looks like this: ``https://discordapp.com/api/webhooks/...```

DOCKER_HOST
~~~~~~~~~~~

**Default value**: ``unix://tmp/docker.sock``

The socket or host of the docker service.

DOCKER_TLS_VERIFY
~~~~~~~~~~~~~~~~~

If defined verify the host against a CA certificate.
Path to certs is defined in ``DOCKER_CERT_PATH``
and can be copied or mapped into this backup container.

DOCKER_CERT_PATH
~~~~~~~~~~~~~~~~

A path to a directory containing TLS certificates to use when
connecting to the Docker host. Combined with ``DOCKER_TLS_VERIFY``
this can be used to talk to docker through TLS in cases
were we cannot map in the docker socket.

INCLUDE_ALL_VOLUMES
~~~~~~~~~~~~~~~~~~~

If defined, all volumes will be included in the backup.
This is useful when you want to back up all volumes
in a project without having to add labels to each service.

Volumes can be excluded by adding the ``stack-back.volumes.exclude``
label to the service.

INCLUDE_PROJECT_NAME
~~~~~~~~~~~~~~~~~~~~

Define this environment variable if your backup destination
paths needs project name as a prefix. This is useful
when running multiple projects.

EXCLUDE_BIND_MOUNTS
~~~~~~~~~~~~~~~~~~~

Docker has to volumes types. Binds and volumes.
Volumes are docker volumes (``docker`volume list``).
Binds are paths mapped into the container from
the host for example in the ``volumes`` section
of a service.

If defined all host binds will be ignored globally.
This is useful when you only care about actual
docker volumes. Often host binds are only used
for mapping in configuration. This saves the user
from manually excluding these bind volumes.

SWARM_MODE
~~~~~~~~~~

If defined containers in swarm stacks are also evaluated.

Compose Labels
--------------

What is backed up is controlled by simple labels in the compose
yaml file. At any point we can verify this configuration
by running the ``rcb status`` command.

.. code:

    $ docker-compose run --rm backup rcb status
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

Here we can see what volumes and databases are detected for backup.

Volumes
~~~~~~~

To enable volume backup for a service we simply add the
`stack-back.volumes: true` label. The value
must be ``true``.

Example:

.. code:: yaml

    myservice:
      image: some_image
      labels:
        stack-back.volumes: true
      volumes:
        - uploaded_media:/srv/media
        - uploaded_files:/srv/files
        - /srv/data:/srv/data

    volumes:
      media:
      files:

This will back up the three volumes mounted to this service.
Their path in restic will be:

- /volumes/myservice/srv/media
- /volumes/myservice/srv/files
- /volumes/myservice/srv/data

In situations where the files in the volume are at risk of being
corrupted during the backup process (such as SQLite databases), 
the `stack-back.volumes.stop-during-backup` label can be added to 
the service. This will stop the service during the backup process 
and start it again when the backup is done.

Example:

.. code:: yaml
  
    myservice:
      image: some_image
      labels:
        stack-back.volumes: true
        stack-back.volumes.stop-during-backup: true
      volumes:
        - uploaded_media:/srv/media
        - uploaded_files:/srv/files
        - /srv/data:/srv/data

    volumes:
      media:
      files:

A simple `include` and `exclude` filter for what volumes
should be backed up is also available. Note that this
includes or excludes entire volumes and are not include/exclude
patterns for files in the volumes.

.. note:: The ``exclude`` and ``include`` filtering is applied on
          the source path, not the destination.

Include example including two volumes only:

.. code:: yaml

    myservice:
      image: some_image
      labels:
        stack-back.volumes: true
        stack-back.volumes.include: "uploaded_media,uploaded_files"
      volumes:
        - uploaded_media:/srv/media
        - uploaded_files:/srv/files
        - /srv/data:/srv/data

    volumes:
      media:
      files:

Exclude example achieving the same result as the example above.

.. code:: yaml

    example:
      image: some_image
      labels:
        stack-back.volumes: true
        stack-back.volumes.exclude: "data"
      volumes:
        # Excluded by filter
        - media:/srv/media
        # Backed up
        - files:/srv/files
        - /srv/data:/srv/data

    volumes:
      media:
      files:

The ``exclude`` and ``include`` tag can be used together
in more complex situations.

mariadb
~~~~~~~

To enable backup of mariadb simply add the
``stack-back.mariadb: true`` label.

Credentials are fetched from the following environment
variables in the mariadb service. This is the standard
when using the official mariadb_ image.

.. code::

    MARIADB_USER
    MARIADB_PASSWORD

Backups are done by dumping all databases directly into
restic through stdin using ``mysqldump``. It will appear
in restic as a separate snapshot with path
``/databases/<service_name>/all_databases.sql``.

.. warning: This will only back up the databases the
            ``MARIADB_USER` has access to. If you have multiple
            databases this must be taken into consideration.

Example:

.. code:: yaml

    mariadb:
      image: mariadb:10
      labels:
        stack-back.mariadb: true
      env_file:
        mariadb-credentials.env
      volumes:
        - mariadb:/var/lib/mysql

    volumes:
      mariadb:

mysql
~~~~~

To enable backup of mysql simply add the
``stack-back.mysql: true`` label.

Credentials are fetched from the following environment
variables in the mysql service. This is the standard
when using the official mysql_ image.

.. code::

    MYSQL_USER
    MYSQL_PASSWORD

Backups are done by dumping all databases directly into
restic through stdin using ``mysqldump``. It will appear
in restic as a separate snapshot with path
``/databases/<service_name>/all_databases.sql``.

.. warning: This will only back up the databases the
            ``MYSQL_USER` has access to. If you have multiple
            databases this must be taken into consideration.

Example:

.. code:: yaml

    mysql:
      image: mysql:5
      labels:
        stack-back.mysql: true
      env_file:
        mysql-credentials.env
      volumes:
        - mysql:/var/lib/mysql

volumes:
  mysql:

postgres
~~~~~~~~

To enable backup of mysql simply add the
``stack-back.postgres: true`` label.

Credentials are fetched from the following environment
variables in the postgres service. This is the standard
when using the official postgres_ image.

.. code::

    POSTGRES_USER
    POSTGRES_PASSWORD
    POSTGRES_DB

Backups are done by dumping the ``POSTGRES_DB`` directly into
restic through stdin using ``pg_dump``. It will appear
in restic as a separate snapshot with path
``/databases/<service_name>/<POSTGRES_DB>.sql``.

.. warning:: Currently only the ``POSTGRES_DB`` database
             is dumped.

Example:

.. code:: yaml

    postgres:
      image: postgres:11
      labels:
        # Enables backup of this database
        stack-back.postgres: true
      env_file:
        postgres-credentials.env
      volumes:
        - pgdata:/var/lib/postgresql/data

    volumes:
      pgdata:

.. _mariadb: https://hub.docker.com/_/mariadb
.. _mysql: https://hub.docker.com/_/mysql
.. _postgres: https://hub.docker.com/_/postgres
