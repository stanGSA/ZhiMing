"""Every package the application imports is in the wheel (PR #35 review 7)."""

import tomllib

from app import ROOT


def test_every_application_package_is_in_the_wheel():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    packaged = set(config["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"])
    packages = {
        path.parent.name
        for path in ROOT.glob("*/__init__.py")
        if path.parent.name not in ("tests",)
    }
    assert packages <= packaged, sorted(packages - packaged)
