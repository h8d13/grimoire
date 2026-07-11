"""--native routes compiler flags through a generated makepkg.conf overlay.

Env-var CFLAGS can't work: makepkg's load_makepkg_config only preserves a fixed
allowlist (PKGDEST..CARCH) and the conf files assign CFLAGS unconditionally. The
overlay replays makepkg's config chain then appends the native flags, and
build_and_install passes it via `makepkg --config`. `nativeflags` prints the
expanded (machine-pinned) equivalents parsed from gcc/rustc output.
"""

import tempfile
import unittest
from pathlib import Path

from grimoireshim import grimoire

# Abbreviated from real `gcc -### -E - -march=native -mtune=native` stderr
# (gcc 16): mixed quoting, --param pairs, and the trailing `-dumpbase -`.
GCC_TRACE = """\
Using built-in specs.
COLLECT_GCC=gcc
Target: x86_64-pc-linux-gnu
gcc version 16.0.0 (GCC)
COLLECT_GCC_OPTIONS='-E' '-march=native' '-mtune=native'
 /usr/lib/gcc/x86_64-pc-linux-gnu/16/cc1 -E -quiet - "-march=alderlake" -mmmx \
-mavx2 -mno-sse4a --param "l1-cache-size=48" "-mtune=alderlake" -dumpbase -
"""

# Abbreviated from real `rustc -C target-cpu=native --print cfg` stdout,
# plus a synthetic crt-static line (some targets list it; it must be dropped).
RUSTC_CFG = """\
debug_assertions
panic="unwind"
target_arch="x86_64"
target_feature="adx"
target_feature="aes"
target_feature="crt-static"
target_feature="sse4.1"
target_has_atomic="64"
unix
"""


class ParseNativeFlagsTests(unittest.TestCase):
	def test_cc1_line_yields_flags_only(self) -> None:
		flags = grimoire._parse_cc1_flags(GCC_TRACE)
		if flags is None:
			self.fail("no flags parsed from cc1 line")
		self.assertTrue(flags.startswith("-march=alderlake"))
		self.assertIn("--param l1-cache-size=48", flags)
		self.assertIn("-mtune=alderlake", flags)
		# driver noise and the -dumpbase pair must not leak into CFLAGS
		self.assertNotIn("cc1", flags)
		self.assertNotIn("-quiet", flags)
		self.assertNotIn("-dumpbase", flags)
		self.assertNotIn('"', flags)

	def test_no_cc1_line_is_none(self) -> None:
		self.assertIsNone(grimoire._parse_cc1_flags("Using built-in specs.\n"))

	def test_rust_features_comma_plus_form(self) -> None:
		self.assertEqual(
			grimoire._parse_rust_features(RUSTC_CFG),
			"-Ctarget-feature=+adx,+aes,+sse4.1",
		)

	def test_rust_no_features_is_none(self) -> None:
		self.assertIsNone(grimoire._parse_rust_features("unix\n"))


class NativeConfTests(unittest.TestCase):
	def setUp(self) -> None:
		tmp = tempfile.TemporaryDirectory()
		self.addCleanup(tmp.cleanup)
		self.root = Path(tmp.name)

	def test_overlay_sources_chain_then_appends(self) -> None:
		conf = grimoire._write_native_conf(self.root)
		self.assertEqual(conf, self.root / "native.makepkg.conf")
		text = conf.read_text()
		# makepkg skips /etc and user confs for a non-default --config file, so
		# the overlay must replay them itself, in makepkg's order, BEFORE the
		# appends (appended -march wins over the conf's -march=x86-64).
		order = [
			text.index("source /etc/makepkg.conf"),
			text.index("/etc/makepkg.conf.d/"),
			text.index("pacman/makepkg.conf"),
			text.index("$HOME/.makepkg.conf"),
			text.index('CFLAGS+=" -march=native -mtune=native"'),
			text.index('CXXFLAGS+=" -march=native -mtune=native"'),
			text.index('RUSTFLAGS+=" -C target-cpu=native"'),
		]
		self.assertEqual(order, sorted(order))

	def test_build_passes_config_only_when_native(self) -> None:
		(self.root / "PKGBUILD").write_text("pkgname=foo\npkgver=1\n")
		calls: list[list[str]] = []

		def fake_run(cmd: list[str], **kwargs: object) -> None:
			calls.append(list(cmd))

		orig_run = grimoire.run_command
		grimoire.run_command = fake_run
		self.addCleanup(setattr, grimoire, "run_command", orig_run)
		self.addCleanup(setattr, grimoire.CONFIG, "native_conf", None)

		grimoire.CONFIG.native_conf = None
		grimoire.build_and_install(self.root, noconfirm=True)
		self.assertNotIn("--config", calls[-1])

		conf = grimoire._write_native_conf(self.root)
		grimoire.CONFIG.native_conf = conf
		grimoire.build_and_install(self.root, noconfirm=True)
		self.assertEqual(calls[-1][0], "makepkg")
		idx = calls[-1].index("--config")
		self.assertEqual(calls[-1][idx + 1], str(conf))


class NativeParserTests(unittest.TestCase):
	def test_native_is_global_and_hoistable(self) -> None:
		parser, commands = grimoire.build_parser()
		self.assertIn("nativeflags", commands)
		self.assertIn("--native", grimoire._GLOBAL_FLAG_OPTIONS)
		args = parser.parse_args(["--native", "install", "foo"])
		self.assertTrue(args.native)


if __name__ == "__main__":
	unittest.main()
