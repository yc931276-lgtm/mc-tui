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
            self.assertTrue(cfg_file.exists())

    def test_update_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_file = Path(tmpdir) / "config.json"
            cfg = Config(cfg_file)
            cfg.username = "Steve"
            cfg.max_ram = "8G"

            # Re-read
            cfg2 = Config(cfg_file)
            self.assertEqual(cfg2.username, "Steve")
            self.assertEqual(cfg2.max_ram, "8G")


if __name__ == "__main__":
    unittest.main()
