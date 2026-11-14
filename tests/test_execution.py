import json
import os
import stat
import tempfile
import time
import unittest
from pathlib import Path
from mc_tui.config import Config
from mc_tui.launcher import Launcher, MinecraftProcess, LaunchPlan
from mc_tui.version_parser import VersionScanner


class TestExecution(unittest.TestCase):
    def test_mock_game_execution_and_logs(self):
        """Test process execution, real-time log capturing, and termination."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cfg = Config(root / "config.json")
            cfg.game_dir = root
            cfg.username = "LocalHero"

            # Create a mock java executable script
            mock_java = root / "mock_java.sh"
            mock_java.write_text(
                "#!/bin/sh\n"
                "echo '[INFO] Mock Minecraft starting for user:' \"$@\"\n"
                "echo '[INFO] Initializing Minecraft world...'\n"
                "sleep 0.1\n"
                "echo '[INFO] Done loading mock world.'\n"
            )
            mock_java.chmod(mock_java.stat().st_mode | stat.S_IEXEC)
            cfg.java_path = str(mock_java)

            # Setup mock version
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
                            "--version", "${version_name}"
                        ],
                        "jvm": []
                    },
                    "libraries": []
                }, f)

            scanner = VersionScanner(root)
            versions = scanner.list_versions()
            self.assertEqual(len(versions), 1)

            launcher = Launcher(cfg)
            captured_logs = []
            proc = launcher.launch(versions[0], log_callback=lambda l: captured_logs.append(l))

            # Wait for finish
            if proc._thread:
                proc._thread.join(timeout=3)

            self.assertEqual(proc.exit_code, 0)
            self.assertFalse(proc.is_running)

            combined_logs = "\n".join(captured_logs)
            self.assertIn("LocalHero", combined_logs)
            self.assertIn("Done loading mock world.", combined_logs)
            self.assertTrue(any("Done loading mock world." in l for l in proc.log_buffer))

    def test_process_stop(self):
        """Test terminating a running process."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mock_sleep = root / "mock_sleep.sh"
            mock_sleep.write_text(
                "#!/bin/sh\n"
                "echo '[INFO] Process running...'\n"
                "sleep 10\n"
            )
            mock_sleep.chmod(mock_sleep.stat().st_mode | stat.S_IEXEC)

            plan = LaunchPlan(
                java_bin=str(mock_sleep),
                args=[],
                cwd=root,
                natives_dir=root,
                classpath=[],
                main_class="",
            )

            proc = MinecraftProcess(plan)
            proc.start()
            time.sleep(0.2)
            self.assertTrue(proc.is_running)

            proc.stop()
            time.sleep(0.2)
            self.assertFalse(proc.is_running)


if __name__ == "__main__":
    unittest.main()
