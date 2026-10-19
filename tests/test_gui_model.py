import time
import unittest

from tests.qt import HAS_QT, app


class FakeTask:
    def __init__(self, name="a.bin", size=None, done=0, speed=0.0, running=False,
                 status="En pause", error=None, url=None):
        self.name, self.size, self.done, self.speed = name, size, done, speed
        self.running, self.status, self.error = running, status, error
        self.url = url or f"https://exemple.fr/{name}"
        self.added = time.time()

    @property
    def finished(self):
        return self.status == "Terminé"


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class ModelTest(unittest.TestCase):
    def setUp(self):
        app()
        from PySide6.QtCore import Qt
        from pydm.gui import model
        self.Qt, self.m = Qt, model
        self.model = model.DownloadModel()

    def text(self, row, col):
        return self.model.data(self.model.index(row, col))

    def progress(self, row):
        return self.model.data(self.model.index(row, 2), self.m.PROGRESS_ROLE)

    def test_lignes_et_valeurs(self):
        self.model.add(FakeTask("x.iso", size=2 * 1024 ** 3, done=1024 ** 3, speed=1048576, running=True,
                                status="Téléchargement"))
        self.model.add(FakeTask("y.zip"))
        self.assertEqual(self.model.rowCount(), 2)
        self.assertEqual(self.model.columnCount(), 7)
        self.assertEqual(self.text(0, 1), "2.0 Go")
        self.assertEqual(self.progress(0), (0.5, "active"))
        self.assertEqual(self.text(0, 3), "1.0 Mo/s")
        self.assertEqual(self.text(0, 4), "17m04s")

    def test_taille_inconnue_ou_nulle(self):
        self.model.add(FakeTask("flux", size=None, done=5000, running=True, status="Téléchargement"))
        self.model.add(FakeTask("vide", size=0, done=0, running=True, speed=10.0, status="Téléchargement"))
        self.assertEqual(self.text(0, 1), "?")
        self.assertEqual(self.progress(0), (None, "active"))
        self.assertEqual(self.text(0, 4), "")
        self.assertEqual(self.progress(1)[0], None)
        self.assertEqual(self.text(1, 4), "")

    def test_tri(self):
        for size in (2000, None, 3 * 10 ** 9, 10):
            self.model.add(FakeTask(f"f{size}", size=size))
        proxy = self.m.DownloadFilter()
        proxy.setSourceModel(self.model)
        proxy.sort(1, self.Qt.AscendingOrder)
        sizes = [self.model.task(proxy.mapToSource(proxy.index(r, 0)).row()).size for r in range(4)]
        self.assertEqual(sizes, [None, 10, 2000, 3 * 10 ** 9])

    def test_recherche(self):
        self.model.add(FakeTask("pop-os.iso"))
        self.model.add(FakeTask("a.bin", url="https://x.fr/iso/a.bin"))
        self.model.add(FakeTask("film.mkv"))
        proxy = self.m.DownloadFilter()
        proxy.setSourceModel(self.model)
        proxy.set_search("ISO")
        names = sorted(proxy.data(proxy.index(r, 0)) for r in range(proxy.rowCount()))
        self.assertEqual(names, ["a.bin", "pop-os.iso"])

    def test_refresh_emet_datachanged(self):
        t = FakeTask("a", size=100, done=10, running=True, status="Téléchargement")
        self.model.add(t)
        self.model.add(FakeTask("b", size=100))
        rows = []
        self.model.dataChanged.connect(lambda tl, br, *_: rows.append((tl.row(), br.row())))
        self.model.refresh()
        rows.clear()
        t.done = 20
        self.model.refresh()
        self.assertEqual(rows, [(0, 0)])
        rows.clear()
        self.model.refresh()
        self.assertEqual(rows, [])

    def test_remplacer(self):
        old, new = FakeTask("analyse"), FakeTask("vrai.iso", size=10)
        self.model.add(FakeTask("autre"))
        self.model.add(old)
        rows = []
        self.model.dataChanged.connect(lambda tl, br, *_: rows.append(tl.row()))
        self.model.replace(old, new)
        self.assertEqual(self.model.rowCount(), 2)
        self.assertIs(self.model.task(1), new)
        self.assertEqual(rows, [1])

    def test_couleur_erreur(self):
        from PySide6.QtGui import QColor
        self.model.add(FakeTask("a", error="refus", status="Erreur : refus"))
        fg = self.model.data(self.model.index(0, 5), self.Qt.ForegroundRole)
        self.assertEqual(QColor(fg), QColor("#ef4444"))
        self.assertEqual(self.progress(0)[1], "error")


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class ProgressDelegateTest(unittest.TestCase):
    def render(self, task):
        from PySide6.QtCore import QRect
        from PySide6.QtGui import QColor, QImage, QPainter
        from PySide6.QtWidgets import QStyleOptionViewItem
        from pydm.gui import delegates, model, theme
        app()
        m = model.DownloadModel()
        m.add(task)
        img = QImage(200, 24, QImage.Format_ARGB32)
        img.fill(QColor("#ffffff"))
        opt = QStyleOptionViewItem()
        opt.rect = QRect(0, 0, 200, 24)
        p = QPainter(img)
        delegates.ProgressDelegate().paint(p, opt, m.index(0, 2))
        p.end()
        return img, theme

    def test_barre_a_moitie(self):
        img, theme = self.render(FakeTask(size=100, done=50, running=True, status="Téléchargement"))
        y = 12
        xs = [x for x in range(200) if img.pixelColor(x, y).name() == theme.accent().name()]
        self.assertTrue(xs, "aucune portion de barre à la couleur d'accent")
        self.assertLess(max(xs) - min(xs), 100)       # la moitié de la barre, pas toute la cellule

    def test_taille_inconnue_sans_barre(self):
        img, theme = self.render(FakeTask(size=None, done=5000, running=True, status="Téléchargement"))
        accent = theme.accent().name()
        self.assertFalse(any(img.pixelColor(x, 12).name() == accent for x in range(200)))


if __name__ == "__main__":
    unittest.main()
