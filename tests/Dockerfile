ARG IMAGE
FROM ${IMAGE}

ARG USER_ID=1000

ENV container=docker

RUN if [ -e /etc/arch-release ]; then \
    pacman -Syu --noconfirm sudo diffutils \
    && echo '%wheel ALL=(ALL:ALL) ALL' >/etc/sudoers.d/wheel \
    && systemctl mask systemd-networkd-wait-online.service \
    && rm -rf /var/cache/pacman/pkg/* /var/lib/pacman/sync/* \
    && admin_group=wheel; \
    else \
    apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends systemd systemd-sysv dbus \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y sudo \
    && rm -rf /var/lib/apt/lists/* /usr/sbin/policy-rc.d \
    && admin_group=sudo; \
    fi \
    && existing_user="$(getent passwd "$USER_ID" | cut -d: -f1)" \
    && { [ -z "$existing_user" ] || userdel --remove "$existing_user"; } \
    && useradd --create-home --uid "$USER_ID" --groups "$admin_group" --shell /bin/bash dev \
    && echo 'dev:vm-setup' | chpasswd

RUN if [ -e /etc/dpkg/dpkg.cfg.d/excludes ]; then \
    echo 'path-include=/usr/share/doc/fzf/examples/*' >/etc/dpkg/dpkg.cfg.d/excludes-fzf; \
    fi

STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
