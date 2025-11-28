"""Pytest fixtures for integration tests"""

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

    def cleanup_directories():
        """Helper to clean up test directories"""
        for directory in [test_data_dir, test_restic_data, test_restic_cache]:
            if directory.exists():
                # Use docker to remove (files owned by docker user)
                subprocess.run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "-v",
                        f"{directory}:/data",
                        "alpine:latest",
                        "rm",
                        "-rf",
                        "/data",
                    ],
                    check=False,
                )
                # Remove empty directory if still exists
                subprocess.run(
                    ["rm", "-rf", str(directory)],
                    check=False,
                    cwd=str(project_root),
                    capture_output=True,
                )

    def cleanup_containers():
        """Helper to clean up docker containers"""
        subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(docker_compose_file),
                "-p",
                compose_project_name,
                "down",
                "-v",
            ],
            check=False,
            cwd=str(project_root),
        )

    # Always clean up before starting (handles previous failed runs)
    cleanup_containers()
    cleanup_directories()

    # Create fresh directories
    for directory in [test_data_dir, test_restic_data, test_restic_cache]:
        directory.mkdir(parents=True, exist_ok=True)

    # Create test data directory structure
    web_data_dir = test_data_dir / "web"
    web_data_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Start docker compose
        subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(docker_compose_file),
                "-p",
                compose_project_name,
                "up",
                "-d",
                "--build",
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
                    "docker",
                    "compose",
                    "-f",
                    str(docker_compose_file),
                    "-p",
                    compose_project_name,
                    "ps",
                    "--format",
                    "json",
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

    finally:
        # Always tear down, even if tests fail or are interrupted
        cleanup_containers()
        cleanup_directories()


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


@pytest.fixture(autouse=True)
def cleanup_restic_snapshots(backup_container):
    """Automatically clean up restic snapshots before each test to ensure isolation"""
    # Clean up snapshots before the test runs
    # This ensures each test starts with a clean slate
    exit_code, output = backup_container.exec_run(
        "sh -c 'restic snapshots --json 2>/dev/null || true'"
    )

    # If there are any snapshots, remove them all
    if exit_code == 0 and output.decode().strip():
        # Use restic forget with --prune to remove all snapshots
        backup_container.exec_run(
            "sh -c 'restic snapshots --quiet | tail -n +2 | head -n -2 | awk \"{print \\$1}\" | xargs -r -I {} restic forget {} --prune 2>/dev/null || true'"
        )

    yield

    # Comment out if you want to inspect snapshots after failed tests


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


@pytest.fixture(scope="session")
def secondary_compose_project_name():
    """Return a unique name for the secondary test compose project"""
    return "stack_back_secondary_test"


@pytest.fixture(scope="session")
def secondary_docker_compose_file(project_root):
    """Return the path to the secondary test docker-compose file"""
    return project_root / "docker-compose.test2.yaml"


@pytest.fixture(scope="session")
def secondary_compose_up(
    secondary_docker_compose_file, secondary_compose_project_name, project_root
):
    """Start secondary docker-compose services before tests and tear down after"""
    # Clean up any existing test data
    test_data_dir = project_root / "test_data" / "secondary_web"

    def cleanup_directories():
        """Helper to clean up test directories"""
        if test_data_dir.exists():
            # Use docker to remove (files owned by docker user)
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{test_data_dir}:/data",
                    "alpine:latest",
                    "rm",
                    "-rf",
                    "/data",
                ],
                check=False,
            )
            # Remove empty directory if still exists
            subprocess.run(
                ["rm", "-rf", str(test_data_dir)],
                check=False,
                cwd=str(project_root),
                capture_output=True,
            )

    def cleanup_containers():
        """Helper to clean up docker containers"""
        subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(secondary_docker_compose_file),
                "-p",
                secondary_compose_project_name,
                "down",
                "-v",
            ],
            check=False,
            cwd=str(project_root),
        )

    # Always clean up before starting (handles previous failed runs)
    cleanup_containers()
    cleanup_directories()

    # Create fresh directories
    test_data_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Start docker compose
        subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(secondary_docker_compose_file),
                "-p",
                secondary_compose_project_name,
                "up",
                "-d",
                "--build",
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
                    "docker",
                    "compose",
                    "-f",
                    str(secondary_docker_compose_file),
                    "-p",
                    secondary_compose_project_name,
                    "ps",
                    "--format",
                    "json",
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

    finally:
        # Always tear down, even if tests fail or are interrupted
        cleanup_containers()
        cleanup_directories()


