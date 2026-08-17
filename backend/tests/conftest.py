from pathlib import Path

import pytest


@pytest.fixture
def sample_path() -> Path:
    return Path(__file__).parent / "sample_files" / "minimal.ies"

