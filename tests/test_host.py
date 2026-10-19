import json
import os
import struct
import subprocess
import sys
import tempfile
import time
import unittest

HOST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pydm_host.py")


def call_host(msg, env=None):
    raw = json.dumps(msg).encode()
    r = subprocess.run([sys.executable, HOST], input=struct.pack("<I", len(raw)) + raw,
                       capture_output=True, env=env, timeout=30)
    return json.loads(r.stdout[4:])


class HostTest(unittest.TestCase):
    def test_ping(self):
        self.assertTrue(call_host({"action": "ping"})["ok"])

    def test_non_installe(self):
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ, HOME=home, PYDM_CONFIG_DIR=os.path.join(home, "cfg"))
            t = time.time()
            reply = call_host({"action": "add", "url": "https://a.fr/x"}, env)
            self.assertLess(time.time() - t, 2)
        self.assertFalse(reply["ok"])
        self.assertIn("install.sh", reply["error"])


if __name__ == "__main__":
    unittest.main()
