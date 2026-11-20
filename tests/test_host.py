import json
import os
import selectors
import socket
import struct
import subprocess
import sys
import tempfile
import threading
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


def framed(msg):
    raw = json.dumps(msg).encode()
    return struct.pack("<I", len(raw)) + raw


def read_framed(stream, timeout=10):
    """Lit un message encadré sur un tube, sans bloquer indéfiniment."""
    sel = selectors.DefaultSelector()
    sel.register(stream, selectors.EVENT_READ)
    try:
        def take(n):
            data, end = b"", time.time() + timeout
            while len(data) < n:
                if not sel.select(max(0.0, end - time.time())):
                    raise AssertionError("rien reçu de l'hôte natif")
                chunk = os.read(stream.fileno(), n - len(data))
                if not chunk:
                    raise AssertionError("l'hôte natif a fermé sa sortie")
                data += chunk
            return data
        (length,) = struct.unpack("<I", take(4))
        return json.loads(take(length))
    finally:
        sel.close()


class FakePyDM:
    """Faux PyDM : accepte le pont et donne la main au test sur la connexion."""

    def __init__(self, path):
        self.path = path
        self.srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.srv.bind(path)
        self.srv.listen(4)
        self.ready = threading.Event()
        self.conn = self.file = None
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        try:
            conn, _ = self.srv.accept()
        except OSError:
            return
        self.conn = conn
        self.file = conn.makefile()
        if json.loads(self.file.readline()).get("action") == "bridge":
            conn.sendall(b'{"ok": true}\n')
            self.ready.set()

    def ask(self, msg):
        self.conn.sendall((json.dumps(msg) + "\n").encode())

    def reply(self, timeout=10):
        self.conn.settimeout(timeout)
        return json.loads(self.file.readline() or "null")

    def close(self):
        for s in (self.conn, self.srv):
            try:
                s and s.close()
            except OSError:
                pass


@unittest.skipIf(os.name == "nt", "socket Unix (POSIX)")
class BridgeHostTest(unittest.TestCase):
    """Le port persistant relaie les demandes de PyDM vers l'extension, et ses réponses en retour."""

    def start(self, with_pydm=True):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cfg = os.path.join(tmp.name, "cfg")
        os.makedirs(cfg)
        pydm = FakePyDM(os.path.join(cfg, "pydm.sock")) if with_pydm else None
        if pydm:
            self.addCleanup(pydm.close)
        env = dict(os.environ, HOME=tmp.name, PYDM_CONFIG_DIR=cfg)
        proc = subprocess.Popen([sys.executable, HOST], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, env=env)
        self.addCleanup(proc.kill)
        proc.stdin.write(framed({"action": "bridge"}))
        proc.stdin.flush()
        return proc, pydm, cfg

    def test_relais_dans_les_deux_sens(self):
        proc, pydm, _ = self.start()
        self.assertTrue(pydm.ready.wait(10), "le pont n'a pas été ouvert")
        pydm.ask({"id": "42", "action": "refresh", "url": "https://a.fr/f", "referer": "https://a.fr/p"})
        demande = read_framed(proc.stdout)
        self.assertEqual(demande, {"id": "42", "action": "refresh",
                                   "url": "https://a.fr/f", "referer": "https://a.fr/p"})
        proc.stdin.write(framed({"id": "42", "headers": {"Cookie": "SID=9"}}))
        proc.stdin.flush()
        self.assertEqual(pydm.reply(), {"id": "42", "headers": {"Cookie": "SID=9"}})

    def test_fin_du_port_arrete_l_hote(self):
        proc, pydm, _ = self.start()
        self.assertTrue(pydm.ready.wait(10))
        proc.stdin.close()
        self.assertEqual(proc.wait(10), 0)

    def test_attend_pydm_sans_le_lancer(self):
        """Ouvrir un navigateur n'est pas une demande de téléchargement : PyDM n'est pas lancé."""
        proc, _, cfg = self.start(with_pydm=False)
        lance = os.path.join(os.path.dirname(cfg), ".local", "bin")
        os.makedirs(lance)
        with open(os.path.join(lance, "pydm"), "w") as f:
            f.write("#!/bin/sh\ntouch %s\n" % os.path.join(cfg, "lance"))
        os.chmod(os.path.join(lance, "pydm"), 0o755)
        time.sleep(1.5)
        self.assertIsNone(proc.poll(), "l'hôte doit rester en vie en attendant PyDM")
        self.assertFalse(os.path.exists(os.path.join(cfg, "lance")))
        pydm = FakePyDM(os.path.join(cfg, "pydm.sock"))     # PyDM s'ouvre enfin
        self.addCleanup(pydm.close)
        self.assertTrue(pydm.ready.wait(20), "le pont doit se raccrocher tout seul")


