import hashlib

import httpx
import pytest

from app import ROOT
from scripts.doctor import diagnose
from scripts.fetch_data import fetch_asset


def test_doctor_week1_required_checks(project):
    report = diagnose(project, data_root=ROOT / "data")
    assert report["ok"]
    assert all(c["required"] is False for c in report["checks"] if c["name"].endswith("API_KEY"))


def test_download_hash_and_cache(tmp_path):
    content = b"synthetic-data"
    asset = {
        "url": "https://example.test/data",
        "path": "ephe/test.bin",
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=content))
    ) as client:
        assert fetch_asset(asset, tmp_path, client)["status"] == "downloaded"
        assert fetch_asset(asset, tmp_path, client)["status"] == "cached"


@pytest.mark.parametrize(
    "path,checksum",
    [("../escape.bin", "a" * 64), ("file.bin", "not-a-hash"), ("file.bin", "a" * 64)],
)
def test_bad_download_is_rejected(tmp_path, path, checksum):
    asset = {"url": "https://example.test/data", "path": path, "sha256": checksum}
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"wrong"))
    ) as client:
        with pytest.raises(ValueError):
            fetch_asset(asset, tmp_path, client)
    assert not (tmp_path / "file.bin").exists()
    assert not list(tmp_path.rglob("*.download"))
