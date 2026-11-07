#!/usr/bin/env python3
"""Focused integration tests; requires ansible-playbook, pnpm and starship on PATH."""

import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import tomllib
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def run(*args, env=None, cwd=ROOT):
    return subprocess.run(
        args,
        env=env,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )


class GlobalUpdates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vm-setup-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / "pnpm"
        (self.home / "bin").mkdir(parents=True)
        self.pnpm = shutil.which("pnpm")
        (self.home / "bin/pnpm").write_text(
            "#!/bin/sh\nexec " + shlex.quote(self.pnpm) + ' "$@"\n'
        )
        (self.home / "bin/pnpm").chmod(0o755)
        self.env = dict(
            os.environ,
            PNPM_HOME=str(self.home),
            PATH=f"{self.home}/bin:{os.environ['PATH']}",
            ANSIBLE_NOCOLOR="1",
        )
        self.play = self.base / "play.yml"
        self.play.write_text(
            json.dumps([
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "vars": {
                        "pnpm_home": str(self.home),
                        "upgrade": True,
                        "ansible_python_interpreter": sys.executable,
                    },
                    "environment": {
                        "PNPM_HOME": str(self.home),
                        "PATH": self.env["PATH"],
                    },
                    "tasks": [
                        {
                            "ansible.builtin.import_tasks": str(
                                ROOT / "tasks/pnpm_globals.yml"
                            )
                        }
                    ],
                }
            ])
        )

    def playbook(self, *args, changed=0, success=True):
        result = run(
            "ansible-playbook",
            "-i",
            "localhost,",
            "-v",
            str(self.play),
            *args,
            env=self.env,
        )
        output = result.stdout + result.stderr
        if success:
            self.assertEqual(result.returncode, 0, output)
            self.assertRegex(output, rf"changed={changed}\s")
        else:
            self.assertNotEqual(result.returncode, 0, output)
            self.assertRegex(output, r"failed=1\s")
        return output

    def test_empty_and_repeat(self):
        self.playbook()
        self.playbook()

    def test_disabled_and_check_mode_do_not_execute(self):
        (self.home / "bin/pnpm").unlink()
        self.playbook("-e", "upgrade=false")
        self.playbook("--check")

    def test_update_errors_are_not_ignored(self):
        executable = self.home / "bin/pnpm"
        executable.unlink()
        executable.write_text(
            '#!/bin/sh\nif [ "$1" = "-g" ]; then echo update-failed >&2; exit 1; fi\n'
            f'exec {shlex.quote(self.pnpm)} "$@"\n'
        )
        executable.chmod(0o755)
        self.assertIn("update-failed", self.playbook(success=False))

    def test_list_errors_are_not_ignored(self):
        executable = self.home / "bin/pnpm"
        executable.unlink()
        executable.write_text("#!/bin/sh\necho list-failed >&2\nexit 2\n")
        executable.chmod(0o755)
        self.assertIn("list-failed", self.playbook(success=False))

    def test_deep_list_errors_are_not_ignored(self):
        executable = self.home / "bin/pnpm"
        executable.unlink()
        executable.write_text(
            '#!/bin/sh\ncase " $* " in *" Infinity "*) '
            "echo tree-list-failed >&2; exit 2;; esac\n"
            + "printf '%s\\n' "
            + shlex.quote(
                json.dumps([{"dependencies": {"fixture": {"version": "1.0.0"}}}])
            )
            + "\n"
        )
        executable.chmod(0o755)
        self.assertIn("tree-list-failed", self.playbook(success=False))

    def test_after_update_list_errors_are_not_ignored(self):
        executable = self.home / "bin/pnpm"
        marker = shlex.quote(str(self.base / "updated"))
        executable.unlink()
        executable.write_text(
            '#!/bin/sh\nif [ "$1" = "-g" ]; then touch ' + marker + "; exit 0; fi\n"
            "if [ -e " + marker + " ]; then echo after-list-failed >&2; exit 2; fi\n"
            "printf '[]\\n'\n"
        )
        executable.chmod(0o755)
        self.assertIn("after-list-failed", self.playbook(success=False))

    def registry(self, manifests, available):
        tarballs = {}
        metadata = {}
        for index, manifest in enumerate(manifests):
            data = io.BytesIO()
            with tarfile.open(fileobj=data, mode="w:gz") as archive:
                contents = {
                    "package.json": json.dumps(manifest).encode(),
                    "cli.js": f'#!/usr/bin/env node\nconsole.log("{manifest["version"]}")\n'.encode(),
                }
                for name, payload in contents.items():
                    item = tarfile.TarInfo("package/" + name)
                    item.size = len(payload)
                    item.mode = 0o755
                    archive.addfile(item, io.BytesIO(payload))
            path = f"/tarballs/{index}.tgz"
            tarballs[path] = data.getvalue()
            metadata[(manifest["name"], manifest["version"])] = (manifest, path)

        class Registry(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                path = unquote(self.path).split("?", 1)[0]
                if path in tarballs:
                    payload = tarballs[path]
                else:
                    name = path.lstrip("/")
                    if name not in available:
                        self.send_error(404)
                        return
                    versions = {}
                    for version in available[name]:
                        manifest, tarball = metadata[(name, version)]
                        versions[version] = dict(
                            manifest,
                            dist={
                                "tarball": f"http://127.0.0.1:{self.server.server_port}{tarball}",
                                "shasum": hashlib.sha1(tarballs[tarball]).hexdigest(),
                            },
                        )
                    payload = json.dumps({
                        "name": name,
                        "dist-tags": {"latest": available[name][-1]},
                        "versions": versions,
                    }).encode()
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    "application/octet-stream"
                    if path in tarballs
                    else "application/json",
                )
                self.send_header("Content-Length", str(len(payload)))
                self.send_header(
                    "ETag", '"' + hashlib.sha256(payload).hexdigest() + '"'
                )
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(payload)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Registry)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.env["npm_config_registry"] = f"http://127.0.0.1:{server.server_port}"
        self.env["PNPM_CONFIG_REGISTRY"] = self.env["npm_config_registry"]
        self.env["PNPM_CONFIG_MINIMUM_RELEASE_AGE"] = "0"
        self.env["npm_config_minimum_release_age"] = "0"

    def install(self, package):
        result = run(str(self.home / "bin/pnpm"), "add", "-g", package, env=self.env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def exercise_update(self, multiple=False, transitive=False):
        fixture = "vm-setup-fixture"
        sentinel = "@vm-setup/sentinel"
        child = "vm-setup-child"
        manifests = [
            {
                "name": fixture,
                "version": version,
                "bin": {fixture: "cli.js"},
                **({"dependencies": {child: "^1.0.0"}} if transitive else {}),
            }
            for version in ("1.0.0", "1.0.1")
        ] + [{"name": sentinel, "version": "1.0.0", "bin": {"sentinel": "cli.js"}}]
        manifests += [
            {"name": child, "version": version} for version in ("1.0.0", "1.0.1")
        ]
        available = {name: ["1.0.0"] for name in (fixture, sentinel, child)}
        self.registry(manifests, available)
        self.install(fixture + "@^1.0.0")
        if multiple:
            self.install(sentinel + "@1.0.0")
            roots = run(
                str(self.home / "bin/pnpm"), "list", "-g", "--json", env=self.env
            )
            self.assertEqual(roots.returncode, 0, roots.stderr)
            names = {
                name
                for group in json.loads(roots.stdout)
                for name in group.get("dependencies", {})
            }
            self.assertTrue({fixture, sentinel}.issubset(names))
        self.playbook()
        available[child if transitive else fixture].append("1.0.1")
        self.playbook("-e", "upgrade=false")
        self.assertEqual(run(fixture, env=self.env).stdout.strip(), "1.0.0")
        self.playbook(changed=1)
        expected = "1.0.0" if transitive else "1.0.1"
        self.assertEqual(run(fixture, env=self.env).stdout.strip(), expected)
        tree = run(
            str(self.home / "bin/pnpm"),
            "list",
            "-g",
            fixture,
            "--json",
            "--depth",
            "Infinity",
            env=self.env,
        )
        self.assertEqual(tree.returncode, 0, tree.stderr)
        if transitive:
            self.assertRegex(tree.stdout, r'"vm-setup-child"[\s\S]*?"version": "1.0.1"')
        if multiple:
            self.assertEqual(run("sentinel", env=self.env).stdout.strip(), "1.0.0")
        self.playbook()

    def test_real_package_update_and_repeat(self):
        self.exercise_update()

    def test_multiple_isolated_global_packages(self):
        self.exercise_update(multiple=True)

    def test_transitive_update_with_multiple_global_packages(self):
        self.exercise_update(multiple=True, transitive=True)


class PromptStyle(unittest.TestCase):
    def test_palette_and_real_rendering(self):
        config = ROOT / "files/starship.toml"
        text = config.read_text()
        parsed = tomllib.loads(text)
        colors = parsed["palettes"][parsed["palette"]]
        self.assertEqual(colors["color_pink"], "#ff79c6")
        self.assertEqual(colors["color_purple"], "#bd93f9")
        for name in re.findall(r"\bcolor_\w+", text):
            self.assertIn(name, colors)
        with tempfile.TemporaryDirectory() as directory:
            env = dict(
                os.environ,
                STARSHIP_CONFIG=str(config),
                STARSHIP_CACHE=directory,
                TERM="xterm-256color",
                COLORTERM="truecolor",
            )
            result = run("git", "init", directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            Path(directory, "package.json").write_text(
                '{"name":"fixture","version":"1.0.0"}'
            )
            Path(directory, "changed.txt").write_text("untracked")
            for status in ("0", "1"):
                result = run(
                    "starship",
                    "prompt",
                    "--status",
                    status,
                    "--cmd-duration",
                    "3000",
                    env=env,
                    cwd=directory,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertIn("38;2;255;121;198", result.stdout)
                self.assertIn("48;2;189;147;249", result.stdout)
                self.assertIn("?2", result.stdout)
                self.assertIn("48;2;139;233;253", result.stdout)
                if status == "1":
                    self.assertIn("✘1", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