@unittest.skipIf(os.name == "nt", "socket Unix (POSIX)")
class BridgeEndToEndTest(unittest.TestCase):
    """Le vrai PyDM, le vrai hôte natif, et le test dans le rôle de l'extension."""

    def test_pydm_interroge_l_extension(self):
        import importlib
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cfg = os.path.join(tmp.name, "cfg")
        with mock.patch.dict(os.environ, {"PYDM_CONFIG_DIR": cfg}):
            import pydm.ipc
            ipc = importlib.reload(pydm.ipc)
            self.addCleanup(lambda: importlib.reload(pydm.ipc))
            ipc.start_ipc(lambda msg: {"ok": True})
            proc = subprocess.Popen([sys.executable, HOST], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE,
                                    env=dict(os.environ, HOME=tmp.name, PYDM_CONFIG_DIR=cfg))
            self.addCleanup(proc.kill)
            proc.stdin.write(framed({"action": "bridge"}))
            proc.stdin.flush()

            out = {}
            def demander():
                try:
                    out["reply"] = ipc.request("refresh", url="https://a.fr/f", referer="https://a.fr/p",
                                               timeout=15)
                except Exception as e:  # noqa: BLE001
                    out["error"] = e
            end = time.time() + 10
            while not ipc._BRIDGES and time.time() < end:
                time.sleep(0.05)
            self.assertTrue(ipc._BRIDGES, "l'hôte natif n'a pas ouvert le pont")
            t = threading.Thread(target=demander, daemon=True)
            t.start()
            demande = read_framed(proc.stdout)
            self.assertEqual(demande["action"], "refresh")
            self.assertEqual(demande["url"], "https://a.fr/f")
            proc.stdin.write(framed({"id": demande["id"], "headers": {"Cookie": "SID=9"}}))
            proc.stdin.flush()
            t.join(15)
            self.assertIsNone(out.get("error"))
            self.assertEqual(out["reply"]["headers"], {"Cookie": "SID=9"})


@unittest.skipIf(os.name == "nt", "socket Unix (POSIX) ; même scénario sous Windows : e2e_windows.ps1")
class BridgeDownloadTest(unittest.TestCase):
    """Scénario complet : cookie périmé, refus du serveur, rattrapage par le pont."""

    def test_telechargement_rattrape_par_le_pont(self):
        import importlib
        from tests.httpserver import serve
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cfg = os.path.join(tmp.name, "cfg")
        with mock.patch.dict(os.environ, {"PYDM_CONFIG_DIR": cfg}):
            import pydm.ipc
            ipc = importlib.reload(pydm.ipc)        # recharge sur place : engine voit le même module
            self.addCleanup(lambda: importlib.reload(pydm.ipc))
            from pydm import fingerprint, netpolicy
            from pydm.engine import Download
            netpolicy.reset()
            fingerprint.reset()
            self.addCleanup(netpolicy.reset)
            self.addCleanup(fingerprint.reset)
            ipc.start_ipc(lambda msg: {"ok": True})

            proc = subprocess.Popen([sys.executable, HOST], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE,
                                    env=dict(os.environ, HOME=tmp.name, PYDM_CONFIG_DIR=cfg))
            self.addCleanup(proc.kill)
            proc.stdin.write(framed({"action": "bridge"}))
            proc.stdin.flush()
            end = time.time() + 10
            while not ipc._BRIDGES and time.time() < end:
                time.sleep(0.05)
            self.assertTrue(ipc._BRIDGES, "l'hôte natif n'a pas ouvert le pont")

            data = os.urandom(2 * 1024 * 1024)
            url, stop = serve(data, require_cookie="SID=2")
            self.addCleanup(stop)
            d = Download(url + "/protege.bin", tmp.name, parts=2,
                         headers={"Cookie": "SID=1", "Referer": url + "/page"})
            d.start()
            self.addCleanup(d.pause)

            demande = read_framed(proc.stdout)       # PyDM a été refusé : il réclame des en-têtes
            self.assertEqual(demande["action"], "refresh")
            self.assertEqual(demande["url"], url + "/protege.bin")
            proc.stdin.write(framed({"id": demande["id"], "headers": {"Cookie": "SID=2"}}))
            proc.stdin.flush()

            end = time.time() + 60
            while d.running and time.time() < end:
                time.sleep(0.1)
            self.assertEqual(d.status, "Terminé", d.error or d.status)
            with open(d.path, "rb") as f:
                self.assertEqual(f.read(), data)