@pytest.fixture
def secondary_web_container(
    docker_client, secondary_compose_project_name, secondary_compose_up
):
    """Return the secondary web container"""
    containers = docker_client.containers.list(
        filters={
            "label": f"com.docker.compose.project={secondary_compose_project_name}"
        }
    )
    for container in containers:
        service_name = container.labels.get("com.docker.compose.service")
        if service_name == "secondary_web":
            return container
    raise RuntimeError("Secondary web container not found")


@pytest.fixture
def secondary_mysql_container(
    docker_client, secondary_compose_project_name, secondary_compose_up
):
    """Return the secondary MySQL container"""
    containers = docker_client.containers.list(
        filters={
            "label": f"com.docker.compose.project={secondary_compose_project_name}"
        }
    )
    for container in containers:
        service_name = container.labels.get("com.docker.compose.service")
        if service_name == "secondary_mysql":
            return container
    raise RuntimeError("Secondary MySQL container not found")


@pytest.fixture
def secondary_postgres_container(
    docker_client, secondary_compose_project_name, secondary_compose_up
):
    """Return the secondary PostgreSQL container"""
    containers = docker_client.containers.list(
        filters={
            "label": f"com.docker.compose.project={secondary_compose_project_name}"
        }
    )
    for container in containers:
        service_name = container.labels.get("com.docker.compose.service")
        if service_name == "secondary_postgres":
            return container
    raise RuntimeError("Secondary PostgreSQL container not found")


@pytest.fixture
def backup_container_with_multi_project(
    docker_client, compose_project_name, compose_up, secondary_compose_up, project_root
):
    """Return the backup container with INCLUDE_ALL_COMPOSE_PROJECTS enabled"""
    # Get the backup container
    containers = docker_client.containers.list(
        filters={"label": f"com.docker.compose.project={compose_project_name}"}
    )
    backup_cont = None
    for container in containers:
        service_name = container.labels.get("com.docker.compose.service")
        if service_name == "backup":
            backup_cont = container
            break

    if backup_cont is None:
        raise RuntimeError("Backup container not found")

    # Set the environment variable for this test
    # We need to restart the container with the new environment variable
    # Since we can't easily modify a running container, we'll use exec to set it
    # and restart the backup process

    # Stop the container
    backup_cont.stop()

    # Get the container config
    container_info = docker_client.api.inspect_container(backup_cont.id)
    config = container_info["Config"]
    host_config = container_info["HostConfig"]

    # Add the environment variable
    env_list = config.get("Env", [])
    # Remove any existing INCLUDE_ALL_COMPOSE_PROJECTS
    env_list = [
        e for e in env_list if not e.startswith("INCLUDE_ALL_COMPOSE_PROJECTS=")
    ]
    env_list.append("INCLUDE_ALL_COMPOSE_PROJECTS=true")

    # Remove the old container
    backup_cont.remove()

    # Parse volumes from Binds format to volumes dict format
    # Binds format: ["/host/path:/container/path:ro"]
    # Volumes format: {"/host/path": {"bind": "/container/path", "mode": "ro"}}
    volumes_dict = {}
    for bind in host_config.get("Binds", []):
        parts = bind.split(":")
        if len(parts) >= 2:
            host_path = parts[0]
            container_path = parts[1]
            mode = parts[2] if len(parts) > 2 else "rw"
            volumes_dict[host_path] = {"bind": container_path, "mode": mode}

    # Get network names
    networks = list(container_info["NetworkSettings"]["Networks"].keys())

    # Create a new container with the updated environment
    # which is needed for the backup container to identify itself
    new_container = docker_client.containers.create(
        config["Image"],
        environment=env_list,
        volumes=volumes_dict,
        name=container_info["Name"].strip("/"),
        labels=config.get("Labels", {}),
    )

    # Connect to networks after creation (more compatible with Podman)
    for network_name in networks:
        try:
            network = docker_client.networks.get(network_name)
            network.connect(new_container)
        except Exception:
            # If network connection fails, continue (may already be connected)
            pass

    # Start the new container
    new_container.start()

    # Wait a bit for it to initialize
    time.sleep(5)

    yield new_container

    # Clean up - stop AND remove the container so compose creates a fresh one
    new_container.stop()
    new_container.remove()

    # Restart the original backup container setup
    # This will now create a fresh container without INCLUDE_ALL_COMPOSE_PROJECTS
    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(project_root / "docker-compose.test.yaml"),
            "-p",
            compose_project_name,
            "up",
            "-d",
            "backup",
        ],
        check=False,
        cwd=str(project_root),
    )
