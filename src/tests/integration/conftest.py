"""Pytest fixtures for integration tests"""
import os
import subprocess
import time
import pytest
import docker
from pathlib import Path


@pytest.fixture(scope="session")
def docker_client():
    """Provide a Docker client for tests"""
    return docker.from_env()


@pytest.fixture(scope="session")
def project_root():
    """Return the project root directory"""
    return Path(__file__).parent.parent.parent.parent


@pytest.fixture(scope="session")
def compose_project_name():
    """Return a unique name for the test compose project"""
    return "stack_back_integration_test"


@pytest.fixture(scope="session")
def docker_compose_file(project_root):
    """Return the path to the test docker-compose file"""
    return project_root / "docker-compose.test.yaml"


@pytest.fixture(scope="session")
def compose_up(docker_compose_file, compose_project_name, project_root):
    """Start docker-compose services before tests and tear down after"""
    # Clean up any existing test data
    test_data_dir = project_root / "test_data"
    test_restic_data = project_root / "test_restic_data"
    test_restic_cache = project_root / "test_restic_cache"
    
    for directory in [test_data_dir, test_restic_data, test_restic_cache]:
        if directory.exists():
            subprocess.run(
                ["rm", "-rf", str(directory)],
                check=False,
                cwd=str(project_root),
            )
        directory.mkdir(parents=True, exist_ok=True)
    
    # Create test data directory structure
    web_data_dir = test_data_dir / "web"
    web_data_dir.mkdir(parents=True, exist_ok=True)
    
    # Start docker compose
    subprocess.run(
        [
            "docker", "compose",
            "-f", str(docker_compose_file),
            "-p", compose_project_name,
            "up", "-d", "--build"
        ],
        check=True,
        cwd=str(project_root),
    )
    
    # Wait for services to be healthy
    max_wait = 60
    start_time = time.time()
    while time.time() - start_time < max_wait:
        result = subprocess.run(
            [
                "docker", "compose",
                "-f", str(docker_compose_file),
                "-p", compose_project_name,
                "ps", "--format", "json"
            ],
            capture_output=True,
            text=True,
            cwd=str(project_root),
        )
        
        if result.returncode == 0:
            # Check if all services are healthy or running
            time.sleep(5)
            break
        time.sleep(2)
    
    yield
    
    # Tear down
    subprocess.run(
        [
            "docker", "compose",
            "-f", str(docker_compose_file),
            "-p", compose_project_name,
            "down", "-v"
        ],
        check=False,
        cwd=str(project_root),
    )
    
    # Clean up test data
    for directory in [test_data_dir, test_restic_data, test_restic_cache]:
        if directory.exists():
            subprocess.run(
                ["rm", "-rf", str(directory)],
                check=False,
                cwd=str(project_root),
            )


@pytest.fixture
def backup_container(docker_client, compose_project_name, compose_up):
    """Return the backup container"""
    containers = docker_client.containers.list(
        filters={"label": f"com.docker.compose.project={compose_project_name}"}
    )
    for container in containers:
        service_name = container.labels.get("com.docker.compose.service")
        if service_name == "backup":
            return container
    raise RuntimeError("Backup container not found")


@pytest.fixture
def run_backup(backup_container):
    """Fixture to execute backup command in the backup container"""
    def _run_backup():
        exit_code, output = backup_container.exec_run("rcb backup")
        return exit_code, output.decode()
    return _run_backup


@pytest.fixture
def run_rcb_command(backup_container):
    """Fixture to execute arbitrary rcb commands in the backup container"""
    def _run_command(command: str):
        full_command = f"rcb {command}"
        exit_code, output = backup_container.exec_run(full_command)
        return exit_code, output.decode()
    return _run_command


@pytest.fixture
def create_test_data(project_root):
    """Helper to create test data files"""
    def _create_data(relative_path: str, content: str):
        file_path = project_root / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return file_path
    return _create_data


@pytest.fixture
def mysql_container(docker_client, compose_project_name, compose_up):
    """Return the MySQL container"""
    containers = docker_client.containers.list(
        filters={"label": f"com.docker.compose.project={compose_project_name}"}
    )
    for container in containers:
        service_name = container.labels.get("com.docker.compose.service")
        if service_name == "mysql":
            return container
    raise RuntimeError("MySQL container not found")


@pytest.fixture
def mariadb_container(docker_client, compose_project_name, compose_up):
    """Return the MariaDB container"""
    containers = docker_client.containers.list(
        filters={"label": f"com.docker.compose.project={compose_project_name}"}
    )
    for container in containers:
        service_name = container.labels.get("com.docker.compose.service")
        if service_name == "mariadb":
            return container
    raise RuntimeError("MariaDB container not found")


@pytest.fixture
def postgres_container(docker_client, compose_project_name, compose_up):
    """Return the PostgreSQL container"""
    containers = docker_client.containers.list(
        filters={"label": f"com.docker.compose.project={compose_project_name}"}
    )
    for container in containers:
        service_name = container.labels.get("com.docker.compose.service")
        if service_name == "postgres":
            return container
    raise RuntimeError("PostgreSQL container not found")


@pytest.fixture
def web_container(docker_client, compose_project_name, compose_up):
    """Return the web container"""
    containers = docker_client.containers.list(
        filters={"label": f"com.docker.compose.project={compose_project_name}"}
    )
    for container in containers:
        service_name = container.labels.get("com.docker.compose.service")
        if service_name == "web":
            return container
    raise RuntimeError("Web container not found")
