# Test Organization

This directory contains all tests for stack-back, organized into two categories:

## Running Tests

### Unit Tests Only (Fast - ~0.1s)
```bash
uv run pytest -m unit
```

### Integration Tests Only (Slow - ~3 minutes)
```bash
uv run pytest -m integration
```

### All Tests
```bash
uv run pytest
```

## Test Markers

Tests are marked using pytest markers:
- `@pytest.mark.unit` - Fast unit tests with mocks
- `@pytest.mark.integration` - Slower integration tests requiring Docker

These markers are configured in `pyproject.toml`.
