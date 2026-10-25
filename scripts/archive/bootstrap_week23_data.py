"""One-time provenance capture. Runtime downloads use the resulting pinned manifest."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[2]


def main():
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        commit = client.get("https://api.github.com/repos/aloistr/swisseph/commits/master")
        commit.raise_for_status()
        revision = commit.json()["sha"]
        assets = [
            (
                f"https://raw.githubusercontent.com/aloistr/swisseph/{revision}/ephe/{name}",
                f"ephe/{name}",
                "Swiss Ephemeris / Astrodienst",
                "AGPL-3.0 / commercial",
                revision,
            )
            for name in ("sepl_18.se1", "semo_18.se1")
        ]
        assets += [
            (
                "https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/de440s.bsp",
                "ephe/de440s.bsp",
                "NASA/JPL DE440 (1849–2150)",
                "US government public data",
                "DE440s",
            ),
            (
                "https://download.geonames.org/export/dump/cities15000.zip",
                "geo/cities15000.zip",
                "GeoNames cities15000 incl. alternate names and IANA timezone",
                "CC BY 4.0",
                "snapshot-" + datetime.now(UTC).strftime("%Y-%m-%d"),
            ),
        ]
        rows = []
        for url, path, source, license_name, version in assets:
            dest = ROOT / "data" / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            response = client.get(url)
            response.raise_for_status()
            dest.write_bytes(response.content)
            checksum = hashlib.sha256(response.content).hexdigest()
            rows.append(
                dict(
                    url=url,
                    path=path,
                    source=source,
                    license=license_name,
                    version=version,
                    sha256=checksum,
                    retrieved_at=datetime.now(UTC).isoformat(),
                )
            )
            print(path, len(response.content), checksum)
        (ROOT / "scripts/data_manifest.yaml").write_text(
            yaml.safe_dump(
                dict(schema_version=1, assets=rows), allow_unicode=True, sort_keys=False
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
