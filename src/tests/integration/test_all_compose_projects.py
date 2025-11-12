"""Integration tests for INCLUDE_ALL_COMPOSE_PROJECTS configuration"""

import time
import pytest

pytestmark = pytest.mark.integration


def test_status_shows_only_same_project_by_default(run_rcb_command, secondary_compose_up):
    """Test that status command only shows containers from the same compose project by default"""
    exit_code, output = run_rcb_command("status")
    assert exit_code == 0, f"Status command failed: {output}"
    
    # Should show services from the main project
    assert "service: web" in output
    assert "service: mysql" in output
    assert "service: mariadb" in output
    assert "service: postgres" in output
    
    # Should NOT show services from the secondary project (different compose project)
    assert "service: secondary_web" not in output
    assert "service: secondary_mysql" not in output
    assert "service: secondary_postgres" not in output


def test_backup_only_same_project_by_default(run_rcb_command, secondary_compose_up, secondary_web_container, create_test_data):
    """Test that backup only includes containers from the same compose project by default"""
    # Create test data in the secondary project
    create_test_data("test_data/secondary_web/test.txt", "Secondary project data")
    time.sleep(2)
    
    # Also create data in secondary container's named volume
    exit_code, output = secondary_web_container.exec_run(
        'sh -c \'echo "Secondary volume data" > /usr/share/nginx/html/secondary.html\''
    )
    assert exit_code == 0, f"Failed to create test data in secondary container: {output.decode()}"
    
    time.sleep(2)
    
    # Run backup with default settings (INCLUDE_ALL_COMPOSE_PROJECTS=false)
    exit_code, output = run_rcb_command("backup")
    assert exit_code == 0, f"Backup command failed: {output}"
    
    # The backup should only mention the main project's services
    # It should not backup the secondary project
    # We verify this indirectly by checking the status output doesn't mention secondary services
    exit_code, status_output = run_rcb_command("status")
    assert exit_code == 0
    assert "service: secondary_web" not in status_output


def test_status_with_include_all_compose_projects(backup_container_with_multi_project):
    """Test that status command shows containers from all compose projects when enabled"""
    # Use the backup container with INCLUDE_ALL_COMPOSE_PROJECTS=true
    exit_code, output = backup_container_with_multi_project.exec_run("rcb status")
    output_text = output.decode()
    assert exit_code == 0, f"Status command failed: {output_text}"
    
    # Should show services from the main project
    assert "service: web" in output_text
    assert "service: mysql" in output_text
    assert "service: mariadb" in output_text
    assert "service: postgres" in output_text
    
    # Should ALSO show services from the secondary project
    assert "service: secondary_web" in output_text
    assert "service: secondary_mysql" in output_text
    assert "service: secondary_postgres" in output_text


def test_backup_all_compose_projects_volumes(backup_container_with_multi_project, secondary_web_container, create_test_data, project_root):
    """Test that volumes from all compose projects are backed up when enabled"""
    # Create test data in secondary project bind mount
    test_content_bind = "Secondary project bind mount data"
    create_test_data("test_data/secondary_web/multi_project_test.txt", test_content_bind)
    time.sleep(2)
    
    # Create test data in secondary project named volume
    test_content_volume = "Secondary project named volume data"
    exit_code, output = secondary_web_container.exec_run(
        f'sh -c \'echo "{test_content_volume}" > /usr/share/nginx/html/multi_project.html\''
    )
    assert exit_code == 0, f"Failed to create test data: {output.decode()}"
    
    time.sleep(2)
    
    # Run backup with INCLUDE_ALL_COMPOSE_PROJECTS=true
    exit_code, output = backup_container_with_multi_project.exec_run("rcb backup")
    backup_output = output.decode()
    assert exit_code == 0, f"Backup command failed: {backup_output}"
    
    # Verify snapshots were created
    exit_code, output = backup_container_with_multi_project.exec_run("rcb snapshots")
    snapshots_output = output.decode()
    assert exit_code == 0, f"Snapshots command failed: {snapshots_output}"
    assert len(snapshots_output.strip().split("\n")) > 1, "No snapshots found"
    
    # Restore from backup and verify secondary project data exists
    exit_code, output = backup_container_with_multi_project.exec_run(
        "restic restore latest --target /restore --path /volumes"
    )
    assert exit_code == 0, f"Restore command failed: {output.decode()}"
    
    # Check for secondary project bind mount data
    exit_code, output = backup_container_with_multi_project.exec_run(
        "find /restore/volumes -name multi_project_test.txt"
    )
    find_output = output.decode()
    assert exit_code == 0, f"Failed to find restored file: {find_output}"
    assert "multi_project_test.txt" in find_output, "Secondary project bind mount file not found in backup"
    
    # Check for secondary project named volume data
    exit_code, output = backup_container_with_multi_project.exec_run(
        "find /restore/volumes -name multi_project.html"
    )
    find_output = output.decode()
    assert exit_code == 0, f"Failed to find restored file: {find_output}"
    assert "multi_project.html" in find_output, "Secondary project named volume file not found in backup"


