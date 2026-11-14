import unittest
from mc_tui.java_detector import parse_java_version, find_best_java, detect_all_javas


class TestJavaDetector(unittest.TestCase):
    def test_parse_java_version(self):
        v1, m1 = parse_java_version('openjdk version "25.0.4.1" 2026-08-18')
        self.assertEqual(m1, 25)
        self.assertEqual(v1, "25.0.4.1")

        v2, m2 = parse_java_version('java version "1.8.0_351"')
        self.assertEqual(m2, 8)
        self.assertEqual(v2, "1.8.0_351")

        v3, m3 = parse_java_version('openjdk version "17.0.9" 2023-10-17')
        self.assertEqual(m3, 17)
        self.assertEqual(v3, "17.0.9")

    def test_detect_system_java(self):
        javas = detect_all_javas()
        self.assertTrue(len(javas) > 0)
        best = find_best_java()
        self.assertIsNotNone(best)


if __name__ == "__main__":
    unittest.main()
