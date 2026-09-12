import unittest

from src.release import can_promote, deployment_app_name


class ReleasePolicyTests(unittest.TestCase):
    def test_only_sequential_promotions_allowed(self):
        self.assertTrue(can_promote("dev", "staging"))
        self.assertTrue(can_promote("staging", "production"))
        self.assertFalse(can_promote("dev", "production"))
        self.assertFalse(can_promote("production", "dev"))

    def test_environment_has_distinct_app_names(self):
        self.assertEqual(deployment_app_name("dev"), "sample-app-dev")
        self.assertEqual(deployment_app_name("staging"), "sample-app-staging")
        self.assertEqual(deployment_app_name("production"), "sample-app")


if __name__ == "__main__":
    unittest.main()
