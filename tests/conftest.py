import shutil
import uuid

import pytest
import yaml

from app import ROOT, create_runtime
from knowledge.build import build


def pytest_configure(config):
    # Existing system pytest temp directories may be owned by another account on Windows.
    # Use a new, project-local directory; never delete or change system temp permissions.
    if config.option.basetemp is None:
        parent = ROOT / "reports/test_tmp"
        parent.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = parent / uuid.uuid4().hex


@pytest.fixture
def project(tmp_path):
    shutil.copyfile(ROOT / "config.yaml", tmp_path / "config.yaml")
    config_path = tmp_path / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["llm"].update(provider="demo", model=None)
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    shutil.copytree(ROOT / "knowledge/sources", tmp_path / "sources")
    shutil.copytree(ROOT / "knowledge/rules", tmp_path / "rules")
    build(tmp_path / "sources", tmp_path / "data/kb.sqlite", tmp_path / "rules")
    return tmp_path


@pytest.fixture
def runtime(project):
    value = create_runtime(root=project, user_id="synthetic-test", seed=42)
    yield value
    value.close()


class ScriptedModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.seen_messages = []

    async def chat(self, messages, tools):
        self.seen_messages.append([dict(m) for m in messages])
        return next(self.responses)


@pytest.fixture
def scripted_model():
    return ScriptedModel
