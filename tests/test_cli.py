import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class CliTest(unittest.TestCase):
    def test_help(self):
        r = subprocess.run([sys.executable, "-m", "pydm", "--help"], cwd=ROOT,
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--connections", r.stdout)


if __name__ == "__main__":
    unittest.main()
