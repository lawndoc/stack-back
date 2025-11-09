
The `rcb` command
-----------------

The ``rcb`` command is is basically what this entire project is.
It provides useful commands interacting with the compose setup
and restic.

The command can be executed inside the container or through ``run``.

.. code:: bash

    # Get the current status using run
    $ docker-compose run --rm backup rcb status

    # by entering the container
    $ docker-compose exec backup sh
    /stack-back # rcb status

Log level can be overridden by using the ``--log-level``
flag. This can help you better understand what is going on
for example by using ``--log-level debug``.

version
~~~~~~~

Displays the version.

Example output::

    /stack-back # rcb version
    1.0.0

status
~~~~~~

Shows the general status of our setup. The command is doing
the following operations

- Displays the name of the compose setup
- Displays the repository path
- Tells us if a backup is currently running
- Removes stale backup process containers if the exist
- Checks is the repository is initialized
- Initializes the repository if this is not already done
- Displays what volumes and databases are flagged for backup

Example output::

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

alert
~~~~~

Sends a test message to all configured alert backends
and is there for you to verify that alerts are in
fact working and configured correctly.

The format of this message::

    subject: myproject: Test Alert
    body: Test message

snapshots
~~~~~~~~~

Displays the latest snapshots in restic. This can also
be done with ``restic snapshots``.

Example output::

    /stack-back # rcb snapshots
    repository f325264e opened successfully, password is correct
    ID        Time                 Host          Tags        Paths
    ---------------------------------------------------------------------------------------------
    19928e1c  2019-12-09 02:07:44  b3038db04ec1              /volumes
    7a642f37  2019-12-09 02:07:45  b3038db04ec1              /databases/mysql/all_databases.sql
    883dada4  2019-12-09 02:07:46  b3038db04ec1              /databases/mariadb/all_databases.sql
    76ef2457  2019-12-09 02:07:47  b3038db04ec1              /databases/postgres/test.sql
    ---------------------------------------------------------------------------------------------
    4 snapshots

backup
~~~~~~

Starts a backup process by spawning a new docker container.
The mounted volumes, env vars etc. from the
backup service are copied to this container.

We attach to this container and stream the logs and delete
the container with the backup process is completed. If the
container for any reason should not be deleted, it will
be in next backup run as these containers are tagged with
a unique label and detected.

If anything goes wrong the exist status of the container
is non-zero and the logs from this backup run will be sent
to the user through the configure alerts.

This command is by default called by cron every
day at 02:00 unless configured otherwise. We can also run this
manually is needed.

Running this command will do the following:

* Checks if a backup process is already running.
  If so, we alert the user and abort
* Gathers all the volumes configured for backup and starts
  the backup process with these volumes mounted into ``/volumes``
* Checks the status of the process and reports to the user
  if anything failed

The backup process does the following:

* ``status`` is first called to ensure everything is ok
* Backs up ``/volumes`` if any volumes were mounted
* Backs up each configured database
* Runs ``cleanup`` purging snapshots based on the configured policy
* Checks the health of the repository

Example::

        $ docker-compose exec backup sh
        /stack-back # rcb backup
        INFO: Starting backup container
        INFO: Backup process container: loving_jepsen
        INFO: 2019-12-09 04:50:22,817 - INFO: Status for compose project 'stack-back'
        INFO: 2019-12-09 04:50:22,817 - INFO: Repository: '/restic_data'
        INFO: 2019-12-09 04:50:22,817 - INFO: Backup currently running?: True
        INFO: 2019-12-09 04:50:23,701 - INFO: ------------------------- Detected Config -------------------------
        INFO: 2019-12-09 04:50:23,701 - INFO: service: mysql
        INFO: 2019-12-09 04:50:23,718 - INFO:  - mysql (is_ready=True)
        INFO: 2019-12-09 04:50:23,718 - INFO: service: mariadb
        INFO: 2019-12-09 04:50:23,726 - INFO:  - mariadb (is_ready=True)
        INFO: 2019-12-09 04:50:23,727 - INFO: service: postgres
        INFO: 2019-12-09 04:50:23,734 - INFO:  - postgres (is_ready=True)
        INFO: 2019-12-09 04:50:23,735 - INFO: service: web
        INFO: 2019-12-09 04:50:23,736 - INFO:  - volume: /some/volume
        INFO: 2019-12-09 04:50:23,736 - INFO: -------------------------------------------------------------------
        INFO: 2019-12-09 04:50:23,736 - INFO: Backing up volumes
        INFO: 2019-12-09 04:50:24,661 - INFO: Backing up databases
        INFO: 2019-12-09 04:50:24,661 - INFO: Backing up mysql in service mysql
        INFO: 2019-12-09 04:50:25,643 - INFO: Backing up mariadb in service mariadb
        INFO: 2019-12-09 04:50:26,580 - INFO: Backing up postgres in service postgres
        INFO: 2019-12-09 04:50:27,555 - INFO: Forget outdated snapshots
        INFO: 2019-12-09 04:50:28,457 - INFO: Prune stale data freeing storage space
        INFO: 2019-12-09 04:50:31,547 - INFO: Checking the repository for errors
        INFO: 2019-12-09 04:50:32,869 - INFO: Backup completed
        INFO: Backup container exit code: 0

crontab
~~~~~~~

Generates and verifies the crontab. This is done automatically when
the container starts. It can be user to verify the configuration.

Example output::

    /stack-back # rcb crontab
    10 2 * * * source /env.sh && rcb backup > /proc/1/fd/1

cleanup
~~~~~~~

Purges all snapshots based on the configured policy. (``RESTIC_KEEP_*``
env variables). It runs ``restic forget`` and ``restic purge``.

Example output::

    /stack-back # rcb cleanup
    2019-12-09 05:09:52,892 - INFO: Forget outdated snapshots
    2019-12-09 05:09:53,776 - INFO: Prune stale data freeing storage space

start-backup-process
~~~~~~~~~~~~~~~~~~~~

This can only be executed by the backup process container.
Attempting to run this command in the backup service
will simply tell you it's not possible.

The backup process is doing the following:

* ``status`` is first called to ensure everything is ok
* Backs up ``/volumes`` if any volumes were mounted
* Backs up each configured database
* Runs ``cleanup`` purging snapshots based on the configured policy
* Checks the health of the repository
