import os
import tempfile
import threading
import time
import unittest
from unittest import mock

from tests.qt import HAS_QT, app


def choice(label, fmt, ext, height=None, audio=False):
    return dict(label=label, format=fmt, ext=ext, size=None, approx=False, height=height, audio_only=audio)


CHOICES = [choice("1080p · MP4 · 392.9 Mo", "137+140", "mp4", 1080),
           choice("720p · MP4", "136+140", "mp4", 720),
           choice("Audio seul · MP3", "ba/b", "mp3", audio=True)]


def result(**kw):
    r = dict(kind="video", name="Conférence.mp4", size=None, resumable=True, site="youtube.com",
             title="Conférence", duration=2538, thumbnail=None, choices=CHOICES, selected=1,
             ffmpeg_missing=False, error=None, drm=False)
    r.update(kw)
    return r


class DialogCase(unittest.TestCase):
    def setUp(self):
        app()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cfg = tmp.name
        for name in ("CONFIG_DIR", "SOCKET_PATH"):
            p = mock.patch(f"pydm.ipc.{name}", f"{self.cfg}/x" if name == "SOCKET_PATH" else self.cfg)
            p.start()
            self.addCleanup(p.stop)
        from pydm import store
        from pydm.gui.adddialog import AddDialog
        p = mock.patch("pydm.gui.adddialog.fetch_youtube_thumbnail", return_value=None)   # pas de réseau
        p.start()
        self.addCleanup(p.stop)
        self.store, self.AddDialog = store, AddDialog
        self.settings = dict(store.DEFAULTS, folder=self.cfg)
        self.emitted = []

    def dialog(self, res=None, urls=("https://www.youtube.com/watch?v=x",), analyzer=None):
        dlg = self.AddDialog(self.settings, list(urls), analyzer=analyzer or (lambda *a, **k: res))
        dlg.accepted_tasks.connect(lambda tasks, start: self.emitted.append((tasks, start)))
        self.addCleanup(dlg.deleteLater)
        dlg.show()
        return dlg

    def wait_filled(self, dlg, timeout=2.0):
        end = time.time() + timeout
        while time.time() < end:
            dlg.poll()
            if dlg.done_count() == len(dlg.urls):
                return
            time.sleep(0.01)
        self.fail("analyse non reçue")


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class AddDialogTest(DialogCase):
    def test_video_remplie(self):
        dlg = self.dialog(result())
        self.wait_filled(dlg)
        self.assertEqual(dlg.quality_box.count(), 3)
        self.assertEqual(dlg.quality_box.currentIndex(), 1)
        self.assertEqual(dlg.name_edit.text(), "Conférence.mp4")
        self.assertIn("youtube.com", dlg.info_label.text())
        self.assertEqual(dlg.windowTitle(), "Ajouter une vidéo")

    def test_telecharger(self):
        dlg = self.dialog(result())
        self.wait_filled(dlg)
        dlg.quality_box.setCurrentIndex(0)
        dlg.download_btn.click()
        self.assertEqual(len(self.emitted), 1)
        tasks, start = self.emitted[0]
        self.assertIs(start, True)
        self.assertEqual((tasks[0]["fmt"], tasks[0]["kind"], tasks[0]["folder"]),
                         ("137+140", "video", os.path.join(self.cfg, "Vidéos")))      # rangé par type

    def test_plus_tard(self):
        dlg = self.dialog(result())
        self.wait_filled(dlg)
        dlg.later_btn.click()
        self.assertIs(self.emitted[0][1], False)

    def test_annuler(self):
        dlg = self.dialog(result())
        self.wait_filled(dlg)
        dlg.reject()
        self.assertEqual(self.emitted, [])

    def test_extension_suit_la_qualite(self):
        dlg = self.dialog(result())
        self.wait_filled(dlg)
        dlg.quality_box.setCurrentIndex(2)
        self.assertTrue(dlg.name_edit.text().endswith(".mp3"))
        self.assertEqual(self.dialog_task(dlg)["quality"], "Audio MP3")
        dlg.name_edit.setText("perso.mp4")
        dlg.name_edit.setModified(True)
        dlg.quality_box.setCurrentIndex(0)
        self.assertEqual(dlg.name_edit.text(), "perso.mp4")

    def dialog_task(self, dlg):
        return dlg.collect()[0]

    def test_nom_vide(self):
        dlg = self.dialog(result())
        self.wait_filled(dlg)
        dlg.name_edit.setText("   ")
        dlg.download_btn.click()
        self.assertEqual(self.emitted[0][0][0]["name"], "Conférence.mp4")

    def test_ne_plus_demander(self):
        dlg = self.dialog(result())
        self.wait_filled(dlg)
        dlg.never_box.setChecked(True)
        dlg.download_btn.click()
        self.assertIs(self.settings["confirm_add"], False)
        self.assertIs(self.store.load_settings(self.cfg)["confirm_add"], False)

    def test_erreur(self):
        dlg = self.dialog(result(kind="error", error="HTTP Error 403: Forbidden", choices=[], name=None))
        self.wait_filled(dlg)
        self.assertIn("403", dlg.info_label.text())
        self.assertEqual(dlg.download_btn.text(), "Télécharger quand même")
        dlg.download_btn.click()
        self.assertIsNone(self.emitted[0][0][0]["fmt"])
        self.assertEqual(self.emitted[0][0][0]["kind"], "auto")

    def test_drm(self):
        dlg = self.dialog(result(kind="error", error="contenu protégé", drm=True, choices=[]))
        self.wait_filled(dlg)
        self.assertFalse(dlg.download_btn.isEnabled())

    def test_resultat_apres_fermeture(self):
        gate = threading.Event()

        def slow(*a, **k):
            gate.wait(2)
            return result()
        dlg = self.dialog(analyzer=slow)
        dlg.reject()
        gate.set()
        time.sleep(0.1)
        dlg.poll()
        self.assertEqual(self.emitted, [])

    def test_fichier(self):
        dlg = self.dialog(result(kind="file", name="blender.tar.xz", size=389 * 2 ** 20, choices=[],
                                 site="download.blender.org"), urls=["https://download.blender.org/b.tar.xz"])
        self.wait_filled(dlg)
        self.assertFalse(dlg.quality_box.isVisible())
        self.assertEqual(dlg.windowTitle(), "Ajouter un téléchargement")
        self.assertIn("reprise possible", dlg.info_label.text())
        dlg.download_btn.click()
        self.assertEqual(self.emitted[0][0][0]["kind"], "file")
        self.assertEqual(self.emitted[0][0][0]["name"], "blender.tar.xz")


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class BatchTest(DialogCase):
    URLS = ["https://a.fr/v1", "https://a.fr/f.zip", "https://a.fr/v2"]

    def batch(self, results=None):
        results = results or {
            self.URLS[0]: result(name="Vidéo 1.mp4"),
            self.URLS[1]: result(kind="file", name="f.zip", size=2048, choices=[]),
            self.URLS[2]: result(name="Vidéo 2.mp4")}
        dlg = self.dialog(urls=self.URLS, analyzer=lambda url, *a, **k: results[url])
        self.wait_filled(dlg)
        return dlg

    def uncheck(self, dlg, row):
        from PySide6.QtCore import Qt
        dlg.table.item(row, 0).setCheckState(Qt.Unchecked)

    def test_lot_trois_liens(self):
        dlg = self.batch()
        self.assertEqual(dlg.table.rowCount(), 3)
        self.assertEqual(dlg.download_btn.text(), "Télécharger 3")
        self.assertEqual(dlg.windowTitle(), "Ajouter 3 téléchargements")
        self.assertEqual(dlg.table.item(1, 1).text(), "f.zip")

    def test_lot_decocher(self):
        dlg = self.batch()
        self.uncheck(dlg, 1)
        self.assertEqual(dlg.download_btn.text(), "Télécharger 2")
        dlg.download_btn.click()
        tasks = self.emitted[0][0]
        self.assertEqual([t["url"] for t in tasks], [self.URLS[0], self.URLS[2]])

    def test_lot_qualite_commune(self):
        dlg = self.batch()
        dlg.videos_box.setCurrentText("720p")
        dlg.download_btn.click()
        videos = [t for t in self.emitted[0][0] if t["kind"] == "video"]
        self.assertEqual([(t["quality"], t["fmt"]) for t in videos], [("720p", None), ("720p", None)])

    def test_lot_erreur_decochee(self):
        from PySide6.QtCore import Qt
        dlg = self.batch({self.URLS[0]: result(), self.URLS[1]: result(kind="error", error="HTTP Error 404",
                                                                         choices=[], name=None),
                          self.URLS[2]: result()})
        self.assertEqual(dlg.table.item(1, 0).checkState(), Qt.Unchecked)
        self.assertIn("404", dlg.table.item(1, 1).toolTip())
        self.assertEqual(dlg.download_btn.text(), "Télécharger 2")

    def test_lot_tout_decoche(self):
        dlg = self.batch()
        for row in range(3):
            self.uncheck(dlg, row)
        self.assertFalse(dlg.download_btn.isEnabled())


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class AddDialogFixesTest(DialogCase):
    def test_video_choisie_malgre_defaut_mp3(self):
        self.settings["quality"] = "Audio MP3"
        dlg = self.dialog(result())
        self.wait_filled(dlg)
        dlg.quality_box.setCurrentIndex(1)
        task = dlg.collect()[0]
        self.assertEqual(task["fmt"], "136+140")
        self.assertNotEqual(task["quality"], "Audio MP3")

    def test_dossier_inutilisable_garde_la_fenetre(self):
        from PySide6.QtWidgets import QMessageBox
        dlg = self.dialog(result())
        self.wait_filled(dlg)
        dlg.folder_edit.setText("/proc/pydm-impossible")
        dlg.never_box.setChecked(True)
        with mock.patch.object(QMessageBox, "warning") as warn:
            dlg.download_btn.click()
        self.assertTrue(warn.called)
        self.assertEqual(self.emitted, [])
        self.assertTrue(dlg.isVisible())
        self.assertIs(self.settings["confirm_add"], True)


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class SortDialogTest(DialogCase):
    def j(self, *p):
        return os.path.join(self.cfg, *p)

    def test_dossier_video_puis_musique(self):
        dlg = self.dialog(result())
        self.wait_filled(dlg)
        self.assertEqual(dlg.folder_edit.text(), self.j("Vidéos"))
        dlg.quality_box.setCurrentIndex(2)          # Audio seul · MP3
        self.assertEqual(dlg.folder_edit.text(), self.j("Musique"))
        dlg.quality_box.setCurrentIndex(0)
        self.assertEqual(dlg.folder_edit.text(), self.j("Vidéos"))

    def test_dossier_modifie_conserve(self):
        dlg = self.dialog(result())
        self.wait_filled(dlg)
        dlg.folder_edit.setText("/tmp/ailleurs")
        dlg.folder_edit.setModified(True)
        dlg.quality_box.setCurrentIndex(2)
        self.assertEqual(dlg.folder_edit.text(), "/tmp/ailleurs")

    def test_fichier_document(self):
        dlg = self.dialog(result(kind="file", name="rapport.pdf", choices=[]), urls=["https://a.fr/r"])
        self.wait_filled(dlg)
        self.assertEqual(dlg.folder_edit.text(), self.j("Documents"))

    def test_rangement_desactive(self):
        self.settings["sort_by_type"] = False
        dlg = self.dialog(result())
        self.wait_filled(dlg)
        self.assertEqual(dlg.folder_edit.text(), self.cfg)

    def test_erreur_dossier_auto(self):
        dlg = self.dialog(result(kind="error", error="x", choices=[], name=None))
        self.wait_filled(dlg)
        task = dlg.collect()[0]
        self.assertEqual(task["folder"], self.cfg)
        self.assertIs(task["auto_folder"], True)

    def test_lot_dossiers_par_categorie(self):
        urls = ["https://a.fr/v", "https://a.fr/a.zip", "https://a.fr/p"]
        res = {urls[0]: result(), urls[1]: result(kind="file", name="a.zip", choices=[]),
               urls[2]: result(kind="error", error="x", choices=[], name=None)}
        dlg = self.dialog(urls=urls, analyzer=lambda u, *a, **k: res[u])
        self.wait_filled(dlg)
        from PySide6.QtCore import Qt
        dlg.table.item(2, 0).setCheckState(Qt.Checked)
        tasks = {t["url"]: t for t in dlg.collect()}
        self.assertEqual(tasks[urls[0]]["folder"], self.j("Vidéos"))
        self.assertEqual(tasks[urls[1]]["folder"], self.j("Archives"))
        self.assertEqual((tasks[urls[2]]["folder"], tasks[urls[2]]["auto_folder"]), (self.cfg, True))
        dlg.videos_box.setCurrentText("Audio MP3")
        dlg.folder_edit.setText("/srv/dl")
        self.assertEqual(dlg.collect()[0]["folder"], "/srv/dl/Musique")
        self.assertEqual(dlg.folder_label.text(), "Dossier principal")


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class ThumbnailTest(DialogCase):
    def test_miniature_youtube_immediate(self):
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from PySide6.QtGui import QColor, QImage
        img = QImage(320, 180, QImage.Format_RGB32)
        img.fill(QColor("#336699"))
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        asked = []
        gate = threading.Event()
        self.addCleanup(gate.set)
        dlg = self.AddDialog(self.settings, ["https://www.youtube.com/watch?v=abc"],
                             analyzer=lambda *a, **k: gate.wait(5) and result(),
                             thumb_fetcher=lambda vid: asked.append(vid) or bytes(data))
        self.addCleanup(dlg.deleteLater)
        end = time.time() + 2
        while dlg.thumb.pixmap().width() != 128 and time.time() < end:
            dlg.poll()
            time.sleep(0.01)
        self.assertEqual(asked, ["abc"])
        self.assertEqual(dlg.thumb.pixmap().width(), 128)


if __name__ == "__main__":
    unittest.main()
