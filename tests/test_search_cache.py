import contextlib
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from grimoireshim import grimoire


class CacheHelperTests(unittest.TestCase):
	def setUp(self) -> None:
		tmp = tempfile.TemporaryDirectory()
		self.addCleanup(tmp.cleanup)
		patcher = mock.patch.object(grimoire, "CACHE_DIR", Path(tmp.name))
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_roundtrip(self) -> None:
		grimoire.cache_put("search/abc.json", '{"ok": 1}')
		self.assertEqual(grimoire.cache_get("search/abc.json", ttl=60), '{"ok": 1}')

	def test_miss_when_absent(self) -> None:
		self.assertIsNone(grimoire.cache_get("nope.json", ttl=60))

	def test_disabled_when_cache_dir_unset(self) -> None:
		with mock.patch.object(grimoire, "CACHE_DIR", None):
			grimoire.cache_put("search/abc.json", '{"ok": 1}')
			self.assertIsNone(grimoire.cache_get("search/abc.json", ttl=60))

	def test_miss_when_expired(self) -> None:
		grimoire.cache_put("packages.list", "foo\nbar")
		stale = time.time() - 120
		os.utime(grimoire.CACHE_DIR / "packages.list", (stale, stale))
		self.assertIsNone(grimoire.cache_get("packages.list", ttl=60))

	def test_clear_search_cache_removes_dir(self) -> None:
		# subdir, so the enclosing TemporaryDirectory survives the rmtree
		sub = grimoire.CACHE_DIR / ".searchcache"
		with mock.patch.object(grimoire, "CACHE_DIR", sub):
			grimoire.cache_put("search/abc.json", '{"ok": 1}')
			grimoire.clear_search_cache()
			self.assertFalse(sub.exists())
			# idempotent when already gone
			grimoire.clear_search_cache()

	def test_expired_entry_is_pruned(self) -> None:
		grimoire.cache_put("packages.list", "foo\nbar")
		path = grimoire.CACHE_DIR / "packages.list"
		stale = time.time() - 120
		os.utime(path, (stale, stale))
		grimoire.cache_get("packages.list", ttl=60)
		self.assertFalse(path.exists())


class CachedJsonTests(unittest.TestCase):
	def setUp(self) -> None:
		tmp = tempfile.TemporaryDirectory()
		self.addCleanup(tmp.cleanup)
		patcher = mock.patch.object(grimoire, "CACHE_DIR", Path(tmp.name))
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_fetches_once_then_serves_from_disk(self) -> None:
		fetch = mock.Mock(return_value=["foo", "bar"])
		first = grimoire.cached_json("packages.json", 60, fetch)
		second = grimoire.cached_json("packages.json", 60, fetch)
		self.assertEqual(first, ["foo", "bar"])
		self.assertEqual(second, ["foo", "bar"])
		fetch.assert_called_once()

	def test_none_result_is_not_cached(self) -> None:
		fetch = mock.Mock(return_value=None)
		self.assertIsNone(grimoire.cached_json("srcinfo/x.json", 60, fetch))
		self.assertIsNone(grimoire.cached_json("srcinfo/x.json", 60, fetch))
		self.assertEqual(fetch.call_count, 2)

	def test_corrupt_entry_refetches(self) -> None:
		grimoire.cache_put("k.json", "{not json")
		fetch = mock.Mock(return_value={"ok": 1})
		self.assertEqual(grimoire.cached_json("k.json", 60, fetch), {"ok": 1})
		fetch.assert_called_once()

	def test_zero_ttl_refetches_and_repopulates(self) -> None:
		# --refresh sets CACHE_TTL=0: every read expires, writes still land
		grimoire.cache_put("k.json", '{"stale": 1}')
		stale = time.time() - 1
		os.utime(grimoire.CACHE_DIR / "k.json", (stale, stale))
		fetch = mock.Mock(return_value={"fresh": 1})
		self.assertEqual(grimoire.cached_json("k.json", 0, fetch), {"fresh": 1})
		fetch.assert_called_once()
		self.assertEqual(
			json.loads((grimoire.CACHE_DIR / "k.json").read_text()), {"fresh": 1}
		)


class NameSourceSelectionTests(unittest.TestCase):
	def test_gz_primary_skips_git(self) -> None:
		with (
			mock.patch.object(grimoire, "_fetch_names_gz", return_value=["foo"]) as gz,
			mock.patch.object(grimoire, "_fetch_names_git") as git,
		):
			self.assertEqual(grimoire._fetch_aur_package_names(), ["foo"])
		gz.assert_called_once()
		git.assert_not_called()

	def test_gz_failure_falls_back_to_git(self) -> None:
		stderr = io.StringIO()
		with (
			mock.patch.object(grimoire, "_fetch_names_gz", return_value=None),
			mock.patch.object(
				grimoire, "_fetch_names_git", return_value=["bar"]
			) as git,
			contextlib.redirect_stderr(stderr),
		):
			self.assertEqual(grimoire._fetch_aur_package_names(), ["bar"])
		git.assert_called_once()
		self.assertIn("git mirror", stderr.getvalue())

	def test_fresh_names_write_completion_cache(self) -> None:
		tmp = tempfile.TemporaryDirectory()
		self.addCleanup(tmp.cleanup)
		# completion.cache lands in dest_root, sibling of .searchcache
		with (
			mock.patch.object(grimoire, "CACHE_DIR", Path(tmp.name) / ".searchcache"),
			mock.patch.object(grimoire, "_fetch_names_gz", return_value=["foo", "bar"]),
		):
			grimoire._fetch_aur_package_names_with_completion()
		self.assertEqual(
			(Path(tmp.name) / "completion.cache").read_text(), "foo\nbar\n"
		)


class GitSearchCacheTests(unittest.TestCase):
	def setUp(self) -> None:
		tmp = tempfile.TemporaryDirectory()
		self.addCleanup(tmp.cleanup)
		self.cache_dir = Path(tmp.name)
		for target, value in (
			("CACHE_DIR", self.cache_dir),
			# force the git-mirror name list so packages.gz never hits the network
			("_fetch_names_gz", mock.Mock(return_value=None)),
			("get_aur_remote", mock.Mock(return_value="https://aur.example")),
			("installed_package_set", mock.Mock(return_value=set())),
		):
			patcher = mock.patch.object(grimoire, target, value)
			patcher.start()
			self.addCleanup(patcher.stop)

	def test_empty_mirror_output_is_not_cached(self) -> None:
		with mock.patch.object(grimoire, "run_command", return_value=""):
			results = grimoire.search_packages_git(regex=None, needle="foo", limit=None)
		self.assertEqual(results, [])
		self.assertFalse((self.cache_dir / "packages.json").exists())

	def test_metadata_failure_drops_entry_without_killing_search(self) -> None:
		ls_remote = "abc123\trefs/heads/foopkg\ndef456\trefs/heads/foolib\n"

		def srcinfo(package: str) -> tuple[str, str]:
			if package == "foopkg":
				raise grimoire.AurGitError("boom")
			return ("1.0", "desc")

		with (
			mock.patch.object(grimoire, "run_command", return_value=ls_remote),
			mock.patch.object(grimoire, "git_srcinfo_metadata", side_effect=srcinfo),
		):
			results = grimoire.search_packages_git(regex=None, needle="foo", limit=None)
		self.assertEqual([r.name for r in results], ["foolib"])


if __name__ == "__main__":
	unittest.main()
