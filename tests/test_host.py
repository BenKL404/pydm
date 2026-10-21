import json
import os
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HOST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pydm_host.py")


def call_host(msg, env=None):
    raw = json.dumps(msg).encode()
    r = subprocess.run([sys.executable, HOST], input=struct.pack("<I", len(raw)) + raw,
                       capture_output=True, env=env, timeout=30)
    return json.loads(r.stdout[4:])


class HostTest(unittest.TestCase):
    def test_ping(self):
        self.assertTrue(call_host({"action": "ping"})["ok"])

    def test_ytdlp_de_l_environnement(self):
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ, HOME=home, PYDM_CONFIG_DIR=os.path.join(home, "cfg"))
            self.assertFalse(call_host({"action": "ping"}, env)["ytdlp"])
            os.makedirs(os.path.join(home, ".local/share/pydm/venv/lib/python3.12/site-packages/yt_dlp"))
            self.assertTrue(call_host({"action": "ping"}, env)["ytdlp"])

    def test_non_installe(self):
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ, HOME=home, PYDM_CONFIG_DIR=os.path.join(home, "cfg"))
            t = time.time()
            reply = call_host({"action": "add", "url": "https://a.fr/x"}, env)
            self.assertLess(time.time() - t, 2)
        self.assertFalse(reply["ok"])
        self.assertIn("install.sh", reply["error"])


    def test_prefetch_ne_lance_pas(self):
        with tempfile.TemporaryDirectory() as home:
            bindir = os.path.join(home, ".local", "bin")
            os.makedirs(bindir)
            marker = os.path.join(home, "lance")
            launcher = os.path.join(bindir, "pydm")
            with open(launcher, "w") as f:
                f.write(f"#!/bin/sh\ntouch {marker}\n")
            os.chmod(launcher, 0o755)
            env = dict(os.environ, HOME=home, PYDM_CONFIG_DIR=os.path.join(home, "cfg"))
            t = time.time()
            reply = call_host({"action": "prefetch", "url": "https://www.youtube.com/watch?v=a"}, env)
            self.assertLess(time.time() - t, 2)
            time.sleep(0.3)
            self.assertFalse(os.path.exists(marker))
        self.assertFalse(reply["ok"])


    def test_lancement_appimage(self):
        with tempfile.TemporaryDirectory() as home:
            mark = os.path.join(home, "lance")
            fake = os.path.join(home, "PyDM.AppImage")
            with open(fake, "w") as f:
                f.write(f'#!/bin/sh\necho "$@" > "{mark}"\n')
            os.chmod(fake, 0o755)
            env = dict(os.environ, HOME=home, PYDM_CONFIG_DIR=os.path.join(home, "cfg"), APPIMAGE=fake,
                       PYDM_HOST_RETRIES="4")
            reply = call_host({"action": "add", "url": "https://a.fr/x"}, env)   # PyDM ne répond jamais
            self.assertFalse(reply["ok"])
            self.assertNotIn("install.sh", reply["error"])
            time.sleep(0.3)
            with open(mark) as f:
                self.assertEqual(f.read().strip(), "--minimized")

    def test_ping_fige(self):
        sys.path.insert(0, os.path.dirname(HOST))
        try:
            import pydm_host
        finally:
            sys.path.pop(0)
        with mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(pydm_host, "send_message") as send, \
                mock.patch.object(pydm_host, "read_message", return_value={"action": "ping"}), \
                mock.patch.object(pydm_host, "YTDLP", "/nulle/part/yt_dlp"):
            pydm_host.main()
        self.assertTrue(send.call_args[0][0]["ytdlp"])

if __name__ == "__main__":
    unittest.main()
