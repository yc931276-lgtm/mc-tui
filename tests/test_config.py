import tempfile
import unittest
from pathlib import Path
from mc_tui.config import Config


class TestConfig(unittest.TestCase):
    def test_default_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_file = Path(tmpdir) / "config.json"
            cfg = Config(cfg_file)
            self.assertEqual(cfg.username, "Player")
            self.assertEqual(cfg.min_ram, "1G")
            self.assertEqual(cfg.max_ram, "4G")
            self.assertEqual(cfg.download_mirror, "official")
            self.assertTrue(cfg.download_assets)
            self.assertEqual(cfg.language, "auto")
            self.assertTrue(cfg_file.exists())

    def test_update_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_file = Path(tmpdir) / "config.json"
            cfg = Config(cfg_file)
            cfg.username = "Steve"
            cfg.max_ram = "8G"
            cfg.download_mirror = "bmclapi"
            cfg.download_assets = False
            cfg.language = "zh_CN"

            # Re-read
            cfg2 = Config(cfg_file)
            self.assertEqual(cfg2.username, "Steve")
            self.assertEqual(cfg2.max_ram, "8G")
            self.assertEqual(cfg2.download_mirror, "bmclapi")
            self.assertFalse(cfg2.download_assets)
            self.assertEqual(cfg2.language, "zh_CN")


if __name__ == "__main__":
    unittest.main()
