import json
import os
import re
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CASES = {
    "https://www.youtube.com/watch?v=abc&list=x": True,
    "https://www.youtube.com/": False,
    "https://www.youtube.com/results?search_query=a": False,
    "https://youtube.com/shorts/xyz": True,
    "https://www.youtube.com/live/xyz": True,
    "https://youtu.be/abc": True,
    "https://vimeo.com/123456": True,
    "https://vimeo.com/channels/staffpicks": False,
    "https://www.dailymotion.com/video/x8abc": True,
    "https://www.reddit.com/r/videos/": False,
    "https://www.reddit.com/r/videos/comments/abc/titre/": True,
    "https://x.com/home": False,
    "https://x.com/user/status/123": True,
    "https://www.instagram.com/someone/": False,
    "https://www.instagram.com/reel/abc/": True,
    "https://www.facebook.com/someone": False,
    "https://www.facebook.com/watch/?v=1": True,
    "https://www.tiktok.com/@user/video/123": True,
    "https://www.tiktok.com/@user": False,
    "https://example.com/video.mp4": False,
}


@unittest.skipUnless(shutil.which("node"), "node absent")
class VideoPageTest(unittest.TestCase):
    def test_pages_video(self):
        src = open(os.path.join(ROOT, "extension", "background.js")).read()
        code = re.search(r"^const VIDEO_PATHS = .*?^function isVideoPage\(url\) \{.*?^\}", src, re.M | re.S).group(0)
        script = f"{code}\nconst cases = {json.dumps(CASES)};\n" \
                 "console.log(JSON.stringify(Object.fromEntries(Object.keys(cases).map(u => [u, isVideoPage(u)]))));"
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        got = json.loads(out.stdout)
        wrong = {u: got[u] for u in CASES if got[u] != CASES[u]}
        self.assertEqual(wrong, {})


if __name__ == "__main__":
    unittest.main()
