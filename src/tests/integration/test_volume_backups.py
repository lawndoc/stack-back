"""Integration tests for volume backups"""

import time
import dataclasses
import re
import pytest

pytestmark = pytest.mark.integration


@dataclasses.dataclass
class Snapshot:
    """Represents a restic snapshot"""
    id: str
    time: str
    host: str
    tags: str
    paths: str


def parse_snapshots(output: str) -> list[Snapshot]:
    """Parse restic snapshots output into Snapshot objects"""
    lines = output.split("\n")
    
    # Find the header line to determine column positions
    header_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("ID"):
            header_idx = i
            break
    
    if header_idx == -1:
        return []
    
    header = lines[header_idx]
    # Find column positions based on header
    id_pos = header.index("ID")
    time_pos = header.index("Time") if "Time" in header else -1
    host_pos = header.index("Host") if "Host" in header else -1
    tags_pos = header.index("Tags") if "Tags" in header else -1
    paths_pos = header.index("Paths") if "Paths" in header else -1
    
    snapshots = []
    # Process lines after the separator line
    for line in lines[header_idx + 2:]:
        if not line.strip() or line.startswith("-"):
            continue
        if re.match(r"^\d+ snapshots", line):
            break
            
        # Extract values based on column positions
        id_val = line[id_pos:time_pos].strip() if time_pos > 0 else line[id_pos:].strip()
        time_val = line[time_pos:host_pos].strip() if time_pos > 0 and host_pos > 0 else ""
        host_val = line[host_pos:tags_pos].strip() if host_pos > 0 and tags_pos > 0 else ""
        tags_val = line[tags_pos:paths_pos].strip() if tags_pos > 0 and paths_pos > 0 else ""
        paths_val = line[paths_pos:].strip() if paths_pos > 0 else ""
        
        if id_val:
            snapshots.append(Snapshot(
                id=id_val,
                time=time_val,
                host=host_val,
                tags=tags_val,
                paths=paths_val,
            ))
    
    return snapshots


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
    
    snapshots = parse_snapshots(output)
    assert len(snapshots) == 4, f"Expected 4 snapshots, found\n{output}"
    assert all("test-tag" in s.tags for s in snapshots), f"Not all snapshots have 'test-tag':\n{output}"


def test_restore_bind_mount(
    run_rcb_command, create_test_data, backup_container, project_root
):
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
    snapshot_lines = [
        line for line in output.split("\n") if line.strip() and not line.startswith("-")
    ]
    # Filter out header lines
    snapshot_count = len(
        [
            line
            for line in snapshot_lines
            if "latest" not in line.lower() and len(line) > 20
        ]
    )
    assert snapshot_count >= 2, f"Expected at least 2 snapshots, found {snapshot_count}"


def test_excluded_service_not_backed_up(run_rcb_command):
    """Test that services with stack-back.volumes=false are not backed up"""
    exit_code, output = run_rcb_command("status")
    assert exit_code == 0
    # The excluded_service should not appear in the backup list
    assert "service: excluded_service" not in output, (
        "Excluded service should not be in backup list"
    )
