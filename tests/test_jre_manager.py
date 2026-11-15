"""Tests for the optional apt-based JRE installation helpers."""
import unittest
from unittest.mock import patch

from mc_tui import jre_manager


class TestJreManager(unittest.TestCase):
    def test_supported_versions(self):
        self.assertEqual(jre_manager.JRE_VERSIONS, (8, 17, 21, 25))

    def test_package_names(self):
        for version in jre_manager.JRE_VERSIONS:
            self.assertEqual(jre_manager.package_name(version), f"openjdk-{version}-jre")

    @patch("mc_tui.jre_manager.shutil.which", return_value="/usr/bin/apt-get")
    @patch("mc_tui.jre_manager.os.geteuid", return_value=0)
    def test_root_runs_apt_directly(self, _mock_euid, _mock_which):
        self.assertEqual(
            jre_manager.get_install_command(17),
            ["apt-get", "install", "-y", "openjdk-17-jre"],
        )

    @patch("mc_tui.jre_manager.shutil.which")
    @patch("mc_tui.jre_manager.os.geteuid", return_value=1000)
    def test_regular_user_uses_sudo(self, _mock_euid, mock_which):
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        self.assertEqual(
            jre_manager.get_install_command(21),
            ["sudo", "apt-get", "install", "-y", "openjdk-21-jre"],
        )

    @patch("mc_tui.jre_manager.shutil.which")
    @patch("mc_tui.jre_manager.os.geteuid", return_value=1000)
    def test_pkexec_fallback(self, _mock_euid, mock_which):
        def which(name):
            return {"apt-get": "/usr/bin/apt-get", "pkexec": "/usr/bin/pkexec"}.get(name)

        mock_which.side_effect = which
        self.assertEqual(
            jre_manager.get_install_command(8),
            ["pkexec", "apt-get", "install", "-y", "openjdk-8-jre"],
        )

    @patch("mc_tui.jre_manager.shutil.which", return_value=None)
    def test_no_apt_available(self, _mock_which):
        self.assertIsNone(jre_manager.get_install_command(25))

    @patch("mc_tui.jre_manager.shutil.which")
    @patch("mc_tui.jre_manager.os.geteuid", return_value=1000)
    def test_no_privilege_helper(self, _mock_euid, mock_which):
        mock_which.side_effect = lambda name: "/usr/bin/apt-get" if name == "apt-get" else None
        self.assertIsNone(jre_manager.get_install_command(17))

    @patch("mc_tui.jre_manager.get_install_command", return_value=["apt-get", "install"])
    @patch("mc_tui.jre_manager.subprocess.call", return_value=0)
    def test_install_success(self, _mock_call, _mock_command):
        self.assertEqual(jre_manager.install_jre(17), (True, 0))

    @patch("mc_tui.jre_manager.get_install_command", return_value=["apt-get", "install"])
    @patch("mc_tui.jre_manager.subprocess.call", return_value=100)
    def test_install_failure(self, _mock_call, _mock_command):
        self.assertEqual(jre_manager.install_jre(17), (False, 100))

    @patch("mc_tui.jre_manager.get_install_command", return_value=["apt-get", "install"])
    @patch("mc_tui.jre_manager.subprocess.call", side_effect=KeyboardInterrupt)
    def test_install_cancelled(self, _mock_call, _mock_command):
        self.assertEqual(jre_manager.install_jre(17), (False, -1))


if __name__ == "__main__":
    unittest.main()
