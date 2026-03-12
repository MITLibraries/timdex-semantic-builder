import os

# Set required environment variables for testing here
# Failure to do so will result in errors during initialization
# You can override these with test-specific values in individual test files as needed
# with monkeypatch.setenv("VARIABLE", "custom_value")
os.environ["WORKSPACE"] = "test"
