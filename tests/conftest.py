"""Pytest configuration and shared fixtures."""

# TODO: Add your shared test fixtures here
# Uncomment the import when you create your first fixture:
# import pytest
#
# Fixtures are reusable setup code for tests. Use them to:
# - Create test data that multiple tests need
# - Set up and tear down resources (files, databases, connections)
# - Mock external dependencies
#
# Example fixtures:
#
# @pytest.fixture
# def sample_data():
#     """Provide sample data for tests."""
#     return {"key": "value"}
#
# @pytest.fixture
# def temp_file(tmp_path):
#     """Create a temporary file for testing."""
#     file = tmp_path / "test.txt"
#     file.write_text("test content")
#     return file
#
# For async tests (requires pytest-asyncio in test dependencies):
# @pytest.fixture
# async def async_client():
#     """Provide async test client."""
#     client = await create_client()
#     yield client
#     await client.close()