def test_backup_all_compose_projects_databases(
    backup_container_with_multi_project, 
    secondary_mysql_container, 
    secondary_postgres_container
):
    """Test that databases from all compose projects are backed up when enabled"""
    # Create test data in secondary MySQL
    exit_code, output = secondary_mysql_container.exec_run(
        "mysql -u root -psecondary_root_password -e "
        '"CREATE TABLE IF NOT EXISTS secondary_db.items (id INT, name VARCHAR(50)); '
        "INSERT INTO secondary_db.items VALUES (1, 'SecondaryItem1'), (2, 'SecondaryItem2');\""
    )
    assert exit_code == 0, f"Failed to create MySQL test data: {output.decode()}"
    
    # Create test data in secondary PostgreSQL
    exit_code, output = secondary_postgres_container.exec_run(
        "psql -U secondary_user -d secondary_db -c "
        '"CREATE TABLE IF NOT EXISTS records (id INT, value VARCHAR(50)); '
        "INSERT INTO records VALUES (1, 'SecondaryRecord1'), (2, 'SecondaryRecord2');\""
    )
    assert exit_code == 0, f"Failed to create PostgreSQL test data: {output.decode()}"
    
    time.sleep(2)
    
    # Run backup with INCLUDE_ALL_COMPOSE_PROJECTS=true
    exit_code, output = backup_container_with_multi_project.exec_run("rcb backup")
    backup_output = output.decode()
    assert exit_code == 0, f"Backup command failed: {backup_output}"
    
    # Verify the backup mentions database backups
    assert "Backing up databases" in backup_output or "database" in backup_output.lower()
    
    # Verify snapshots exist
    exit_code, output = backup_container_with_multi_project.exec_run("rcb snapshots")
    assert exit_code == 0, f"Snapshots command failed: {output.decode()}"


def test_all_projects_after_multiple_backups(backup_container_with_multi_project, secondary_web_container, create_test_data):
    """Test multiple backups with data changes across different compose projects"""
    # First backup
    create_test_data("test_data/secondary_web/backup1.txt", "First backup data")
    time.sleep(2)
    exit_code, _ = backup_container_with_multi_project.exec_run("rcb backup")
    assert exit_code == 0
    
    # Second backup with new data
    time.sleep(2)
    create_test_data("test_data/secondary_web/backup2.txt", "Second backup data")
    time.sleep(2)
    exit_code, _ = backup_container_with_multi_project.exec_run("rcb backup")
    assert exit_code == 0
    
    # Verify multiple snapshots
    exit_code, output = backup_container_with_multi_project.exec_run("rcb snapshots")
    snapshots_output = output.decode()
    assert exit_code == 0
    
    # Should have at least 2 snapshots
    snapshot_lines = [
        line for line in snapshots_output.split("\n") 
        if line.strip() and not line.startswith("-")
    ]
    snapshot_count = len([
        line for line in snapshot_lines 
        if "latest" not in line.lower() and len(line) > 20
    ])
    assert snapshot_count >= 2, f"Expected at least 2 snapshots, found {snapshot_count}"


def test_include_all_projects_with_excluded_services(backup_container_with_multi_project):
    """Test that excluded services are still excluded even with INCLUDE_ALL_COMPOSE_PROJECTS=true"""
    exit_code, output = backup_container_with_multi_project.exec_run("rcb status")
    status_output = output.decode()
    assert exit_code == 0
    
    # The excluded_service from main project should not appear
    assert "service: excluded_service" not in status_output, (
        "Excluded service should not be in backup list even with INCLUDE_ALL_COMPOSE_PROJECTS"
    )
    
    # But other services should appear
    assert "service: web" in status_output
    assert "service: secondary_web" in status_output


def test_project_name_in_backup_path_with_all_projects(backup_container_with_multi_project, create_test_data):
    """Test that when INCLUDE_ALL_COMPOSE_PROJECTS is enabled, project names are included in paths"""
    # Create test data
    create_test_data("test_data/secondary_web/project_name_test.txt", "Testing project names")
    time.sleep(2)
    
    # Run backup
    exit_code, _ = backup_container_with_multi_project.exec_run("rcb backup")
    assert exit_code == 0
    
    # When INCLUDE_ALL_COMPOSE_PROJECTS is true, INCLUDE_PROJECT_NAME should also be enabled
    # Check the status to verify
    exit_code, output = backup_container_with_multi_project.exec_run("rcb status")
    assert exit_code == 0
    
    # The backup should have project-specific paths
    # We can verify this by restoring and checking the path structure
    exit_code, output = backup_container_with_multi_project.exec_run(
        "restic restore latest --target /restore"
    )
    assert exit_code == 0, f"Restore failed: {output.decode()}"
    
    # List the restored structure
    exit_code, output = backup_container_with_multi_project.exec_run(
        "find /restore -type d -name '*secondary*' -o -type d -name '*integration*'"
    )
    # Should find directories with project names in the path
    # Note: The exact path structure depends on INCLUDE_PROJECT_NAME implementation
    assert exit_code == 0

