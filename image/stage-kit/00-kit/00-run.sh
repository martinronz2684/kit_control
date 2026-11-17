#!/bin/bash -e
# Kit Control ins Image einbauen (läuft in pi-gen, Dateien liegen in files/src)
rm -rf "${ROOTFS_DIR}/var/tmp/kit-src"
mkdir -p "${ROOTFS_DIR}/var/tmp/kit-src"
cp -a files/src/. "${ROOTFS_DIR}/var/tmp/kit-src/"
on_chroot << 'CHROOT'
set -e
KIT_IN_IMAGE=1 bash /var/tmp/kit-src/install.sh
install -m 755 /var/tmp/kit-src/get.sh /usr/local/sbin/kit-update
cp /var/tmp/kit-src/VERSION /etc/kit/version
rm -rf /var/tmp/kit-src
CHROOT
