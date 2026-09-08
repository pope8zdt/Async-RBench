"""Verify the build context cannot accidentally include repository/private data."""
from __future__ import annotations

import os
import stat
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from build import BUILD_FILES, _is_linked, write_context


class ContextTests(unittest.TestCase):
    def test_windows_junction_detection_does_not_require_new_pathlib(self) -> None:
        metadata = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        with patch.object(Path, "lstat", return_value=metadata):
            self.assertTrue(_is_linked(Path("junction")))

    def fixture(self, root: Path) -> None:
        (root / "async_rbench").mkdir()
        (root / "async_rbench" / "__init__.py").write_text("# package\n")
        (root / "docker" / "track-b").mkdir(parents=True)
        (root / "pyproject.toml").write_text("[project]\n")
        (root / "event_taxonomy.json").write_text('{"public_protocol": true}\n')
        for name in BUILD_FILES:
            (root / "docker" / "track-b" / name).write_text("# build input\n")

    def test_only_allowlisted_source_is_sent_and_archive_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            for name in ("cases/private.py", "artifacts/secret.py", ".git/config", ".codex/auth.json",
                         "async_rbench/auth.json", "async_rbench/__pycache__/private.py"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("private sentinel")
            first, second = root / "first.tar", root / "second.tar"
            a, b = write_context(root, first), write_context(root, second)
            self.assertEqual(a["sha256"], b["sha256"])
            with tarfile.open(first) as archive:
                names = archive.getnames()
                self.assertEqual(len(names), 3 + len(BUILD_FILES))
                self.assertIn("async_rbench/__init__.py", names)
                for member in archive:
                    self.assertNotIn(b"private sentinel", archive.extractfile(member).read())

    def test_symlinked_package_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            secret = root / "private.py"
            secret.write_text("private sentinel")
            try:
                os.symlink(secret, root / "async_rbench" / "linked.py")
            except OSError:
                self.skipTest("symlink creation is unavailable")
            with self.assertRaisesRegex(ValueError, "linked paths"):
                write_context(root, root / "context.tar")


if __name__ == "__main__":
    unittest.main()
