#!/bin/sh -eux

echo "Enable password-less sudo for user virtomate"
echo 'virtomate ALL=(ALL) NOPASSWD:ALL' >/etc/sudoers.d/virtomate;
chmod 440 /etc/sudoers.d/virtomate;

# The predictable interface names (enp0s2, etc.) are unpredictable in this case because we do not know beforehand how
# the virtual machine using the image will be configured. Relying on the old numbering scheme (ethX) ensures that the
# machine will be reachable. The user can still re-enable predictable interface names.
echo "Restore old interface numbering scheme (ethX)"
sed -i 's/en[[:alnum:]]*/eth0/g' /etc/network/interfaces;
sed -i 's/GRUB_CMDLINE_LINUX="\(.*\)"/GRUB_CMDLINE_LINUX="net.ifnames=0 biosdevname=0 \1"/g' /etc/default/grub;
update-grub;

echo "Remove old kernel images"
dpkg --list \
    | awk '{ print $2 }' \
    | grep 'linux-image-[1-9].*' \
    | grep -v "$(uname -r)" \
    | xargs apt-get -y purge;

echo "Remove package installation-report"
apt-get -y purge installation-report;

echo "Remove apt caches"
apt-get clean
find /var/lib/apt/lists/ -type f -exec rm -f {} \;

echo "Truncate logs"
find /var/log -type f -exec truncate --size=0 {} \;

echo "Force generation of a new machine identifier during the next boot"
truncate -s 0 /etc/machine-id
if test -f /var/lib/dbus/machine-id
then
  truncate -s 0 /var/lib/dbus/machine-id
fi

echo "Force generation of a new random seed during the next boot"
rm -f /var/lib/systemd/random-seed

echo "Whiteout /"
dd if=/dev/zero of=/tmp/whitespace bs=1M || true;
rm /tmp/whitespace

echo "Whiteout /boot"
dd if=/dev/zero of=/boot/whitespace bs=1M || true;
rm /boot/whitespace

echo "Remove history"
rm -f /root/.bash_history
rm -f /root/.wget-hsts
export HISTSIZE=0
