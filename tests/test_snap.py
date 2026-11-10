#!/usr/bin/env python3
"""Exercise the real Snap tasks against a local fake snap command."""

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class SnapRetries(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="vm-setup-snap-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.counts = self.base / "counts.json"
        binaries = self.base / "bin"
        binaries.mkdir()
        snap = binaries / "snap"
        snap.write_text(
            f"#!{sys.executable}\n"
            "import json, os, pathlib, sys\n"
            "base = pathlib.Path(os.environ['TEST_SNAP_HOME'])\n"
            "state = base / 'counts.json'\n"
            "counts = json.loads(state.read_text()) if state.exists() else {}\n"
            "key = ':'.join(sys.argv[1:])\n"
            "counts[key] = counts.get(key, 0) + 1\n"
            "state.write_text(json.dumps(counts))\n"
            "if counts[key] <= json.loads(os.environ['TEST_SNAP_FAILURES']).get(key, 0):\n"
            "    print('error: unexpected HTTP response (502)', file=sys.stderr)\n"
            "    sys.exit(1)\n"
            "if sys.argv[1] == 'install':\n"
            "    (base / 'snaps' / sys.argv[2] / 'current').mkdir(parents=True)\n"
            "elif os.environ['TEST_SNAP_UPDATED'] == '1':\n"
            "    print('snaps refreshed', file=sys.stderr)\n"
            "else:\n"
            "    print('All snaps up to date.', file=sys.stderr)\n"
        )
        snap.chmod(0o755)
        tasks = copy.deepcopy([
            task for task in yaml.safe_load((ROOT / "tasks/snap.yml").read_text())
            if task["name"] in ("Install snaps", "Refresh snaps")
        ])
        self.attempts = tasks[0]["retries"] + 1
        for task in tasks:
            task["become"] = False
            task["delay"] = 0
            if task["name"] == "Install snaps":
                task["args"]["creates"] = str(self.base / "snaps/{{ item }}/current")
        self.play = self.base / "play.yml"
        self.play.write_text(yaml.safe_dump([{
            "hosts": "localhost", "connection": "local", "gather_facts": False,
            "vars": {"ansible_python_interpreter": sys.executable},
            "environment": {"PATH": f"{binaries}:{os.environ['PATH']}"},
            "tasks": tasks,
        }], sort_keys=False))

    def playbook(self, *, packages=(), failures=None, updated=False, upgrade=True,
                 success=True, changed=0):
        result = subprocess.run(
            ["ansible-playbook", "-i", "localhost,", str(self.play), "-e", json.dumps({
                "snap_packages": list(packages), "chromium_source": "apt", "upgrade": upgrade,
            })],
            env=dict(os.environ, TEST_SNAP_HOME=str(self.base),
                     TEST_SNAP_FAILURES=json.dumps(failures or {}),
                     TEST_SNAP_UPDATED="1" if updated else "0",
                     ANSIBLE_HOME=str(self.base / "ansible"), ANSIBLE_NOCOLOR="1"),
            capture_output=True, text=True, timeout=120,
        )
        output = result.stdout + result.stderr
        if success:
            self.assertEqual(result.returncode, 0, output)
            self.assertRegex(output, rf"changed={changed}\s")
        else:
            self.assertNotEqual(result.returncode, 0, output)
            self.assertIn("unexpected HTTP response (502)", output)
        return json.loads(self.counts.read_text())

    def test_install_retries_each_package_and_skips_installed_snaps_on_rerun(self):
        settings = dict(packages=("drawio", "btop"),
                        failures={"install:drawio": 1, "install:btop": 2})
        counts = self.playbook(**settings, changed=1)
        self.assertEqual(counts, {"install:drawio": 2, "install:btop": 3, "refresh": 1})
        counts = self.playbook(**settings)
        self.assertEqual(counts, {"install:drawio": 2, "install:btop": 3, "refresh": 2})

    def test_persistent_install_failure_still_fails(self):
        counts = self.playbook(packages=("btop",), failures={"install:btop": 100}, success=False)
        self.assertEqual(counts, {"install:btop": self.attempts})

    def test_refresh_recovers_without_reporting_a_change(self):
        counts = self.playbook(failures={"refresh": 2})
        self.assertEqual(counts, {"refresh": 3})

    def test_refresh_reports_an_update_and_an_unchanged_rerun(self):
        self.playbook(failures={"refresh": 1}, updated=True, changed=1)
        self.assertEqual(self.playbook(), {"refresh": 3})

    def test_persistent_refresh_failure_still_fails(self):
        counts = self.playbook(failures={"refresh": 100}, success=False)
        self.assertEqual(counts, {"refresh": self.attempts})

    def test_upgrade_false_still_installs_and_does_not_refresh(self):
        counts = self.playbook(packages=("btop",), failures={"install:btop": 1},
                               upgrade=False, changed=1)
        self.assertEqual(counts, {"install:btop": 2})


if __name__ == "__main__":
    unittest.main(verbosity=2)
