import json
import tempfile
import unittest
from pathlib import Path
from mc_tui.version_parser import (
    evaluate_rules,
    maven_to_path,
    get_offline_uuid,
    VersionScanner,
)


class TestParser(unittest.TestCase):
    def test_maven_to_path(self):
        p1 = maven_to_path("org.lwjgl:lwjgl:3.3.1")
        self.assertEqual(p1, "org/lwjgl/lwjgl/3.3.1/lwjgl-3.3.1.jar")

        p2 = maven_to_path("org.lwjgl:lwjgl:3.3.1:natives-linux")
        self.assertEqual(p2, "org/lwjgl/lwjgl/3.3.1/lwjgl-3.3.1-natives-linux.jar")

        p3 = maven_to_path("com.example:lib:1.0@zip")
        self.assertEqual(p3, "com/example/lib/1.0/lib-1.0.zip")

    def test_evaluate_rules(self):
        rules = [
            {"action": "allow"},
            {"action": "disallow", "os": {"name": "osx"}},
        ]
        self.assertTrue(evaluate_rules(rules, current_os="linux"))
        self.assertFalse(evaluate_rules(rules, current_os="osx"))

        rules_linux_only = [
            {"action": "allow", "os": {"name": "linux"}},
        ]
        self.assertTrue(evaluate_rules(rules_linux_only, current_os="linux"))
        self.assertFalse(evaluate_rules(rules_linux_only, current_os="windows"))

    def test_offline_uuid(self):
        u1 = get_offline_uuid("Steve")
        u2 = get_offline_uuid("Steve")
        u3 = get_offline_uuid("Alex")
        self.assertEqual(u1, u2)
        self.assertNotEqual(u1, u3)
        self.assertTrue(len(u1) == 36)

    def test_scanner_and_inheritance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            v_dir = root / "versions"
            v_dir.mkdir()

            # Parent version
            v_parent = v_dir / "1.20.4"
            v_parent.mkdir()
            (v_parent / "1.20.4.jar").touch()
            with open(v_parent / "1.20.4.json", "w") as f:
                json.dump({
                    "id": "1.20.4",
                    "type": "release",
                    "mainClass": "net.minecraft.client.main.Main",
                    "javaVersion": {"majorVersion": 17},
                    "arguments": {
                        "game": ["--demo"],
                        "jvm": ["-Dparent=true"]
                    },
                    "libraries": [
                        {"name": "com.mojang:authlib:5.0.47"}
                    ]
                }, f)

            # Child version (Fabric style)
            v_child = v_dir / "fabric-loader-1.20.4"
            v_child.mkdir()
            with open(v_child / "fabric-loader-1.20.4.json", "w") as f:
                json.dump({
                    "id": "fabric-loader-1.20.4",
                    "inheritsFrom": "1.20.4",
                    "type": "modified",
                    "mainClass": "net.fabricmc.loader.impl.launch.knot.KnotClient",
                    "arguments": {
                        "game": ["--quickPlayPath", "dummy"],
                        "jvm": ["-Dchild=true"]
                    },
                    "libraries": [
                        {"name": "net.fabricmc:fabric-loader:0.15.7"}
                    ]
                }, f)

            scanner = VersionScanner(root)
            versions = scanner.list_versions()
            self.assertEqual(len(versions), 2)

            resolved = scanner.resolve_version_tree("fabric-loader-1.20.4")
            self.assertEqual(resolved["id"], "fabric-loader-1.20.4")
            self.assertEqual(resolved["mainClass"], "net.fabricmc.loader.impl.launch.knot.KnotClient")
            self.assertEqual(resolved["jar"], "1.20.4")
            self.assertEqual(len(resolved["libraries"]), 2)
            self.assertIn("-Dparent=true", resolved["arguments"]["jvm"])
            self.assertIn("-Dchild=true", resolved["arguments"]["jvm"])


if __name__ == "__main__":
    unittest.main()
