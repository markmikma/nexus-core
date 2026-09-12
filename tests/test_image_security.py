import json
import unittest

from src import image_security


class FakeContainers:
    def __init__(self, report):
        self.report = report
        self.kwargs = None

    def run(self, **kwargs):
        self.kwargs = kwargs
        return json.dumps(self.report).encode("utf-8")


class FakeClient:
    def __init__(self, report):
        self.containers = FakeContainers(report)


class ImageSecurityTests(unittest.TestCase):
    def test_passes_when_trivy_returns_no_policy_findings(self):
        client = FakeClient({"Results": []})
        summary = image_security.scan_image(client, "nexus-sample-app:candidate")

        self.assertEqual(summary["findings"], 0)
        self.assertEqual(client.containers.kwargs["image"], "aquasec/trivy:0.57.1")
        self.assertIn("--ignore-unfixed", client.containers.kwargs["command"])

    def test_blocks_when_trivy_returns_a_policy_finding(self):
        client = FakeClient({"Results": [{"Vulnerabilities": [{
            "PkgName": "openssl",
            "VulnerabilityID": "CVE-2099-0001",
        }]}]})
        with self.assertRaisesRegex(RuntimeError, "CVE-2099-0001"):
            image_security.scan_image(client, "nexus-sample-app:candidate")


if __name__ == "__main__":
    unittest.main()
