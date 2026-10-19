import os
import tempfile
import time
import unittest

from pydm.engine import Download
from tests.httpserver import serve


def wait(task, timeout=20):
    end = time.time() + timeout
    while task.running and time.time() < end:
        time.sleep(0.05)


class DownloadTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.data = os.urandom(8 * 1024 * 1024)   # 4 segments : MIN_SPLIT vaut 2 Mo

    def start_server(self, **kw):
        url, stop = serve(self.data, **kw)
        self.addCleanup(stop)
        return url + "/fichier.bin"

    def read(self, d):
        with open(d.path, "rb") as f:
            return f.read()

    def test_download_multi_connexions(self):
        d = Download(self.start_server(), self.dir, parts=4)
        d.start()
        wait(d)
        self.assertEqual(d.status, "Terminé")
        self.assertEqual(self.read(d), self.data)
        self.assertGreaterEqual(len(d.segments), 2)

    def test_pause_puis_reprise(self):
        url = self.start_server(delay=0.02)
        d = Download(url, self.dir, parts=4)
        d.start()
        end = time.time() + 20
        while d.done <= 512 * 1024 and time.time() < end:
            time.sleep(0.02)
        d.pause()
        d.wait()
        self.assertEqual(d.status, "En pause")
        d2 = Download(url, self.dir, 4, name=d.name)
        self.assertEqual(d2.status, "En pause")
        d2.start()
        wait(d2, 60)
        self.assertEqual(d2.status, "Terminé")
        self.assertEqual(self.read(d2), self.data)

    def test_proprietes_detail(self):
        d = Download(self.start_server(), self.dir, parts=4)
        self.assertEqual(d.active_connections, 0)
        d.start()
        wait(d)
        self.assertTrue(d.resumable)
        self.assertEqual(d.active_connections, 0)
        self.assertEqual(d.files(), [d.path])

    def test_serveur_sans_plages(self):
        d = Download(self.start_server(ranges=False), self.dir, parts=4)
        d.start()
        wait(d)
        self.assertIs(d.ranges, False)
        self.assertEqual(d.status, "Terminé")
        self.assertEqual(self.read(d), self.data)

    @unittest.skipIf(os.geteuid() == 0, "root peut écrire partout")
    def test_dossier_non_inscriptible(self):
        folder = os.path.join(self.dir, "lecture-seule")
        os.mkdir(folder, 0o500)
        self.addCleanup(os.chmod, folder, 0o700)
        d = Download(self.start_server(), folder, parts=4)
        d.start()
        wait(d)
        self.assertTrue(d.status.startswith("Erreur"), d.status)
        self.assertFalse(d.running)

    def test_nom_unicode_content_disposition(self):
        cd = "attachment; filename*=UTF-8''r%C3%A9sum%C3%A9 %C3%A9t%C3%A9.pdf"
        d = Download(self.start_server(headers={"Content-Disposition": cd}), self.dir, parts=2)
        d.start()
        wait(d)
        self.assertEqual(d.name, "résumé été.pdf")


if __name__ == "__main__":
    unittest.main()
