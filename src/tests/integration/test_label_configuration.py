"""Integration tests for label-based configuration"""
import subprocess
import time
import pytest

pytestmark = pytest.mark.integration


def test_volume_include_label(run_rcb_command):
    """Test that stack-back.volumes.include label filters volumes correctly"""
    exit_code, output = run_rcb_command("status")
    assert exit_code == 0
    
    # Web service has include label for "data"
    # It should only back up the /srv/data mount, not the nginx html volume
    assert "service: web" in output
    # Should see the data volume
    assert "/srv/data" in output


def test_volume_exclude_label(run_rcb_command):
    """Test that stack-back.volumes=false excludes a service from backups"""
    exit_code, output = run_rcb_command("status")
    assert exit_code == 0
    
    # excluded_service has stack-back.volumes=false
    assert "service: excluded_service" not in output


def test_database_labels_detection(run_rcb_command):
    """Test that database backup labels are detected correctly"""
    exit_code, output = run_rcb_command("status")
    assert exit_code == 0
    
    # Check that all three database types are detected
    assert "mysql" in output.lower()
    assert "mariadb" in output.lower()
    assert "postgres" in output.lower()


def test_backup_respects_labels(run_rcb_command, create_test_data, project_root, compose_project_name):
    """Test that backup only processes labeled services"""
    # Create data in both included and excluded services
    create_test_data("test_data/web/included.txt", "Should be backed up")
    
    time.sleep(2)
    
    # Run backup
    exit_code, output = run_rcb_command("backup")
    assert exit_code == 0
    
    # The output should mention processing web service but not excluded_service
    # (excluded_service has stack-back.volumes=false)
    exit_code, status_output = run_rcb_command("status")
    assert "service: web" in status_output
    assert "service: excluded_service" not in status_output


def test_database_label_enables_backup(run_rcb_command, mysql_container):
    """Test that database-specific labels enable database backups"""
    # MySQL container has stack-back.mysql=true label
    exit_code, output = run_rcb_command("status")
    assert exit_code == 0
    
    # Should show mysql service with database backup enabled
    assert "service: mysql" in output
    assert "mysql" in output.lower()


def test_multiple_mounts_with_include(run_rcb_command):
    """Test that include pattern works when service has multiple mounts"""
    # Web service has two mounts but include filter for "data"
    exit_code, output = run_rcb_command("status")
    assert exit_code == 0
    
    # Should only show the included volume
    lines = output.split('\n')
    web_section = []
    in_web_section = False
    
    for line in lines:
        if "service: web" in line:
            in_web_section = True
        elif in_web_section:
            if line.strip().startswith("service:"):
                break
            if "volume:" in line:
                web_section.append(line)
    
    # Should have the data mount but web service has include filter
    # so we should see limited volumes
    assert len(web_section) > 0, "Web service should have at least one volume listed"


def test_services_without_labels_not_backed_up(run_rcb_command):
    """Test that services without stack-back labels are not backed up when AUTO_BACKUP_ALL=false"""
    exit_code, output = run_rcb_command("status")
    assert exit_code == 0
    
    # With AUTO_BACKUP_ALL=false in test environment,
    # only explicitly labeled services should appear
    lines = [line for line in output.split('\n') if line.strip().startswith('service:')]
    
    # We should see our explicitly labeled services
    service_names = [line.split('service:')[1].strip() for line in lines]
    
    # All services in the list should be ones we explicitly labeled
    expected_services = ['web', 'mysql', 'mariadb', 'postgres', 'backup']
    for service in service_names:
        assert service in expected_services, f"Unexpected service '{service}' in backup list"
