"""Integration tests for ensure_clone --repo-url ref checkout: a branch, tag, or
commit resolves identically on a fresh clone and on --refresh, building from a
nested subdir. Exercises a real local git repo via file:// (no network)."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from grimaurshim import grimaur


def _git(repo: Path, *args: str) -> str:
	out = subprocess.run(
		[
			"git",
			"-C",
			str(repo),
			"-c",
			"user.email=t@t",
			"-c",
			"user.name=t",
			"-c",
			"commit.gpgsign=false",
			*args,
		],
		capture_output=True,
		text=True,
		check=True,
	)
	return out.stdout.strip()


def _write_pkgbuild(repo: Path, pkgver: int) -> None:
	(repo / "pkg").mkdir(exist_ok=True)
	(repo / "pkg" / "PKGBUILD").write_text(
		f"pkgname=foo\npkgver={pkgver}\npkgrel=1\narch=(any)\n"
	)


class EnsureCloneRefTests(unittest.TestCase):
	def setUp(self) -> None:
		tmp = tempfile.TemporaryDirectory()
		self.addCleanup(tmp.cleanup)
		self.root = Path(tmp.name)
		self.src = self.root / "src"
		self.src.mkdir()
		# master: v1 (tagged v1.0) -> v2 ; dev branched off v2 -> v3
		_git(self.src, "init", "-q", "-b", "master")
		_write_pkgbuild(self.src, 1)
		_git(self.src, "add", "-A")
		_git(self.src, "commit", "-qm", "v1")
		_git(self.src, "tag", "v1.0")
		self.sha_v1 = _git(self.src, "rev-parse", "HEAD")
		_write_pkgbuild(self.src, 2)
		_git(self.src, "add", "-A")
		_git(self.src, "commit", "-qm", "v2")
		_git(self.src, "checkout", "-q", "-b", "dev")
		_write_pkgbuild(self.src, 3)
		_git(self.src, "add", "-A")
		_git(self.src, "commit", "-qm", "v3")
		_git(self.src, "checkout", "-q", "master")

		# default globals already False at import; pin them so a developer's
		# environment can't flip shallow clones on and break commit checkout.
		for name in ("SHALLOW_CLONE", "USE_SSH", "USE_AUR_RPC"):
			patcher = mock.patch.object(grimaur, name, False)
			patcher.start()
			self.addCleanup(patcher.stop)

	def _ensure(self, branch: str | None, dest: Path, *, refresh: bool = False) -> Path:
		build_dir: Path = grimaur.ensure_clone(
			"foo",
			dest,
			refresh=refresh,
			repo_url=f"file://{self.src}",
			branch=branch,
			subdir="pkg",
		)
		return build_dir

	def _fresh(self, branch: str | None) -> Path:
		# A clone is keyed by package name, so each fresh checkout needs its own
		# dest-root; switching ref in an existing clone would need --refresh.
		dest = Path(tempfile.mkdtemp(dir=self.root))
		return self._ensure(branch, dest)

	def _pkgver(self, build_dir: Path) -> str:
		return (build_dir / "PKGBUILD").read_text().split("pkgver=")[1].split("\n")[0]

	def test_subdir_is_the_returned_build_dir(self) -> None:
		dest = Path(tempfile.mkdtemp(dir=self.root))
		self.assertEqual(self._ensure("master", dest), dest / "foo" / "pkg")

	def test_branch_checks_out_branch_tip(self) -> None:
		self.assertEqual(self._pkgver(self._fresh("master")), "2")
		self.assertEqual(self._pkgver(self._fresh("dev")), "3")

	def test_tag_checks_out_tagged_commit(self) -> None:
		self.assertEqual(self._pkgver(self._fresh("v1.0")), "1")

	def test_commit_sha_checks_out_that_commit(self) -> None:
		build_dir = self._fresh(self.sha_v1)
		self.assertEqual(self._pkgver(build_dir), "1")
		head = _git(build_dir.parent, "rev-parse", "HEAD")
		self.assertEqual(head, self.sha_v1)

	def test_no_branch_uses_default_head(self) -> None:
		self.assertEqual(self._pkgver(self._fresh(None)), "2")

	def test_refresh_keeps_each_ref_pinned(self) -> None:
		# Second call exercises the fetch + reset-to-FETCH_HEAD refresh path.
		for ref, expected in (("master", "2"), ("dev", "3"), ("v1.0", "1")):
			with self.subTest(ref=ref):
				dest = Path(tempfile.mkdtemp(dir=self.root))
				self._ensure(ref, dest)
				build_dir = self._ensure(ref, dest, refresh=True)
				self.assertEqual(self._pkgver(build_dir), expected)

	def test_missing_subdir_raises(self) -> None:
		with self.assertRaises(grimaur.AurGitError):
			grimaur.ensure_clone(
				"foo",
				Path(tempfile.mkdtemp(dir=self.root)),
				refresh=False,
				repo_url=f"file://{self.src}",
				branch="master",
				subdir="does-not-exist",
			)


if __name__ == "__main__":
	unittest.main()
