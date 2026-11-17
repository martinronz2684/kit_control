#!/bin/bash -e
# Kit Control ins Image einbauen (läuft in pi-gen, Dateien liegen in files/src)
rm -rf "${ROOTFS_DIR}/tmp/kit-src"
mkdir -p "${ROOTFS_DIR}/tmp/kit-src"
cp -a files/src/. "${ROOTFS_DIR}/tmp/kit-src/"
on_chroot << 'CHROOT'
set -e
KIT_IN_IMAGE=1 bash /tmp/kit-src/install.sh
install -m 755 /tmp/kit-src/get.sh /usr/local/sbin/kit-update
cp /tmp/kit-src/VERSION /etc/kit/version
rm -rf /tmp/kit-src
CHROOT
