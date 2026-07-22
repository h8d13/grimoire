"""Virtual-provider resolution must ask pacman with dep resolution OFF.

The catch: for a virtual dep (pandoc, provided by pandoc-cli), plain
`pacman -Sp --print-format %n` prints the ENTIRE would-be install chain in
dependency order, requested target LAST. Taking line 0 therefore returns the
deepest transitive dep (haskell-lua), which gets installed yet leaves the
virtual dep unsatisfied. `-Sddp` (--nodeps twice) skips resolution so the
output is exactly the one package satisfying the dep.

Tested against a fake pacman that reproduces both behaviors, so the test is
independent of the host's sync DBs and makepkg/pacman config.
"""

import unittest
from unittest import mock

from grimoireshim import grimoire

# Real `pacman -Sp --print-format %n pandoc` chain, abbreviated: transitive
# deps first, the actual provider last.
FULL_CHAIN = "haskell-lua\nhaskell-hslua-core\nhaskell-pandoc\npandoc-cli\n"


def _nodeps_level(cmd: list[str]) -> int:
	# Count -d occurrences the way pacman does: each --nodeps or each `d`
	# inside a short-option cluster (-Sddp) raises the level by one.
	level = cmd.count("--nodeps")
	for arg in cmd:
		if arg.startswith("-") and not arg.startswith("--"):
			level += arg.count("d")
	return level


def fake_pacman_run(cmd: list[str], **_kwargs: object) -> str:
	# -dd -> only the requested target; plain -Sp -> full install chain.
	if _nodeps_level(cmd) >= 2:
		return "pandoc-cli\n"
	return FULL_CHAIN


class ResolveOfficialDependencyTests(unittest.TestCase):
	def test_virtual_dep_resolves_to_provider_not_chain_head(self) -> None:
		with (
			mock.patch.object(grimoire, "exists_in_sync_repo", return_value=False),
			mock.patch.object(grimoire, "run_command", fake_pacman_run),
		):
			provider = grimoire.resolve_official_dependency("pandoc")
		self.assertEqual(
			provider,
			"pandoc-cli",
			"resolver read the -Sp install chain head (deepest transitive "
			"dep) instead of the provider; pacman must be called with -dd",
		)

	def test_real_package_short_circuits_on_sync_repo(self) -> None:
		with (
			mock.patch.object(grimoire, "exists_in_sync_repo", return_value=True),
			mock.patch.object(
				grimoire, "run_command", side_effect=AssertionError("no -Sp needed")
			),
		):
			self.assertEqual(grimoire.resolve_official_dependency("gcc"), "gcc")

	def test_unknown_dep_is_none(self) -> None:
		def raise_err(cmd: list[str], **_kwargs: object) -> str:
			raise grimoire.GrimoireErr("target not found")

		with (
			mock.patch.object(grimoire, "exists_in_sync_repo", return_value=False),
			mock.patch.object(grimoire, "run_command", raise_err),
		):
			self.assertIsNone(grimoire.resolve_official_dependency("no-such-pkg"))


if __name__ == "__main__":
	unittest.main()
