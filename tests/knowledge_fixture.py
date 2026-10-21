"""A controlled draft baseline for unit tests, independent of production approvals."""

import shutil


def copy_draft_knowledge(source, destination):
    def ignore(path, names):
        if path.replace("\\", "/").rstrip("/").endswith("/reviews"):
            return [name for name in names if name.endswith(".yaml")]
        return []

    shutil.copytree(source, destination, ignore=ignore)
