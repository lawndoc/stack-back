"""
# ┌───────────── minute (0 - 59)
# │ ┌───────────── hour (0 - 23)
# │ │ ┌───────────── day of the month (1 - 31)
# │ │ │ ┌───────────── month (1 - 12)
# │ │ │ │ ┌───────────── day of the week (0 - 6) (Sunday to Saturday;
# │ │ │ │ │                                   7 is also Sunday on some systems)
# │ │ │ │ │
# │ │ │ │ │
# * * * * * command to execute
"""
QUOTE_CHARS = ['"', "'"]


def generate_crontab(config):
    """Generate a crontab entry for running backup job"""
    backup_command = config.cron_command.strip()
    backup_schedule = config.cron_schedule

    if backup_schedule:
        backup_schedule = backup_schedule.strip()
        backup_schedule = strip_quotes(backup_schedule)
        if not validate_schedule(backup_schedule):
            backup_schedule = config.default_crontab_schedule
    else:
        backup_schedule = config.default_crontab_schedule

    crontab = f'{backup_schedule} {backup_command}\n'
    
    maintenance_command = config.maintenance_command.strip()
    maintenance_schedule = config.maintenance_schedule
    
    if maintenance_schedule:
        maintenance_schedule = maintenance_schedule.strip()
        maintenance_schedule = strip_quotes(maintenance_schedule)
        if validate_schedule(maintenance_schedule):
            crontab += f'{maintenance_schedule} {maintenance_command}\n'

    return crontab


def validate_schedule(schedule: str):
    """Validate crontab format"""
    parts = schedule.split()
    if len(parts) != 5:
        return False

    for p in parts:
        if p != '*' and not p.isdigit():
            return False

    minute, hour, day, month, weekday = parts
    try:
        validate_field(minute, 0, 59)
        validate_field(hour, 0, 23)
        validate_field(day, 1, 31)
        validate_field(month, 1, 12)
        validate_field(weekday, 0, 6)
    except ValueError:
        return False

    return True


def validate_field(value, min, max):
    if value == '*':
        return

    i = int(value)
    return min <= i <= max


def strip_quotes(value: str):
    """Strip enclosing single or double quotes if present"""
    if value[0] in QUOTE_CHARS:
        value = value[1:]
    if value[-1] in QUOTE_CHARS:
        value = value[:-1]

    return value
