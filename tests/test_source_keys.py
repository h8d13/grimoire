"""_import_source_keys gates on origin and keys/pgp contents.

Official gitlab.archlinux.org clones ship source-signing keys as
keys/pgp/<fingerprint>.asc; those import into the builder's gpg keyring
before makepkg. Everything else (AUR, custom repos, no keys dir) is a no-op.
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from grimoireshim import grimoire

OFFICIAL = "https://gitlab.archlinux.org/archlinux/packaging/packages/foo.git"
AUR = "https://github.com/archlinux/aur.git"


class ImportSourceKeysTests(unittest.TestCase):
	def setUp(self) -> None:
		tmp = tempfile.TemporaryDirectory()
		self.addCleanup(tmp.cleanup)
		self.pkg_dir = Path(tmp.name)

	def _patch(self, *, origin: str | None) -> mock.Mock:
		mock.patch.object(grimoire, "_clone_origin", return_value=origin).start()
		run = mock.patch.object(grimoire, "run_command").start()
		self.addCleanup(mock.patch.stopall)
		return run

	def _key(self, name: str) -> Path:
		d = self.pkg_dir / "keys" / "pgp"
		d.mkdir(parents=True, exist_ok=True)
		key = d / name
		key.write_text("-----BEGIN PGP PUBLIC KEY BLOCK-----\n")
		return key

	def test_official_clone_imports_keys(self) -> None:
		key = self._key("ABCDEF.asc")
		run = self._patch(origin=OFFICIAL)
		grimoire._import_source_keys(self.pkg_dir)
		run.assert_called_once_with(["gpg", "--import", str(key)], check=False)

	def test_ssh_rewritten_origin_still_matches(self) -> None:
		key = self._key("ABCDEF.asc")
		run = self._patch(
			origin="git@gitlab.archlinux.org:archlinux/packaging/packages/foo.git"
		)
		grimoire._import_source_keys(self.pkg_dir)
		run.assert_called_once_with(["gpg", "--import", str(key)], check=False)

	def test_aur_clone_skipped(self) -> None:
		self._key("ABCDEF.asc")
		run = self._patch(origin=AUR)
		grimoire._import_source_keys(self.pkg_dir)
		run.assert_not_called()

	def test_no_keys_dir_says_so(self) -> None:
		# Official clone without keys/pgp: no gpg call, but tell the user why.
		run = self._patch(origin=OFFICIAL)
		out = io.StringIO()
		with contextlib.redirect_stdout(out):
			grimoire._import_source_keys(self.pkg_dir)
		run.assert_not_called()
		self.assertIn("no source keys", out.getvalue())

	def test_non_asc_files_ignored(self) -> None:
		self._key("README")  # not *.asc
		run = self._patch(origin=OFFICIAL)
		grimoire._import_source_keys(self.pkg_dir)
		run.assert_not_called()

	def test_no_origin_skipped(self) -> None:
		self._key("ABCDEF.asc")
		run = self._patch(origin=None)
		grimoire._import_source_keys(self.pkg_dir)
		run.assert_not_called()


if __name__ == "__main__":
	unittest.main()
