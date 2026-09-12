import unittest

from scripts.scan_secrets import scan_text


class SecretScanTests(unittest.TestCase):
    def test_detects_private_key_without_echoing_its_content(self):
        findings = scan_text("key.txt", "-----BEGIN PRIVATE KEY-----\nprivate material")  # nexus-secret-scan: allow
        self.assertEqual(findings[0]["type"], "private-key")
        self.assertNotIn("private material", str(findings))

    def test_detects_hard_coded_credential(self):
        findings = scan_text("config.py", 'DEPLOY_TOKEN="real-secret-value"\n')  # nexus-secret-scan: allow
        self.assertEqual(findings[0]["type"], "hard-coded-credential")
        self.assertEqual(findings[0]["name"], "DEPLOY_TOKEN")

    def test_allows_environment_variable_reference(self):
        findings = scan_text("compose.yml", "NEXUS_DEPLOY_TOKEN: ${NEXUS_DEPLOY_TOKEN}\n")
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
