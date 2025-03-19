#!/bin/sh

# Dump all env vars so we can source them in cron jobs
rcb dump-env > /.env

# Write crontab
rcb crontab > crontab

# start cron in the foreground
crontab crontab
crond -f
