"""Imitation minimale de winreg pour tester l'intégration Windows sous Linux."""


class _Handle:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def Close(self):
        pass


class FakeReg:
    HKEY_CURRENT_USER = _Handle("HKCU")
    REG_SZ = 1
    KEY_READ = 0x20019
    KEY_SET_VALUE = 0x2
    KEY_ALL_ACCESS = 0xF003F

    def __init__(self):
        self.keys = {}          # chemin complet (minuscules) -> {nom de valeur: texte}

    @staticmethod
    def _join(key, sub):
        return f"{key.path}\\{sub}".lower() if sub else key.path.lower()

    def CreateKey(self, key, sub):
        path = self._join(key, sub)
        parts = path.split("\\")
        for i in range(2, len(parts) + 1):
            self.keys.setdefault("\\".join(parts[:i]), {})
        return _Handle(path)

    def OpenKey(self, key, sub, reserved=0, access=KEY_READ):
        path = self._join(key, sub)
        if path not in self.keys:
            raise FileNotFoundError(2, "clé absente", sub)
        return _Handle(path)

    def SetValue(self, key, sub, kind, value):
        self.keys[self.CreateKey(key, sub).path][""] = value

    def QueryValue(self, key, sub):
        values = self.keys.get(self._join(key, sub))
        if values is None or "" not in values:
            raise FileNotFoundError(2, "valeur absente", sub)
        return values[""]

    def SetValueEx(self, key, name, reserved, kind, value):
        self.keys[key.path][name] = value

    def QueryValueEx(self, key, name):
        try:
            return self.keys[key.path][name], self.REG_SZ
        except KeyError:
            raise FileNotFoundError(2, "valeur absente", name) from None

    def DeleteValue(self, key, name):
        try:
            del self.keys[key.path][name]
        except KeyError:
            raise FileNotFoundError(2, "valeur absente", name) from None

    def DeleteKey(self, key, sub):
        path = self._join(key, sub)
        if path not in self.keys:
            raise FileNotFoundError(2, "clé absente", sub)
        if any(k.startswith(path + "\\") for k in self.keys):
            raise PermissionError(5, "sous-clés présentes", sub)
        del self.keys[path]

    def CloseKey(self, key):
        pass

    def value(self, sub):
        """Valeur par défaut d'une clé, ou None (pour les assertions)."""
        return self.keys.get(f"hkcu\\{sub}".lower(), {}).get("")
