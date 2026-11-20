import base64
import json
import time
import unittest

from pydm.signed import expiry_of, freshness


def jwt(exp):
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return "eyJhbGciOiJIUzI1NiJ9." + payload + ".c2lnbmF0dXJl"


class ExpiryTest(unittest.TestCase):
    def test_aws_sigv4(self):
        url = ("https://s3.exemple.fr/f.bin?X-Amz-Algorithm=AWS4-HMAC-SHA256"
               "&X-Amz-Date=20261120T100000Z&X-Amz-Expires=900&X-Amz-Signature=ab")
        self.assertEqual(expiry_of(url), 1795168800.0 + 900)

    def test_sigv4_sans_date_ignore_la_duree(self):
        self.assertIsNone(expiry_of("https://s3.exemple.fr/f.bin?X-Amz-Expires=900"))

    def test_cloudfront_expires(self):
        url = "https://d1.cloudfront.net/f.mp4?Expires=1764000000&Signature=x&Key-Pair-Id=K1"
        self.assertEqual(expiry_of(url), 1764000000.0)

    def test_cloudfront_policy(self):
        policy = json.dumps({"Statement": [{"Resource": "https://d1/f.mp4", "Condition": {
            "DateLessThan": {"AWS:EpochTime": 1764000123}}}]}).encode()
        enc = base64.b64encode(policy).decode().replace("+", "-").replace("=", "_").replace("/", "~")
        self.assertEqual(expiry_of("https://d1.cloudfront.net/f.mp4?Policy=" + enc), 1764000123.0)

    def test_akamai_token(self):
        url = "https://a.exemple.fr/v.m3u8?hdnts=st=1763000000~exp=1764000000~hmac=deadbeef"
        self.assertEqual(expiry_of(url), 1764000000.0)

    def test_jwt_en_parametre(self):
        self.assertEqual(expiry_of("https://a.fr/f.bin?token=" + jwt(1764000500)), 1764000500.0)

    def test_jwt_dans_le_chemin(self):
        self.assertEqual(expiry_of("https://a.fr/dl/%s/f.bin" % jwt(1764000600)), 1764000600.0)

    def test_epoch_en_millisecondes(self):
        self.assertEqual(expiry_of("https://a.fr/f.bin?expires=1764000000000"), 1764000000.0)

    def test_date_iso(self):
        self.assertEqual(expiry_of("https://a.fr/f.bin?valid_until=2026-11-20T10:00:00Z"), 1795168800.0)

    def test_sans_expiration(self):
        self.assertIsNone(expiry_of("https://a.fr/f.bin"))
        self.assertIsNone(expiry_of("https://a.fr/f.bin?id=42&name=a.b.c"))
        self.assertIsNone(expiry_of("pas-une-url"))

    def test_jwt_illisible_ignore(self):
        self.assertIsNone(expiry_of("https://a.fr/f.bin?token=aaa.bbb.ccc"))


class FreshnessTest(unittest.TestCase):
    def test_etats(self):
        now = time.time()
        self.assertEqual(freshness("https://a.fr/f.bin")[0], "unknown")
        self.assertEqual(freshness("https://a.fr/f?expires=%d" % int(now - 10))[0], "expired")
        self.assertEqual(freshness("https://a.fr/f?expires=%d" % int(now + 30))[0], "soon")
        self.assertEqual(freshness("https://a.fr/f?expires=%d" % int(now + 3600))[0], "ok")

    def test_marge_reglable(self):
        soon = "https://a.fr/f?expires=%d" % int(time.time() + 300)
        self.assertEqual(freshness(soon)[0], "ok")
        self.assertEqual(freshness(soon, margin=600)[0], "soon")
        state, left = freshness(soon)
        self.assertAlmostEqual(left, 300, delta=5)


if __name__ == "__main__":
    unittest.main()
