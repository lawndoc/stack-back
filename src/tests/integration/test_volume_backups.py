"""Integration tests for volume backups"""
import time
import pytest

pytestmark = pytest.mark.integration


def test_backup_status(run_rcb_command):
    """Test that the status command works"""
    exit_code, output = run_rcb_command("status")
    assert exit_code == 0, f"Status command failed: {output}"
    assert "Detected Config" in output
    assert "service: web" in output
    assert "service: mysql" in output


def test_backup_bind_mount(run_rcb_command, create_test_data, backup_container):
    """Test backing up a bind mount"""
    # Create test data in the bind mount
    test_file = create_test_data("test_data/web/test.txt", "Hello from bind mount!")
    
    # Wait a moment for the file to be visible
    time.sleep(2)
    
    # Run backup
    exit_code, output = run_rcb_command("backup")
    assert exit_code == 0, f"Backup command failed: {output}"
    
    # Check that snapshots were created
    exit_code, output = run_rcb_command("snapshots")
    assert exit_code == 0, f"Snapshots command failed: {output}"
    assert len(output.strip().split('\n')) > 1, "No snapshots found"


def test_restore_bind_mount(run_rcb_command, create_test_data, backup_container, project_root):
    """Test restoring data from a bind mount backup"""
    # Create and backup test data
    test_content = "This is test data for restore"
    test_file = create_test_data("test_data/web/restore_test.txt", test_content)
    
    time.sleep(2)
    
    # Run backup
    exit_code, output = run_rcb_command("backup")
    assert exit_code == 0, f"Backup command failed: {output}"
    
    # Remove the test file
    test_file.unlink()
    
    # Restore from backup
    exit_code, output = backup_container.exec_run(
        "restic restore latest --target /restore --path /volumes"
    )
    assert exit_code == 0, f"Restore command failed: {output.decode()}"
    
    # Verify the restored file exists
    exit_code, output = backup_container.exec_run(
        "cat /restore/volumes/web/srv/data/restore_test.txt"
    )
    assert exit_code == 0, f"Could not read restored file: {output.decode()}"
    assert test_content in output.decode(), "Restored content doesn't match original"


def test_named_volume_backup(run_rcb_command, web_container):
    """Test backing up a named Docker volume"""
    # Create test data in the named volume
    test_content = "Named volume test data"
    exit_code, output = web_container.exec_run(
        f"sh -c 'echo \"{test_content}\" > /usr/share/nginx/html/index.html'"
    )
    assert exit_code == 0, f"Failed to create test data: {output.decode()}"
    
    time.sleep(2)
    
    # Run backup
    exit_code, output = run_rcb_command("backup")
    assert exit_code == 0, f"Backup command failed: {output}"
    
    # Verify snapshot exists
    exit_code, output = run_rcb_command("snapshots")
    assert exit_code == 0, f"Snapshots command failed: {output}"


def test_multiple_backups_creates_snapshots(run_rcb_command, create_test_data):
    """Test that running multiple backups creates multiple snapshots"""
    # First backup
    create_test_data("test_data/web/file1.txt", "First backup")
    time.sleep(2)
    exit_code, _ = run_rcb_command("backup")
    assert exit_code == 0
    
    # Second backup with new data
    time.sleep(2)
    create_test_data("test_data/web/file2.txt", "Second backup")
    time.sleep(2)
    exit_code, _ = run_rcb_command("backup")
    assert exit_code == 0
    
    # Check that we have multiple snapshots
    exit_code, output = run_rcb_command("snapshots")
    assert exit_code == 0
    # Should have at least 2 snapshots (may have more from previous tests)
    snapshot_lines = [line for line in output.split('\n') if line.strip() and not line.startswith('-')]
    # Filter out header lines
    snapshot_count = len([line for line in snapshot_lines if 'latest' not in line.lower() and len(line) > 20])
    assert snapshot_count >= 2, f"Expected at least 2 snapshots, found {snapshot_count}"


def test_excluded_service_not_backed_up(run_rcb_command):
    """Test that services with stack-back.volumes=false are not backed up"""
    exit_code, output = run_rcb_command("status")
    assert exit_code == 0
    # The excluded_service should not appear in the backup list
    assert "service: excluded_service" not in output, "Excluded service should not be in backup list"
