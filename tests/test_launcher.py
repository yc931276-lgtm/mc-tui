import json
import tempfile
import unittest
from pathlib import Path
from mc_tui.config import Config
from mc_tui.launcher import Launcher
from mc_tui.version_parser import VersionScanner


class TestLauncher(unittest.TestCase):
    def test_legacy_launch_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cfg_path = root / "config.json"
            cfg = Config(cfg_path)
            cfg.game_dir = root
            cfg.username = "TestPlayer"
            cfg.min_ram = "512M"
            cfg.max_ram = "2G"

            v_dir = root / "versions" / "1.12.2"
            v_dir.mkdir(parents=True)
            (v_dir / "1.12.2.jar").touch()

            libs_dir = root / "libraries" / "org" / "lwjgl" / "lwjgl" / "2.9.4"
            libs_dir.mkdir(parents=True)
            (libs_dir / "lwjgl-2.9.4.jar").touch()

            with open(v_dir / "1.12.2.json", "w") as f:
                json.dump({
                    "id": "1.12.2",
                    "type": "release",
                    "mainClass": "net.minecraft.client.main.Main",
                    "minecraftArguments": "--username ${auth_player_name} --version ${version_name} --gameDir ${game_directory} --uuid ${auth_uuid}",
                    "libraries": [
                        {"name": "org.lwjgl:lwjgl:2.9.4"}
                    ]
                }, f)

            scanner = VersionScanner(root)
            versions = scanner.list_versions()
            self.assertEqual(len(versions), 1)

            launcher = Launcher(cfg)
            plan = launcher.build_launch_plan(versions[0])

            self.assertIn("-Xms512M", plan.args)
            self.assertIn("-Xmx2G", plan.args)
            self.assertEqual(plan.main_class, "net.minecraft.client.main.Main")
            self.assertIn("TestPlayer", plan.args)
            self.assertIn("1.12.2", plan.args)
            self.assertIn(str(root), plan.args)

    def test_modern_launch_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cfg_path = root / "config.json"
            cfg = Config(cfg_path)
            cfg.game_dir = root
            cfg.username = "ModernPlayer"

            v_dir = root / "versions" / "1.20.4"
            v_dir.mkdir(parents=True)
            (v_dir / "1.20.4.jar").touch()

            with open(v_dir / "1.20.4.json", "w") as f:
                json.dump({
                    "id": "1.20.4",
                    "type": "release",
                    "mainClass": "net.minecraft.client.main.Main",
                    "arguments": {
                        "game": [
                            "--username", "${auth_player_name}",
                            "--version", "${version_name}",
                            {"rules": [{"action": "allow"}], "value": ["--demo"]}
                        ],
                        "jvm": [
                            "-Dcustom.prop=true",
                            {"rules": [{"action": "allow", "os": {"name": "linux"}}], "value": "-Dplatform=linux"}
                        ]
                    },
                    "libraries": []
                }, f)

            scanner = VersionScanner(root)
            versions = scanner.list_versions()
            launcher = Launcher(cfg)
            plan = launcher.build_launch_plan(versions[0])

            self.assertIn("ModernPlayer", plan.args)
            self.assertIn("--demo", plan.args)
            self.assertIn("-Dcustom.prop=true", plan.args)
            self.assertIn("-Dplatform=linux", plan.args)


if __name__ == "__main__":
    unittest.main()
