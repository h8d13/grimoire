import hashlib
import json
import os
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request  # ensure loaded: grimaur imports it lazily, tests patch it
from pathlib import Path
from unittest import mock

from grimaurshim import grimaur


def _search_cache_key(pattern):
	query = urllib.parse.urlencode(
		{"v": "5", "type": "search", "arg": pattern}, doseq=True
	)
	return f"search/{hashlib.sha256(query.encode()).hexdigest()}.json"


class CacheHelperTests(unittest.TestCase):
	def setUp(self):
		tmp = tempfile.TemporaryDirectory()
		self.addCleanup(tmp.cleanup)
		patcher = mock.patch.object(grimaur, "CACHE_DIR", Path(tmp.name))
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_roundtrip(self):
		grimaur.cache_put("search/abc.json", '{"ok": 1}')
		self.assertEqual(grimaur.cache_get("search/abc.json", ttl=60), '{"ok": 1}')

	def test_miss_when_absent(self):
		self.assertIsNone(grimaur.cache_get("nope.json", ttl=60))

	def test_miss_when_expired(self):
		grimaur.cache_put("packages.list", "foo\nbar")
		stale = time.time() - 120
		os.utime(grimaur.CACHE_DIR / "packages.list", (stale, stale))
		self.assertIsNone(grimaur.cache_get("packages.list", ttl=60))


class CachedJsonTests(unittest.TestCase):
	def setUp(self):
		tmp = tempfile.TemporaryDirectory()
		self.addCleanup(tmp.cleanup)
		patcher = mock.patch.object(grimaur, "CACHE_DIR", Path(tmp.name))
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_fetches_once_then_serves_from_disk(self):
		fetch = mock.Mock(return_value=["foo", "bar"])
		first = grimaur.cached_json("packages.json", 60, fetch)
		second = grimaur.cached_json("packages.json", 60, fetch)
		self.assertEqual(first, ["foo", "bar"])
		self.assertEqual(second, ["foo", "bar"])
		fetch.assert_called_once()

	def test_none_result_is_not_cached(self):
		fetch = mock.Mock(return_value=None)
		self.assertIsNone(grimaur.cached_json("srcinfo/x.json", 60, fetch))
		self.assertIsNone(grimaur.cached_json("srcinfo/x.json", 60, fetch))
		self.assertEqual(fetch.call_count, 2)

	def test_corrupt_entry_refetches(self):
		grimaur.cache_put("k.json", "{not json")
		fetch = mock.Mock(return_value={"ok": 1})
		self.assertEqual(grimaur.cached_json("k.json", 60, fetch), {"ok": 1})
		fetch.assert_called_once()


class RpcSearchCacheTests(unittest.TestCase):
	def setUp(self):
		tmp = tempfile.TemporaryDirectory()
		self.addCleanup(tmp.cleanup)
		patcher = mock.patch.object(grimaur, "CACHE_DIR", Path(tmp.name))
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_served_from_cache_without_network(self):
		grimaur.cache_put(
			_search_cache_key("foo"),
			json.dumps({"type": "search", "results": [{"Name": "foo"}]}),
		)
		with mock.patch.object(
			grimaur.urllib.request, "urlopen", side_effect=AssertionError
		) as urlopen:
			results = grimaur.aur_rpc_search_results("foo")
		self.assertEqual([entry["Name"] for entry in results], ["foo"])
		urlopen.assert_not_called()

	def test_corrupt_cache_falls_through_to_network(self):
		grimaur.cache_put(_search_cache_key("foo"), "{not json")
		with mock.patch.object(
			grimaur.urllib.request,
			"urlopen",
			side_effect=urllib.error.URLError("offline"),
		) as urlopen:
			results = grimaur.aur_rpc_search_results("foo")
		self.assertEqual(results, [])
		urlopen.assert_called_once()


if __name__ == "__main__":
	unittest.main()
