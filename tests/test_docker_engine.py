import unittest
from unittest.mock import patch

from src import docker_engine as engine


class FakeImage:
    def __init__(self):
        self.tags = []

    def tag(self, **kwargs):
        self.tags.append(kwargs)
        return True


class FakeCandidate:
    short_id = "candidate123"

    def __init__(self):
        self.removed = False

    def remove(self, force=False):
        self.removed = force


class FakePrevious:
    short_id = "previous123"

    def __init__(self):
        self.removed = False

    def remove(self, force=False):
        self.removed = force


class FakeImages:
    def __init__(self, image):
        self.image = image

    def build(self, **_kwargs):
        return self.image, []


class FakeContainers:
    def __init__(self, candidate):
        self.candidate = candidate

    def run(self, **_kwargs):
        return self.candidate


class FakeClient:
    def __init__(self, image, candidate):
        self.images = FakeImages(image)
        self.containers = FakeContainers(candidate)


class DeploymentRollbackTests(unittest.TestCase):
    def setUp(self):
        self.original_client = engine.client
        self.image = FakeImage()
        self.candidate = FakeCandidate()
        self.previous = FakePrevious()
        engine.client = FakeClient(self.image, self.candidate)

    def tearDown(self):
        engine.client = self.original_client

    def test_failed_health_check_removes_candidate_and_restores_previous_release(self):
        with (
            patch.object(engine, "get_nexus_network"),
            patch.object(engine, "scan_image", return_value={"enabled": True, "findings": 0}),
            patch.object(engine, "register_or_update_app"),
            patch.object(engine, "log_deployment"),
            patch.object(
                engine,
                "move_current_container_to_rollback_slot",
                return_value=self.previous,
            ),
            patch.object(
                engine,
                "wait_for_healthcheck",
                return_value=(False, "health endpoint unavailable"),
            ),
            patch.object(
                engine,
                "restore_rollback_container",
                return_value=self.previous.short_id,
            ) as restore,
            patch.object(engine, "get_container_or_none", return_value=self.previous),
        ):
            result = engine.build_and_deploy_app(
                app_name="sample-app",
                app_dir="/unused",
                commit_hash="a" * 40,
            )

        self.assertEqual(result["status"], "error")
        self.assertTrue(self.candidate.removed)
        restore.assert_called_once_with(self.previous, "nexus-app-sample-app")
        self.assertEqual(result["rollback_container_id"], self.previous.short_id)

    def test_healthy_candidate_is_promoted_and_previous_release_is_removed(self):
        with (
            patch.object(engine, "get_nexus_network"),
            patch.object(engine, "scan_image", return_value={"enabled": True, "findings": 0}),
            patch.object(engine, "register_or_update_app"),
            patch.object(engine, "log_deployment"),
            patch.object(
                engine,
                "move_current_container_to_rollback_slot",
                return_value=self.previous,
            ),
            patch.object(engine, "wait_for_healthcheck", return_value=(True, "ok")),
        ):
            result = engine.build_and_deploy_app(
                app_name="sample-app",
                app_dir="/unused",
                commit_hash="b" * 40,
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["container_id"], self.candidate.short_id)
        self.assertTrue(self.previous.removed)
        self.assertEqual(
            self.image.tags,
            [{"repository": "nexus-sample-app", "tag": "latest", "force": True}],
        )


if __name__ == "__main__":
    unittest.main()
