import unittest
from unittest import mock

from grimaurshim import grimaur


class BackendTriStateTests(unittest.TestCase):
	def test_default_is_auto(self):
		args = grimaur.build_parser().parse_args(["list"])
		self.assertIsNone(args.aur_rpc)

	def test_aur_rpc_forces_rpc(self):
		args = grimaur.build_parser().parse_args(["--aur-rpc", "list"])
		self.assertTrue(args.aur_rpc)

	def test_git_mirror_forces_mirror(self):
		args = grimaur.build_parser().parse_args(["--git-mirror", "list"])
		self.assertFalse(args.aur_rpc)

	def test_last_flag_wins(self):
		args = grimaur.build_parser().parse_args(["--git-mirror", "--aur-rpc", "list"])
		self.assertTrue(args.aur_rpc)


class DisableAurRpcTests(unittest.TestCase):
	def test_forced_rpc_raises_instead_of_falling_back(self):
		with (
			mock.patch.object(grimaur, "FORCE_AUR_RPC", True),
			mock.patch.object(grimaur, "USE_AUR_RPC", True),
		):
			with self.assertRaises(grimaur.AurRpcForcedError):
				grimaur.disable_aur_rpc("timed out")
			self.assertTrue(grimaur.USE_AUR_RPC)

	def test_auto_mode_falls_back(self):
		with (
			mock.patch.object(grimaur, "FORCE_AUR_RPC", False),
			mock.patch.object(grimaur, "FORCE_GIT_MIRROR", False),
			mock.patch.object(grimaur, "USE_AUR_RPC", True),
			mock.patch.object(grimaur, "_RPC_FALLBACK_NOTIFIED", True),
		):
			grimaur.disable_aur_rpc("timed out")
			self.assertFalse(grimaur.USE_AUR_RPC)

	def test_forced_error_is_not_swallowed_as_fallback_signal(self):
		self.assertNotIsInstance(grimaur.AurRpcForcedError("x"), grimaur.AurGitError)


if __name__ == "__main__":
	unittest.main()
