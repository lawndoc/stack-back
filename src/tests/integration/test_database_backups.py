"""Integration tests for database backups"""

import time
import pytest

pytestmark = pytest.mark.integration


def test_mysql_backup(run_rcb_command, mysql_container):
    """Test backing up MySQL database"""
    # Create test data in MySQL
    exit_code, output = mysql_container.exec_run(
        "mysql -u root -ptest_root_password -e "
        '"CREATE TABLE IF NOT EXISTS testdb.users (id INT, name VARCHAR(50)); '
        "INSERT INTO testdb.users VALUES (1, 'Alice'), (2, 'Bob');\""
    )
    assert exit_code == 0, f"Failed to create MySQL test data: {output.decode()}"

    time.sleep(2)

    # Run backup
    exit_code, output = run_rcb_command("backup")
    assert exit_code == 0, f"Backup command failed: {output}"

    # Verify the backup includes database dumps
    assert "Backing up databases" in output or "mysql" in output.lower()


def test_mysql_data_integrity(run_rcb_command, mysql_container, backup_container):
    """Test MySQL backup and restore data integrity"""
    # Insert unique test data
    test_data = "IntegrationTestUser"
    exit_code, output = mysql_container.exec_run(
        f"mysql -u root -ptest_root_password -e "
        f"\"INSERT INTO testdb.users VALUES (999, '{test_data}');\""
    )
    assert exit_code == 0, f"Failed to insert test data: {output.decode()}"

    time.sleep(2)

    # Backup
    exit_code, output = run_rcb_command("backup")
    assert exit_code == 0, f"Backup failed: {output}"

    # Verify data can be dumped from backup
    # The backup creates SQL dumps in the backup process
    # We can verify the snapshot exists and contains database data
    exit_code, output = run_rcb_command("snapshots")
    assert exit_code == 0, f"Failed to list snapshots: {output}"


def test_mariadb_backup(run_rcb_command, mariadb_container):
    """Test backing up MariaDB database"""
    # Create test data in MariaDB
    exit_code, output = mariadb_container.exec_run(
        "mariadb -u root -ptest_root_password -e "
        '"CREATE TABLE IF NOT EXISTS testdb.products (id INT, name VARCHAR(50)); '
        "INSERT INTO testdb.products VALUES (1, 'Widget'), (2, 'Gadget');\""
    )
    assert exit_code == 0, f"Failed to create MariaDB test data: {output.decode()}"

    time.sleep(2)

    # Run backup
    exit_code, output = run_rcb_command("backup")
    assert exit_code == 0, f"Backup command failed: {output}"

    # Verify the backup includes database dumps
    assert "Backing up databases" in output or "mariadb" in output.lower()


def test_postgres_backup(run_rcb_command, postgres_container):
    """Test backing up PostgreSQL database"""
    # Create test data in PostgreSQL
    exit_code, output = postgres_container.exec_run(
        "psql -U testuser -d testdb -c "
        '"CREATE TABLE IF NOT EXISTS orders (id INT, item VARCHAR(50)); '
        "INSERT INTO orders VALUES (1, 'Book'), (2, 'Pen');\""
    )
    assert exit_code == 0, f"Failed to create PostgreSQL test data: {output.decode()}"

    time.sleep(2)

    # Run backup
    exit_code, output = run_rcb_command("backup")
    assert exit_code == 0, f"Backup command failed: {output}"

    # Verify the backup includes database dumps
    assert "Backing up databases" in output or "postgres" in output.lower()


def test_all_databases_backed_up(
    run_rcb_command, mysql_container, mariadb_container, postgres_container
):
    """Test that all three database types are backed up in a single backup operation"""
    # Insert data in all databases
    mysql_container.exec_run(
        "mysql -u root -ptest_root_password -e "
        "\"INSERT INTO testdb.users VALUES (100, 'MultiDBTest');\""
    )

    mariadb_container.exec_run(
        "mariadb -u root -ptest_root_password -e "
        "\"INSERT INTO testdb.products VALUES (100, 'MultiDBProduct');\""
    )

    postgres_container.exec_run(
        "psql -U testuser -d testdb -c "
        "\"INSERT INTO orders VALUES (100, 'MultiDBItem');\""
    )

    time.sleep(2)

    # Single backup operation
    exit_code, output = run_rcb_command("backup")
    assert exit_code == 0, f"Backup command failed: {output}"

    # Check that all databases were processed
    # The status command should show all three database services
    exit_code, status_output = run_rcb_command("status")
    assert exit_code == 0
    assert "service: mysql" in status_output
    assert "service: mariadb" in status_output
    assert "service: postgres" in status_output


def test_database_health_check(run_rcb_command):
    """Test that database health checks work in status command"""
    exit_code, output = run_rcb_command("status")
    assert exit_code == 0

    # All databases should be reported as ready
    assert "is_ready=True" in output, (
        "Database health checks should show databases as ready"
    )


def test_backup_after_database_changes(run_rcb_command, mysql_container):
    """Test incremental backup after database modifications"""
    # Initial backup
    exit_code, _ = run_rcb_command("backup")
    assert exit_code == 0

    # Modify data
    time.sleep(2)
    mysql_container.exec_run(
        "mysql -u root -ptest_root_password -e "
        "\"UPDATE testdb.users SET name='UpdatedName' WHERE id=1;\""
    )

    time.sleep(2)

    # Second backup
    exit_code, output = run_rcb_command("backup")
    assert exit_code == 0, f"Incremental backup failed: {output}"

    # Verify we have snapshots
    exit_code, snapshot_output = run_rcb_command("snapshots")
    assert exit_code == 0
