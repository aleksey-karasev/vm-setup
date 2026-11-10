#!/usr/bin/env python3
"""Offline bootstrap and Ansible routing tests; requires ansible-core on PATH.

Ansible evaluates the real task conditions, tags and arguments, while a recording
action replaces system mutations. Real package/service tests run in CI containers.
"""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class Bootstrap(unittest.TestCase):
    def bootstrap(self, distro, *, installed=False, missing_git=False, password=False,
                  arguments=(), root=False, success=True, brew_location="path",
                  forwarded=("--tags", "dnf,gh", "-e", "upgrade=false")):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            binaries = base / "bin"
            binaries.mkdir()
            log = base / "commands.jsonl"
            shim = binaries / "shim"
            shim.write_text(
                f"#!{sys.executable}\n"
                "import json, os, pathlib, shlex, subprocess, sys\n"
                "name = pathlib.Path(sys.argv[0]).name\n"
                "args = sys.argv[1:]\n"
                "if name == 'uname':\n"
                "    print('Darwin' if os.environ['TEST_DISTRO'] == 'macos' else 'Linux')\n"
                "    sys.exit(0)\n"
                "if name == 'id':\n"
                "    print('1000' if os.environ['TEST_ROOT'] == '0' and (os.environ['TEST_PASSWORD'] == '1' or os.environ['TEST_DISTRO'] == 'macos') else '0')\n"
                "    sys.exit(0)\n"
                "if name == 'brew' and args == ['shellenv']:\n"
                "    print('export PATH=' + shlex.quote(str(pathlib.Path(sys.argv[0]).parent)) + ':$PATH')\n"
                "    sys.exit(0)\n"
                "with open(os.environ['TEST_LOG'], 'a') as output:\n"
                "    output.write(json.dumps([name, *args]) + '\\n')\n"
                "if name == 'sudo':\n"
                "    if args == ['-k', '-n', 'true']: sys.exit(1)\n"
                "    if args == ['-v']: sys.exit(0)\n"
                "    sys.exit(subprocess.call(args))\n"
                "if name == 'curl':\n"
                "    print(os.environ['TEST_BREW_INSTALL'])\n"
                "    sys.exit(0)\n"
                "if name in ('dnf', 'pacman', 'apt-get', 'brew'):\n"
                "    for tool in ('ansible-pull', 'git'):\n"
                "        target = pathlib.Path(sys.argv[0]).parent / tool\n"
                "        if not target.exists(): target.symlink_to(pathlib.Path(sys.argv[0]).resolve())\n"
            )
            shim.chmod(0o755)
            for tool in ("id", "uname", "sudo", "dnf", "pacman", "apt-get", "curl"):
                (binaries / tool).symlink_to("shim")
            prefixes = {"arm64": base / "opt/homebrew", "intel": base / "usr/local"}
            if brew_location == "path":
                (binaries / "brew").symlink_to("shim")
            elif brew_location in prefixes:
                candidate = prefixes[brew_location] / "bin/brew"
                candidate.parent.mkdir(parents=True)
                candidate.symlink_to(shim)
            install_code = (
                "from pathlib import Path; "
                f"target = Path({str(prefixes['arm64'] / 'bin/brew')!r}); "
                "target.parent.mkdir(parents=True); "
                f"target.symlink_to({str(shim)!r})"
            )
            installer = f"{shlex.quote(sys.executable)} -c {shlex.quote(install_code)}"
            for tool in ("env", "mkdir", "dirname", "touch", "grep", "sed", "tail"):
                (binaries / tool).symlink_to(shutil.which(tool))
            if installed:
                (binaries / "ansible-pull").symlink_to("shim")
            if not missing_git:
                (binaries / "git").symlink_to("shim")
            # Point only the release-file probes at fixture files.
            script = (ROOT / "bootstrap.sh").read_text()
            for prefix, fixture in (("/opt/homebrew", prefixes["arm64"]),
                                    ("/usr/local", prefixes["intel"])):
                script = script.replace(prefix, str(fixture))
            for name in ("arch", "fedora"):
                marker = base / f"{name}-release"
                if distro == name:
                    marker.touch()
                script = script.replace(f"/etc/{name}-release", str(marker))
            bootstrap = base / "bootstrap.sh"
            bootstrap.write_text(script)
            result = subprocess.run(
                [shutil.which("bash"), str(bootstrap), *forwarded, *arguments],
                env=dict(os.environ, PATH=str(binaries), TEST_LOG=str(log),
                         TEST_PASSWORD="1" if password else "0", TEST_DISTRO=distro,
                         TEST_BREW_INSTALL=installer,
                         TEST_ROOT="1" if root else "0", HOME=str(base / "home")),
                capture_output=True, text=True, timeout=30,
            )
            if success:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            else:
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Homebrew cannot run as root", result.stderr)
            if arguments:
                self.assertIn("nvidia_enabled: false", (base / "home/.config/vm-setup/vars.yml").read_text())
            return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def test_fedora_bootstrap_and_forwarded_arguments(self):
        calls = self.bootstrap("fedora")
        self.assertEqual(calls[0], ["dnf", "install", "-y", "ansible-core", "git",
                                    "/usr/bin/curl", "ca-certificates", "python3-libdnf5"])
        self.assertEqual(calls[-1][-5:], ["--tags", "dnf,gh", "-e", "upgrade=false", "local.yml"])
        self.assertIn("--full", calls[-1])

    def test_existing_tools_skip_bootstrap_packages(self):
        self.assertEqual([call[0] for call in self.bootstrap("fedora", installed=True)],
                         ["ansible-pull"])

    def test_missing_git_installs_prerequisites(self):
        self.assertEqual(self.bootstrap("fedora", installed=True, missing_git=True)[0][0], "dnf")

    def test_password_and_become_argument(self):
        calls = self.bootstrap("fedora", password=True)
        self.assertIn(["sudo", "dnf", "install", "-y", "ansible-core", "git",
                       "/usr/bin/curl", "ca-certificates", "python3-libdnf5"], calls)
        self.assertIn("--ask-become-pass", calls[-1])

    def test_existing_distribution_bootstraps(self):
        for distro, manager in (("debian", "apt-get"), ("arch", "pacman")):
            with self.subTest(distro=distro):
                calls = self.bootstrap(distro)
                self.assertEqual(calls[0][0], manager)
                self.assertEqual(calls[-1][0], "ansible-pull")

    def test_macos_bootstrap_uses_homebrew_without_sudo(self):
        calls = self.bootstrap("macos")
        self.assertEqual(calls[0], ["brew", "install", "ansible", "git"])
        self.assertNotIn("--ask-become-pass", calls[-1])
        self.assertFalse(any(call[0] == "sudo" for call in calls))

    def test_macos_existing_prerequisites(self):
        self.assertEqual([call[0] for call in self.bootstrap("macos", installed=True)],
                         ["ansible-pull"])
        self.assertEqual(self.bootstrap("macos", installed=True, missing_git=True)[0][0], "brew")

    def test_macos_rejects_root(self):
        self.assertEqual(self.bootstrap("macos", root=True, success=False), [])

    def test_macos_discovers_both_homebrew_prefixes(self):
        for location in ("arm64", "intel"):
            with self.subTest(location=location):
                self.assertEqual(self.bootstrap("macos", brew_location=location)[0],
                                 ["brew", "install", "ansible", "git"])

    def test_macos_installs_missing_homebrew(self):
        calls = self.bootstrap("macos", brew_location="missing")
        self.assertEqual(calls[0], ["sudo", "-v"])
        self.assertEqual(calls[1], ["curl", "-fsSL", "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"])
        self.assertEqual(calls[2], ["brew", "install", "ansible", "git"])
        self.assertEqual(calls[-1][0], "ansible-pull")

    def test_empty_arguments_work_with_bash_32(self):
        for distro in ("macos", "debian"):
            with self.subTest(distro=distro):
                self.assertEqual(self.bootstrap(distro, installed=True, forwarded=())[-1][-1], "local.yml")

    def test_remember_flags_work_with_bsd_sed(self):
        calls = self.bootstrap("macos", installed=True, arguments=("--nvidia", "--no-nvidia"))
        self.assertNotIn("--nvidia", calls[-1])
        self.assertNotIn("--no-nvidia", calls[-1])


