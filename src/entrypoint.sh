#!/bin/sh

# Dump all env vars so we can source them in cron jobs
rcb dump-env > /.env

# Write crontab
rcb crontab > crontab

# Start cron in the background and capture its PID
crontab crontab
crond -f &
CRON_PID=$!

# Trap termination signals and kill the cron process
trap 'kill $CRON_PID; exit 0' TERM INT

# Wait for cron and handle signals
wait $CRON_PID
