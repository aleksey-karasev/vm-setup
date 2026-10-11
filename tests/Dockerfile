ARG IMAGE
FROM ${IMAGE}

ARG USER_ID=1000

ENV container=docker

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends systemd systemd-sysv dbus \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y sudo \
    && rm -rf /var/lib/apt/lists/* /usr/sbin/policy-rc.d \
    && useradd --create-home --non-unique --uid "$USER_ID" --groups sudo --shell /bin/bash dev \
    && echo 'dev:vm-setup' | chpasswd

STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
