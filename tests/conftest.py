import os
from pathlib import Path

import pytest

# Skip dependency installation during tests for faster execution.
# The linting tests (ruff, djlint, django-upgrade) don't need
# dependencies installed - they just check the generated code syntax.
# Use test_docker.sh for full integration testing with dependencies.
os.environ["COPIER_TEST_MODE"] = "1"


@pytest.fixture
def template_path():
    """Return the path to the template root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def context():
    """Default context for template generation."""
    return {
        "project_name": "My Test Project",
        "project_slug": "my_test_project",
        "author_name": "Test Author",
        "email": "test@example.com",
        "description": "A short description of the project.",
        "domain_name": "example.com",
        "version": "0.1.0",
        "timezone": "UTC",
    }
