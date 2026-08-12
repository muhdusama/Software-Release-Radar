from __future__ import annotations

import unittest
from pathlib import Path


class WorkerHealthcheckTests(unittest.TestCase):
    def test_non_web_services_disable_image_http_healthcheck(self):
        compose = (Path(__file__).parents[1] / "docker-compose.yml").read_text()

        scheduler = compose.split("  scheduler:\n", 1)[1].split("\n  portainer-worker:\n", 1)[0]
        worker = compose.split("  portainer-worker:\n", 1)[1].split("\nvolumes:\n", 1)[0]

        for service in (scheduler, worker):
            self.assertIn("healthcheck:\n      disable: true", service)
            self.assertNotIn("http://127.0.0.1:8080/healthz", service)


if __name__ == "__main__":
    unittest.main()
