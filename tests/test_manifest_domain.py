from __future__ import annotations
import json
from pathlib import Path
import pytest

pytestmark = pytest.mark.asyncio

def test_manifest_domain_matches_code():
    manifest = json.loads(
        Path("custom_components/fertility_tracker/manifest.json").read_text()
    )
    from custom_components.fertility_tracker.const import DOMAIN
    assert manifest["domain"] == DOMAIN == "fertility_tracker"
