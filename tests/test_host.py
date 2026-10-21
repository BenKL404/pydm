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

    @unittest.skipIf(os.name == "nt", "lanceur POSIX (install.sh, AppImage)")
    def test_ytdlp_de_l_environnement(self):
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ, HOME=home, PYDM_CONFIG_DIR=os.path.join(home, "cfg"))
            self.assertFalse(call_host({"action": "ping"}, env)["ytdlp"])
            os.makedirs(os.path.join(home, ".local/share/pydm/venv/lib/python3.12/site-packages/yt_dlp"))
            self.assertTrue(call_host({"action": "ping"}, env)["ytdlp"])

    @unittest.skipIf(os.name == "nt", "lanceur POSIX (install.sh, AppImage)")
    def test_non_installe(self):
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ, HOME=home, PYDM_CONFIG_DIR=os.path.join(home, "cfg"))
            t = time.time()
            reply = call_host({"action": "add", "url": "https://a.fr/x"}, env)
            self.assertLess(time.time() - t, 2)
        self.assertFalse(reply["ok"])
        self.assertIn("install.sh", reply["error"])


    @unittest.skipIf(os.name == "nt", "lanceur POSIX (install.sh, AppImage)")
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


    @unittest.skipIf(os.name == "nt", "lanceur POSIX (install.sh, AppImage)")
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

    def test_meme_adresse(self):
        sys.path.insert(0, os.path.dirname(HOST))
        try:
            import pydm_host
        finally:
            sys.path.pop(0)
        from pydm import ipc
        for args in ((None, "Élodie Durand"), ("C:\\x\\cfg", "u")):
            self.assertEqual(pydm_host.pipe_address(*args), ipc.pipe_address(*args))

    def test_lancement_windows(self):
        sys.path.insert(0, os.path.dirname(HOST))
        try:
            import pydm_host
        finally:
            sys.path.pop(0)
        exe = "C:\\Users\\Élodie Durand\\Programs\\PyDM\\pydm-host.exe"
        with mock.patch.object(pydm_host, "WINDOWS", True), mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "executable", exe), mock.patch.object(pydm_host, "RETRIES", 1), \
                mock.patch.object(pydm_host, "_send", side_effect=FileNotFoundError), \
                mock.patch.object(pydm_host.os.path, "exists", return_value=True), \
                mock.patch.object(pydm_host.subprocess, "Popen") as popen, mock.patch.object(pydm_host.time, "sleep"):
            pydm_host.forward({"action": "add", "url": "https://a.fr/x"})
        args, kwargs = popen.call_args
        self.assertEqual(args[0], ["C:\\Users\\Élodie Durand\\Programs\\PyDM\\pydm.exe", "--minimized"])
        self.assertEqual(kwargs["creationflags"], 0x01000208)     # + CREATE_BREAKAWAY_FROM_JOB (Firefox)
        self.assertNotIn("start_new_session", kwargs)

    def _host(self):
        sys.path.insert(0, os.path.dirname(HOST))
        try:
            import pydm_host
        finally:
            sys.path.pop(0)
        return pydm_host

    def test_job_sans_sortie_autorisee(self):
        pydm_host = self._host()
        with mock.patch.object(pydm_host, "WINDOWS", True), mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "executable", "C:\\P\\pydm-host.exe"), mock.patch.object(pydm_host, "RETRIES", 1), \
                mock.patch.object(pydm_host, "_send", side_effect=FileNotFoundError), \
                mock.patch.object(pydm_host.os.path, "exists", return_value=True), \
                mock.patch.object(pydm_host.subprocess, "Popen", side_effect=[PermissionError(5, "job"), mock.Mock()]) as popen, \
                mock.patch.object(pydm_host.time, "sleep"):
            pydm_host.forward({"action": "add", "url": "https://a.fr/x"})
        self.assertEqual([c.kwargs["creationflags"] for c in popen.call_args_list], [0x01000208, 0x208])

    def test_message_appimage_inchange(self):
        pydm_host = self._host()
        with mock.patch.dict(os.environ, {"APPIMAGE": "/nulle/part/PyDM.AppImage"}), \
                mock.patch.object(pydm_host, "WINDOWS", False), \
                mock.patch.object(pydm_host, "_send", side_effect=FileNotFoundError):
            reply = pydm_host.forward({"action": "add", "url": "https://a.fr/x"})
        self.assertEqual(reply["error"], "PyDM introuvable : relancez l'AppImage")

    def test_attente_plus_longue_sous_windows(self):
        pydm_host = self._host()
        self.assertEqual(pydm_host.default_retries(windows=False), 60)
        self.assertEqual(pydm_host.default_retries(windows=True), 180)       # 45 s : premier lancement lent

    def test_attend_pydm_qui_demarre(self):
        pydm_host = self._host()                    # canal créé mais PyDM pas encore prêt : on attend
        with mock.patch.object(pydm_host, "_send", side_effect=[TimeoutError(), {"ok": True}]), \
                mock.patch.object(pydm_host.subprocess, "Popen") as popen, mock.patch.object(pydm_host.time, "sleep"):
            self.assertEqual(pydm_host.forward({"action": "add", "url": "https://a.fr/x"}), {"ok": True})
        popen.assert_not_called()

    def test_canal_d_un_autre(self):
        pydm_host = self._host()                    # canal occupé par un autre compte : refus clair
        from multiprocessing import AuthenticationError
        for error in (AuthenticationError("clé"), PermissionError(5, "refus")):
            with mock.patch.object(pydm_host, "_send", side_effect=error):
                reply = pydm_host.forward({"action": "add", "url": "https://a.fr/x"})
            self.assertFalse(reply["ok"])
            self.assertIn("refusée", reply["error"])

if __name__ == "__main__":
    unittest.main()
