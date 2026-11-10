"""Icônes d'action et illustrations : dessins à deux tons (repères) et accent fixe propre à chacun."""
import os
import re
import unittest
import xml.etree.ElementTree as ET

from tests.qt import HAS_QT, app

ICONS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pydm", "gui", "icons")
ACCENTS = {"add": "#06b6d4", "resume": "#22c55e", "pause": "#f59e0b", "force": "#8b5cf6", "remove": "#ef4444",
           "folder": "#f59e0b", "schedule": "#8b5cf6", "search": "#06b6d4", "menu": "#64748b"}


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class ActionIconsTest(unittest.TestCase):
    def setUp(self):
        app()

    def test_icones_d_action(self):
        from PySide6.QtSvg import QSvgRenderer
        for name, accent in ACCENTS.items():
            with self.subTest(name=name):
                path = os.path.join(ICONS, name + ".svg")
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                drawing = re.sub(r"<!--.*?-->", "", text, flags=re.S)
                self.assertTrue("#010101" in drawing or "#fefefe" in drawing)        # tons du thème
                self.assertNotIn("currentColor", text)
                self.assertIn(accent, text)
                self.assertEqual(ET.fromstring(text).get("viewBox"), "0 0 32 32")
                self.assertTrue(QSvgRenderer(path).isValid())


if __name__ == "__main__":
    unittest.main()
