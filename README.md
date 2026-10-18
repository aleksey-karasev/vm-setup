# vm-setup

Turns a clean Ubuntu, Debian or Arch Linux machine into a ready dev VM with one
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

## Update

```bash
vm-setup
```

Pulls the repo and applies it again, bringing system packages, snaps and every
tool to the newest version. Arguments go to `ansible-pull`:

```bash
vm-setup --tags uv,claude      # only some components
vm-setup --skip-tags apt,snap  # pacman on Arch
vm-setup -e upgrade=false      # install what is missing, upgrade nothing
```

## What is installed

| Tag | Installs | Source |
| --- | --- | --- |
| `apt` | ffmpeg, inkscape, pandoc, texlive-full, graphviz, ripgrep, duf, fd, bat, eza, fzf, jq, tree, hyperfine, tmux, sqlite3, git-lfs, 7zip, wget, rsync, zip, build-essential, cmake, pkg-config | apt |
| `snap` | drawio, btop, procs, dust, chromium | snap (chromium: apt on Debian) |
| `pacman` | on Arch, everything in the `apt` and `snap` rows, and bash-completion | pacman |
| `docker` | Docker Engine, buildx and compose plugins | Docker's apt repository (Arch: pacman) |
| `gh` | GitHub CLI | GitHub's apt repository (Arch: pacman) |
| `uv` | uv, Python 3.9 to 3.14, the tools in `uv_tools` | uv installer |
| `pnpm` | pnpm, Node.js | pnpm installer |
| `rtk`, `rclone`, `claude`, `duckdb`, `lazydocker` | rtk, rclone, Claude Code, DuckDB CLI, lazydocker | each tool's installer |
| `starship` | starship, its config and bash init | starship installer, `files/starship.toml` |
| `shell` | 100k-line bash history shared by all terminals, fzf key bindings in bash, Git LFS in `~/.gitconfig` | `.bashrc` lines and blocks, `git lfs install` |
| `fonts` | Nerd Fonts in `nerd_fonts` | latest GitHub release |
| `nvidia` | driver, CUDA toolkit, container toolkit, nvtop (opt-in) | NVIDIA's CUDA apt repository (Arch: pacman) |

`fd` and `bat` are linked into `~/.local/bin`, because apt installs them as
`fdfind` and `batcat`.

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
nerd_fonts: [JetBrainsMono, FiraCode]
```

`--nvidia` and `--no-nvidia` are remembered in that file. When enabled:

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

To add a tool, put it in the matching list in `vars/main.yml`. For a
`curl | sh` installer, import `tasks/tool.yml` in `local.yml`, as is done for
rtk.

## Supported systems

Ubuntu 24.04, Ubuntu 26.04, Debian 13 and Arch Linux, on a VM or under WSL2
with `systemd=true` in `/etc/wsl.conf` (snaps need systemd).

On Ubuntu 26.04 root tasks run through `sudo.ws`, because Ansible cannot read
the password prompt of the default sudo-rs.

## Development

Run a working copy without pulling:

```bash
ansible-playbook local.yml --ask-become-pass
```

Every push to `main` runs [the test workflow](.github/workflows/test.yml):

- `ubuntu:24.04`, `ubuntu:26.04`, `debian:13` and `archlinux:latest` boot as
  clean systemd containers with a sudo password, install the full default
  set, must change nothing on a second run, and then execute every installed
  tool ([tests/check.sh](tests/check.sh)).
- The hosted Ubuntu 24.04 VM does the same without texlive-full, and builds
  the NVIDIA driver.

Not covered: the driver on 26.04, Debian and Arch, since containers share the
runner's kernel, and anything that needs a GPU. A manual run accepts extra
`bootstrap.sh` arguments, such as `--tags snap`.
