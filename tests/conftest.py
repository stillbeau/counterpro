from pathlib import Path

import pytest

from counterpro.inventory import load_slabs

FIXTURE = Path(__file__).parent / "fixtures" / "sample_inventory.csv"


@pytest.fixture(scope="session")
def slabs():
    result = load_slabs([str(FIXTURE)])
    assert result.errors == []
    return result.slabs
