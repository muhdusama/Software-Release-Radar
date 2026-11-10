"""Keep the runtime candidate's CI coverage and existing protection contexts explicit.

These checks intentionally inspect the small, repository-owned workflow rather
than adding a YAML parser dependency to the application.
"""
from pathlib import Path
import json
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CIRuntimeCoverageTests(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / '.github/workflows/ci.yml').read_text()

    def job(self, name):
        match = re.search(r'^  ' + re.escape(name) + r':\n(.*?)(?=^  [a-z][a-z0-9-]*:|\Z)',
                          self.workflow, re.MULTILINE | re.DOTALL)
        assert match is not None, name
        return match.group(1)

    def test_full_unittest_matrix_includes_supported_and_candidate_runtimes(self):
        job = self.job('python-tests')
        matrix = re.search(r'python-version: (\[[^\n]+\])', job)
        assert matrix is not None
        self.assertEqual(json.loads(matrix.group(1)), ['3.13', '3.15'])
        self.assertIn('name: Python ${{ matrix.python-version }} tests', job)
        self.assertIn('python-version: ${{ matrix.python-version }}', job)
        self.assertIn('fail-fast: false', job)
        self.assertIn('fetch-depth: 0', job)
        self.assertIn('python -m unittest discover -s tests -v', job)
        self.assertNotIn('continue-on-error', job)

    def test_security_matrix_retains_existing_required_context(self):
        job = self.job('security-audit')
        entries = re.findall(r'- python-version: "([^"]+)"\n\s+check-name: ([^\n]+)', job)
        self.assertEqual(entries, [
            ('3.13', 'Dependency and Python security audit'),
            ('3.15', 'Dependency and Python 3.15 security audit'),
        ])
        self.assertIn('name: ${{ matrix.check-name }}', job)
        self.assertIn('python-version: ${{ matrix.python-version }}', job)
        self.assertIn('python -m pip_audit -r requirements.txt', job)
        self.assertIn('python scripts/check_bandit.py /tmp/bandit.json', job)
        self.assertIn('test "$scan_exit" -le 1', job)
        self.assertNotIn('continue-on-error', job)

    def test_public_container_acceptance_and_read_only_permissions_remain(self):
        job = self.job('docker-acceptance')
        self.assertIn('name: Public Docker setup and recovery acceptance', job)
        self.assertIn('python scripts/mcp_acceptance.py --project srr01-4-acceptance', job)
        self.assertIn('RADAR_SETUP_BIND_ADDRESS: "127.0.0.1"', job)
        self.assertIn('permissions:\n  contents: read', self.workflow)
        self.assertNotRegex(self.workflow, r'(?m)^\s+(contents|packages|actions): write')

    def test_container_candidate_matches_runtime_tested_by_matrix(self):
        self.assertEqual((ROOT / 'Dockerfile').read_text().splitlines()[0],
                         'FROM python:3.15-slim')


if __name__ == '__main__':
    unittest.main()
