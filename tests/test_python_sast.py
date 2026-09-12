import tempfile
import unittest
from pathlib import Path

from scripts.scan_python_security import scan


class PythonSastTests(unittest.TestCase):
    def test_detects_eval(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / "bad.py").write_text("eval('1 + 1')" + chr(10))
            findings = scan(target)
        self.assertEqual(findings[0]["rule"], "dangerous-dynamic-execution")

    def test_allows_safe_code(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / "safe.py").write_text("print('safe')" + chr(10))
            self.assertEqual(scan(target), [])


if __name__ == "__main__":
    unittest.main()