class DistributionTasks(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="vm-setup-routing-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.log = self.base / "tasks.jsonl"
        plugins = self.base / "action_plugins"
        plugins.mkdir()
        (plugins / "record.py").write_text(
            "import json, os\n"
            "from ansible.plugins.action import ActionBase\n"
            "class ActionModule(ActionBase):\n"
            "    def run(self, tmp=None, task_vars=None):\n"
            "        with open(os.environ['TEST_LOG'], 'a') as output:\n"
            "            output.write(json.dumps(dict(name=self._task.name, become=self._task.become, **self._task.args)) + '\\n')\n"
            "        arguments = self._task.args['arguments']\n"
            "        argv = arguments.get('argv', []) if isinstance(arguments, dict) else []\n"
            "        if argv and argv[0].endswith('/brew'):\n"
            "            if 'outdated' in argv:\n"
            "                data = json.loads(os.environ.get('TEST_BREW_OUTDATED', '{}'))\n"
            "                return dict(changed=False, rc=0, stdout=json.dumps(dict(formulae=data.get('formulae', []), casks=data.get('casks', []))))\n"
            "            packages = json.loads(os.environ.get('TEST_BREW_INSTALLED', '[]'))\n"
            "            return dict(changed=False, rc=0, stdout='\\n'.join(packages), stdout_lines=packages)\n"
            "        if arguments == 'colima status':\n"
            "            return dict(changed=False, rc=int(os.environ.get('TEST_COLIMA_RC', '0')))\n"
            "        if self._task.args['module'] == 'ansible.builtin.uri':\n"
            "            return dict(changed=False, location='https://github.com/ryanoasis/nerd-fonts/releases/tag/v3.4.0')\n"
            "        if argv and argv[0].endswith('/pnpm') and 'list' in argv:\n"
            "            return dict(changed=False, rc=0, stdout='[]')\n"
            "        if self._task.args['module'] == 'ansible.builtin.command' and str(self._task.args['arguments']).startswith('rpm -qa '):\n"
            "            packages = json.loads(os.environ.get('TEST_INSTALLED_RPMS', '[]'))\n"
            "            return dict(changed=False, rc=0, stdout='\\n'.join(packages), stdout_lines=packages)\n"
            "        return dict(changed=False, rc=0, stdout='there is nothing to do',\n"
            "                    stderr='All snaps up to date', content='e30=')\n"
        )
        for source in [ROOT / "local.yml", *ROOT.glob("tasks/*.yml")]:
            data = yaml.safe_load(source.read_text())
            self.record_mutations(data)
            if source.name == "local.yml":
                data[0]["gather_facts"] = False
                data[0]["vars_files"] = [str(ROOT / "vars/main.yml")]
            target = self.base / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(yaml.safe_dump(data, sort_keys=False))

    def record_mutations(self, data):
        if isinstance(data, list):
            for item in data:
                self.record_mutations(item)
        elif isinstance(data, dict):
            for key in list(data):
                if key.startswith("ansible.builtin.") and key not in (
                    "ansible.builtin.import_tasks", "ansible.builtin.assert",
                    "ansible.builtin.debug", "ansible.builtin.include_vars",
                ):
                    arguments = data.pop(key)
                    data["record"] = {"module": key, "arguments": arguments}
                    if "args" in data:
                        data["record"]["extra_arguments"] = data.pop("args")
                elif key in ("tasks", "block", "rescue", "always"):
                    self.record_mutations(data[key])

    def playbook(self, distro="Fedora", *, tags="dnf,snap,docker,gh,nvidia", success=True,
                 installed_rpms=(), architecture="x86_64", failure_message=None,
                 brew_installed=(), brew_outdated=None, colima_rc=0, **variables):
        facts = {
            "distribution": distro,
            "os_family": {"Fedora": "RedHat", "Archlinux": "Archlinux", "MacOSX": "Darwin"}.get(distro, "Debian"),
            "distribution_version": "44" if distro == "Fedora" else "24.04",
            "distribution_major_version": "44" if distro == "Fedora" else "24",
            "distribution_release": "noble", "architecture": architecture,
            "kernel": "test-kernel", "user_id": "dev", "service_mgr": "launchd" if distro == "MacOSX" else "systemd",
        }
        settings = dict(ansible_facts=facts, home=str(self.base / "home"),
                        machine_vars_file=str(self.base / "missing-vars.yml"),
                        is_wsl=False, upgrade=True, nvidia_enabled=True)
        settings.update(variables)
        result = subprocess.run(
            ["ansible-playbook", "-i", "localhost,", str(self.base / "local.yml"),
             "--tags", tags, "-e", json.dumps(settings)],
            env=dict(os.environ, TEST_LOG=str(self.log), ANSIBLE_NOCOLOR="1",
                     TEST_INSTALLED_RPMS=json.dumps(installed_rpms),
                     TEST_BREW_INSTALLED=json.dumps(brew_installed),
                     TEST_BREW_OUTDATED=json.dumps(brew_outdated or {}),
                     TEST_COLIMA_RC=str(colima_rc), HOMEBREW_PREFIX="",
                     ANSIBLE_HOME=str(self.base / "ansible")),
            capture_output=True, text=True, timeout=120,
        )
        output = result.stdout + result.stderr
        if success:
            self.assertEqual(result.returncode, 0, output)
        else:
            self.assertNotEqual(result.returncode, 0, output)
            self.assertIn(failure_message, output)
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_fedora_routing_and_native_packages(self):
        calls = self.playbook(dnf_packages_exclude=["texlive-scheme-full", "bat"])
        self.assertFalse(any(call["module"].endswith((".apt", ".deb822_repository")) for call in calls))
        self.assertFalse(any("pacman" in str(call["arguments"]) for call in calls))
        packages = next(call["arguments"]["name"] for call in calls if call["name"] == "Install dnf packages")
        self.assertNotIn("texlive-scheme-full", packages)
        self.assertNotIn("bat", packages)
        self.assertTrue({"ffmpeg-free", "postgresql", "du-dust", "chromium"}.issubset(packages))
        self.assertTrue(any(call["arguments"].get("name") == "gh" for call in calls if isinstance(call["arguments"], dict)))
        snaps = [call["arguments"] for call in calls if call["name"] == "Install snaps"]
        self.assertEqual(snaps, ["snap install drawio"])
        self.assertTrue(any(call["arguments"].get("dest") == "/snap" for call in calls if isinstance(call["arguments"], dict)))
        upgrades = [call for call in calls if call["name"] == "Upgrade installed dnf packages"]
        self.assertEqual(len(upgrades), 1)
        self.assertEqual(upgrades[0]["arguments"]["state"], "latest")

    def test_fedora_upgrade_and_nvidia_disabled(self):
        calls = self.playbook(upgrade=False, nvidia_enabled=False)
        self.assertNotIn("Upgrade installed dnf packages", [call["name"] for call in calls])
        self.assertNotIn("Refresh snaps", [call["name"] for call in calls])
        self.assertFalse(any("nvidia" in str(call).lower() for call in calls))

    def test_fedora_nvidia_and_wsl(self):
        for wsl in (False, True):
            with self.subTest(wsl=wsl):
                self.log.unlink(missing_ok=True)
                calls = self.playbook(is_wsl=wsl)
                names = [call["name"] for call in calls]
                self.assertEqual("Install NVIDIA driver" in names, not wsl)
                self.assertEqual("Install kernel headers for the NVIDIA kernel module" in names, not wsl)
                self.assertIn("Install CUDA toolkit", names)
                self.assertIn("Install NVIDIA Container Toolkit and nvtop", names)
                urls = [call["arguments"]["url"] for call in calls if call["module"].endswith(".get_url")]
                self.assertIn("https://developer.download.nvidia.com/compute/cuda/repos/fedora44/x86_64/cuda-fedora44.repo", urls)

    def test_dnf_tag_is_isolated(self):
        calls = self.playbook(tags="dnf")
        self.assertIn("Install dnf packages", [call["name"] for call in calls])
        self.assertFalse(any(call["module"].endswith(".get_url") for call in calls))

    def test_fedora_cuda_rejects_unsupported_architecture(self):
        calls = self.playbook(tags="nvidia", architecture="aarch64", success=False,
                              failure_message="Fedora NVIDIA/CUDA setup currently requires x86_64.")
        self.assertFalse(any(call["module"].endswith(".get_url") for call in calls))

    def test_docker_cleanup_does_not_remove_virtual_providers(self):
        calls = self.playbook(tags="docker", installed_rpms=["container-selinux", "podman-docker"])
        removals = [call["arguments"]["name"] for call in calls
                    if call["name"] == "Remove distro packages that conflict with Docker Engine"]
        self.assertEqual(removals, [["podman-docker"]])

    def test_existing_distributions_do_not_run_fedora_tasks(self):
        for distro in ("Ubuntu", "Debian", "Archlinux"):
            with self.subTest(distro=distro):
                self.log.unlink(missing_ok=True)
                calls = self.playbook(distro, tags="apt,pacman,snap,docker,gh,nvidia")
                self.assertFalse(any(call["module"].endswith(".dnf") for call in calls))
                self.assertFalse(any("Fedora" in call["name"] for call in calls))

    def test_macos_full_routing_on_both_architectures(self):
        for architecture, prefix in (("arm64", "/opt/homebrew"), ("x86_64", "/usr/local")):
            with self.subTest(architecture=architecture):
                self.log.unlink(missing_ok=True)
                calls = self.playbook("MacOSX", tags="all", architecture=architecture,
                                      brew_packages_exclude=["texlive"], brew_casks_exclude=["drawio"])
                self.assertFalse(any(call["become"] for call in calls))
                self.assertFalse(any(call["module"].endswith((".apt", ".dnf", ".user", ".systemd_service")) for call in calls))
                self.assertFalse(any("nvidia" in str(call).lower() for call in calls))
                brew_installs = [call["arguments"]["argv"] for call in calls
                                 if call["name"] == "Install Homebrew packages"]
                self.assertTrue(all(argv[0] == prefix + "/bin/brew" for argv in brew_installs))
                formulae = [name for argv in brew_installs if "--formula" in argv for name in argv[3:]]
                casks = [name for argv in brew_installs if "--cask" in argv for name in argv[3:]]
                self.assertNotIn("texlive", formulae)
                self.assertNotIn("drawio", casks)
                self.assertTrue({"libpq", "fd", "gh", "rclone", "lazydocker", "colima", "docker-compose"}.issubset(formulae))
                self.assertEqual(set(casks), {"inkscape", "ungoogled-chromium"})
                names = [call["name"] for call in calls]
                self.assertIn("Enable starship in zsh", names)
                self.assertIn("Enable fzf key bindings in zsh", names)
                self.assertNotIn("Rebuild the font cache", names)
                font_paths = [call["arguments"]["path"] for call in calls if call["name"] == "Create font directories"]
                self.assertTrue(all("/Library/Fonts/NerdFonts/" in path for path in font_paths))
                self.assertTrue(any("Library/pnpm/bin/pnpm" in str(call) for call in calls))

    def test_macos_upgrades_only_selected_outdated_packages(self):
        calls = self.playbook("MacOSX", tags="brew", brew_packages=["jq", "fd"],
                              brew_casks=["drawio"], brew_installed=["jq", "drawio"],
                              brew_outdated={"formulae": [{"name": "jq"}, {"name": "unmanaged"}],
                                             "casks": [{"name": "drawio"}]})
        installs = [call["arguments"]["argv"][3:] for call in calls if call["name"] == "Install Homebrew packages"]
        self.assertIn(["fd"], installs)
        upgrades = [call["arguments"]["argv"][3:] for call in calls if call["name"] == "Upgrade outdated Homebrew packages"]
        self.assertEqual(upgrades, [["jq"], ["drawio"]])

    def test_macos_no_upgrades_and_existing_packages(self):
        calls = self.playbook("MacOSX", tags="brew", upgrade=False,
                              brew_packages=["jq"], brew_casks=[],
                              brew_installed=["ca-certificates", "curl", "git", "gnu-tar", "xz", "jq"])
        names = [call["name"] for call in calls]
        self.assertNotIn("Update Homebrew metadata", names)
        self.assertNotIn("List outdated Homebrew packages", names)
        self.assertNotIn("Install Homebrew packages", names)

    def test_macos_component_tags_and_colima_start(self):
        for tag, package in (("gh", "gh"), ("rclone", "rclone"), ("lazydocker", "lazydocker"), ("docker", "colima")):
            with self.subTest(tag=tag):
                self.log.unlink(missing_ok=True)
                calls = self.playbook("MacOSX", tags=tag, colima_rc=1)
                installs = [name for call in calls if call["name"] == "Install Homebrew packages"
                            for name in call["arguments"]["argv"][3:]]
                self.assertIn(package, installs)
                self.assertNotIn("ffmpeg", installs)
                self.assertEqual(any(call["name"] == "Start Colima" for call in calls), tag == "docker")

    def test_unsupported_distribution_fails_before_installing(self):
        self.assertEqual(self.playbook("Rocky", success=False,
                                      failure_message="Only Ubuntu, Debian, Arch Linux, Fedora and macOS are supported"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
