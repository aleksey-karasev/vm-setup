# vm-setup

Turns a clean Ubuntu, Debian, Arch Linux, Fedora or macOS machine into a ready dev environment with one
command, and upgrades everything each time it is run again. Ansible runs on the
machine itself through `ansible-pull`, so there is no control node.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/aleksey-karasev/vm-setup/main/bootstrap.sh | bash
```

Add `--nvidia` for the NVIDIA driver, CUDA toolkit and container toolkit:

```bash
curl -fsSL https://raw.githubusercontent.com/aleksey-karasev/vm-setup/main/bootstrap.sh | bash -s -- --nvidia
```

The script installs `ansible-core` and `git`, clones this repo to
`~/.local/share/vm-setup` and applies `local.yml`, asking for the sudo password
if one is needed. Log out and back in afterwards to get the new `PATH` and the
`docker` group. Without curl, `wget -qO-` does the same.

On macOS, run as your normal user. Bootstrap finds Homebrew under `/opt/homebrew`
(Apple Silicon) or `/usr/local` (Intel), or uses the `brew` already on `PATH`.
If missing, it installs Homebrew with the official installer, which may ask for
your administrator password and install Xcode Command Line Tools. Ansible and
Git then come from Homebrew's `ansible` and `git` formulae. Homebrew packages run
without sudo. Open a new terminal afterwards to load the shell configuration.

## Update

```bash
vm-setup
```

Pulls the repo and applies it again, bringing system packages, snaps and every
tool to the newest version. Arguments go to `ansible-pull`:

```bash
vm-setup --tags uv,duckdb      # only some components
vm-setup --skip-tags apt,snap  # pacman on Arch; dnf on Fedora
vm-setup --skip-tags brew      # skip the macOS package and application lists
vm-setup -e upgrade=false      # install what is missing, upgrade nothing
```

Global npm packages are updated with `pnpm -g update` after pnpm and Node.js
are available. This follows each package's declared version range (it does not
force major upgrades with `--latest`) and is skipped with `upgrade=false`.
The task enumerates global package names at depth 0, then compares each package's
JSON dependency tree before and after the update, so an unchanged second run
reports `changed=0`. Deep listing always selects one package because pnpm does
not support a merged transitive tree across isolated global installations. Nonzero update/list exit codes still
fail the play; failures are not treated as successful no-ops.

## What is installed

| Tag | Installs | Source |
| --- | --- | --- |
| `apt` | ffmpeg, inkscape, pandoc, texlive-full, graphviz, ripgrep, duf, fd, bat, eza, fzf, jq, tree, hyperfine, tmux, sqlite3, psql, git-lfs, 7zip, wget, rsync, zip, build-essential, cmake, pkg-config | apt |
| `snap` | drawio, btop, procs, dust, chromium | snap (chromium: apt on Debian) |
| `pacman` | on Arch, everything in the `apt` and `snap` rows, and bash-completion | pacman |
| `dnf` | on Fedora, equivalents of the `apt` row, bash-completion, btop, procs, dust and chromium | Fedora repositories |
| `brew` | on macOS, command-line equivalents of the Linux package lists; Inkscape, draw.io and Ungoogled Chromium applications | Homebrew formulae and casks |
| `docker` | Docker Engine, buildx and compose plugins (macOS: Docker CLI and Colima) | Docker's apt/RPM repository (Arch: pacman; macOS: Homebrew) |
| `gh` | GitHub CLI | GitHub's apt repository (Arch: pacman; Fedora: dnf; macOS: Homebrew) |
| `uv` | uv, Python 3.9 to 3.14, the tools in `uv_tools` | uv installer |
| `pnpm` | pnpm, Node.js | pnpm installer |
| `rtk`, `rclone`, `duckdb`, `lazydocker` | rtk, rclone, DuckDB CLI, lazydocker | each tool's installer (macOS: rclone and lazydocker from Homebrew) |
| `lazygit` | Lazygit terminal UI for Git | official GitHub release on Linux; Homebrew on macOS |
| `starship` | starship, its config and bash init; zsh init on macOS | starship installer, `files/starship.toml` |
| `shell` | 100k-line shared history and fzf key bindings in bash (also zsh on macOS), Git LFS in `~/.gitconfig` | shell configuration, `git lfs install` |
| `fonts` | Nerd Fonts in `nerd_fonts` | latest GitHub release |
| `nvidia` | driver, CUDA toolkit, container toolkit, nvtop (opt-in) | NVIDIA's apt/RPM repositories (Arch: pacman) |

`fd` and `bat` are linked into `~/.local/bin`, because apt installs them as
`fdfind` and `batcat`.

`psql` is installed from `postgresql-client` on Ubuntu/Debian and
`postgresql-libs` on Arch and `postgresql` on Fedora. These packages install the
PostgreSQL client tools.

Fedora uses DNF5, with `python3-libdnf5` installed during bootstrap. Its package
list uses `ffmpeg-free` (Fedora's codec selection), `texlive-scheme-full`,
`fd-find`, `du-dust`, and explicit compiler/build packages. Only draw.io uses
Snap on Fedora; the `snap` tag installs snapd, enables its socket and creates
the `/snap` link. The other tools in the `snap` row use native Fedora packages.
The `dnf` tag also upgrades installed RPM packages unless `upgrade=false`.
Fedora's `chromium-browser` is exposed as `~/.local/bin/chromium`.

macOS uses Homebrew formulae for CLI packages, including `texlive`, `libpq`
(PostgreSQL client tools), `sevenzip` (`7zz`), and `gnu-tar` for font extraction.
Compiler tools come from Xcode Command Line Tools. The `brew` tag installs and
upgrades the configured formulae and casks; component tags such as `gh`, `docker`,
`rclone`, `lazydocker` and `lazygit` manage their own formulae. With `upgrade=false`, installed
packages are left alone and Homebrew metadata is not refreshed.
Homebrew's [Chromium cask is disabled](https://formulae.brew.sh/cask/chromium),
so macOS installs [Ungoogled Chromium](https://formulae.brew.sh/cask/ungoogled-chromium)
and exposes its executable as `chromium`.

Lazygit installs on every supported system. On Linux, the `lazygit` tag extracts
the latest official x86_64 or ARM64 release into `~/.local/bin`; macOS uses its
Homebrew formula. Run `vm-setup --tags lazygit` to install or update it alone.
With `upgrade=false`, an existing installation is kept.

The macOS `docker` tag installs Docker CLI, buildx, compose and
[Colima](https://github.com/abiosoft/colima), starts Colima's default Linux VM,
and makes the CLI plugins available in `~/.docker/cli-plugins`. Colima selects its
Docker context when starting; after restarting macOS, run `colima start` or
`vm-setup --tags docker` to start it again. No Docker group is needed.

macOS configures both zsh and bash, including login-shell paths for Homebrew,
`~/.local/bin`, pnpm in `~/Library/pnpm`, and Homebrew's `libpq` tools. Starship
installs into `~/.local/bin` without sudo. Nerd Fonts install into
`~/Library/Fonts/NerdFonts`; macOS discovers them without `fc-cache`.

On Arch, TeX Live is `texlive-meta` and `texlive-lang`, without the 3 GB of
`texlive-doc`. Arch does not support partial upgrades, so the system is
upgraded before pacman installs anything, also when only `docker`, `gh` or
`nvidia` is selected. With `upgrade=false` pacman installs from the package
databases already on the machine.

## Configuration

Package lists, Python versions and the other settings are in
[vars/main.yml](vars/main.yml); push a change there to change every machine.
To change one machine only, override values in `~/.config/vm-setup/vars.yml`:

```yaml
apt_packages_exclude: [texlive-full]
pacman_packages_exclude: [texlive-meta, texlive-lang]
dnf_packages_exclude: [texlive-scheme-full]
brew_packages_exclude: [texlive]
brew_casks_exclude: [ungoogled-chromium]
nerd_fonts: [JetBrainsMono, FiraCode]
```

`--nvidia` and `--no-nvidia` are remembered in that file. NVIDIA tasks are skipped
on macOS, including when an existing machine override enables them. On Linux, when enabled:

- the `nvidia-open` driver is installed (reboot afterwards), except under WSL2,
  where the Windows driver is used
- `cuda-toolkit` is installed, with `/usr/local/cuda/bin` on `PATH` (on Arch:
  `cuda`, with `/opt/cuda/bin`)
- `nvidia-container-toolkit` is registered with Docker, so
  `docker run --gpus all` works
- `nvtop` shows GPU load

`nvidia_driver_package` and `nvidia_cuda_package` select other packages, such
as `cuda-drivers` for older GPUs or `cuda-toolkit-12-8` to pin CUDA. On Arch,
`nvidia-open` is built for the `linux` kernel: use `nvidia-open-lts` for
`linux-lts`, or `nvidia-open-dkms` and the kernel's headers for any other.

On Fedora, NVIDIA's repository is selected using the Fedora release number.
The NVIDIA/CUDA setup requires x86_64.
The driver uses `kernel-devel-matched` and `kernel-headers`; WSL skips the
driver and kernel packages. CUDA uses `/usr/local/cuda/bin`, and the container
toolkit uses NVIDIA's separate RPM repository. A new Fedora release needs a
matching NVIDIA CUDA repository before `--nvidia` can be used.

To add a tool, put it in the matching list in `vars/main.yml`. For a
`curl | sh` installer, import `tasks/tool.yml` in `local.yml`, as is done for
rtk.

The Starship powerline prompt uses the official Dracula palette, with pink
identity and Git accents, a purple directory segment, cyan language segments,
and dark foregrounds on bright backgrounds. It suits the Dracula VS Code theme;
terminal and editor theme settings are managed separately.

## Supported systems

Ubuntu 24.04, Ubuntu 26.04, Debian 13, Arch Linux and Fedora 44, on a VM or under WSL2
with `systemd=true` in `/etc/wsl.conf` (snaps need systemd).
Snap installs and refreshes retry up to three times after a failure, with a
15-second delay between attempts, to tolerate temporary Snap Store errors.
macOS uses Homebrew on Apple Silicon (`arm64`) and Intel (`x86_64`); the macOS
version must meet [Homebrew's requirements](https://docs.brew.sh/Installation)
and those of the selected packages. Intel bottle availability varies by package.
The full default Linux installation requires x86_64: draw.io's Snap is unavailable
for ARM64. Fedora Atomic variants such as Silverblue are not supported.

On Ubuntu 26.04 root tasks run through `sudo.ws`, because Ansible cannot read
the password prompt of the default sudo-rs.

Bootstrap uses full Git checkouts to avoid an upstream Ansible shallow-fetch
regression on repeated detached-commit runs.

## Development

Run a working copy without pulling:

```bash
ansible-playbook local.yml --ask-become-pass
```

Every push to `main` runs [the test workflow](.github/workflows/test.yml):

- `ubuntu:24.04`, `ubuntu:26.04`, `debian:13`, `archlinux:base-20261101.0.620205`
  and `fedora:44` boot as
  clean systemd containers with a sudo password, install the full default
  set, must change nothing on a second run, and then execute every installed
  tool ([tests/check.sh](tests/check.sh)).
  The test user has a persistent systemd user manager and session bus so that
  snaps using `core26` can [track application processes](https://canonical.com/lxd/docs/default/reference/release-notes/6/release-notes-6.9/#strict-process-tracking-failures-with-core26-snap-base).
  FUSE is loaded on the runner before container creation so Fedora's Snap
  mounts can access `/dev/fuse`.
- The hosted Ubuntu 24.04 VM does the same without texlive-full, and builds
  the NVIDIA driver.
- The hosted macOS 15 runner executes the offline regression suite and installs
  a small Homebrew package set, GitHub CLI, Lazygit, shell configuration, Starship and fonts.
  It checks an unchanged rerun and both zsh and bash login shells. The full macOS
  package list, GUI applications and Colima VM startup are not covered by this job.

The Arch starting image is pinned by its SHA-256 digest in the workflow.
Provisioning still runs `pacman -Syu` to upgrade packages from current repositories.

Not covered: the driver on 26.04, Debian, Arch and Fedora, since containers share the
runner's kernel, and anything that needs a GPU. A manual run accepts extra
`bootstrap.sh` arguments, such as `--tags snap`.

### Distribution regression tests

On Linux or macOS with `ansible-core` installed, run:

```bash
bash -n bootstrap.sh tests/check.sh
ansible-playbook --syntax-check local.yml
python3 tests/test_distributions.py
python3 tests/test_snap.py
```

These offline tests exercise bootstrap package-manager selection, existing
prerequisites, sudo password handling and argument forwarding. Ansible evaluates
the real task conditions, tags and package arguments through a recording action,
covering Fedora exclusions, upgrades, Snap setup, NVIDIA/WSL routing, unsupported
distributions, macOS on both architectures, Homebrew exclusions and updates, Colima
startup, macOS shell/font paths, BSD sed, and the existing Ubuntu/Debian/Arch branches. CI runs these alongside
the real container installation and unchanged-rerun checks.
The suite also gathers real host facts before evaluating the task environment,
and checks the resulting paths for each supported distribution and macOS
architecture. Fact-dependent environment settings apply to the task block;
fact gathering uses the original process environment.
The Snap tests run the install and refresh tasks against a local fake command,
covering transient failures, exhausted retries, unchanged reruns and
`upgrade=false` without contacting the Snap Store.

Fedora setup references: [Docker RPM installation](https://docs.docker.com/engine/install/fedora/),
[NVIDIA driver installation](https://docs.nvidia.com/datacenter/tesla/driver-installation-guide/fedora.html),
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html),
and [Snap on Fedora](https://snapcraft.io/docs/tutorials/install-the-daemon/fedora/).

### Focused update tests

With Python 3.11+, `ansible-playbook`, `pnpm` and `starship` on `PATH`, run:

```bash
ansible-playbook --syntax-check local.yml
python3 tests/test_updates.py
```

These tests use temporary global package directories and a local npm registry.
They check an empty package set, single and multiple isolated global installs
(including a scoped package), direct and transitive version updates, unchanged
reruns, `upgrade=false`, check mode, and failed enumeration/deep-list/update
commands before or after an update. Starship is rendered
in a Git/Node project with successful and failed command statuses; warnings and
missing palette references fail the test. CI runs these tests with pnpm 11.25.0
and the latest installer version, alongside the existing full-machine tests.

References: [pnpm global packages](https://pnpm.io/global-packages),
[pnpm update](https://pnpm.io/cli/update),
[pnpm list](https://pnpm.io/cli/list),
[Ansible change/failure handling](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_error_handling.html),
[Starship configuration](https://starship.rs/config/), and the
[Dracula palette](https://github.com/dracula/dracula-theme#color-palette-oss).
