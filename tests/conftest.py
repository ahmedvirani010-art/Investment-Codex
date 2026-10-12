import json
from pathlib import Path

import pytest

from investment_workspace.pipeline import fixture_bytes
from investment_workspace.storage import git


@pytest.fixture
def bundle():
    return json.loads(fixture_bytes())


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    git(root, "init", "-q")
    (root / ".gitignore").write_text(".runtime/\ninputs/private/\n")
    git(root, "add", ".gitignore")
    git(root, "-c", "user.name=Test", "-c", "user.email=test@localhost", "commit", "-qm", "test baseline")
    return root
