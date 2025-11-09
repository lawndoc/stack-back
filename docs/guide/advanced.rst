Advanced
--------

Currently work in progress. These are only notes :D

Temp Notes
~~~~~~~~~~

* Quick setup guide from start to end
* we group snapshots by path when forgetting
* explain rcb commands
* examples of using restic directly
* Explain what happens during backup process
* Explain the backup process container
* cache directory
* Not displaying passwords in logs

Inner workings
~~~~~~~~~~~~~~

* Each service in the compose setup is configured with a label
  to enable backup of volumes or databases
* When backup starts a new instance of the container is created
  mapping in all the needed volumes.
* Volumes are mounted to `/volumes/<service_name>/<path>`
  in the backup process container. `/volumes` is pushed into restic
* Databases are backed up from stdin / dumps into restic using path
  `/databases/<service_name>/dump.sql`
* Cron triggers backup at 2AM every day
