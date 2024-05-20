packer {
  required_plugins {
    qemu = {
      source  = "github.com/hashicorp/qemu"
      version = "~> 1"
    }
  }
}

variable "cpus" {
  type    = number
  default = 1
}

variable "disk_size" {
  type    = number
  default = 8192
}

variable "memory" {
  type    = number
  default = 1024
}

source "qemu" "simple-uefi" {
  accelerator  = "kvm"
  # Debian's UEFI installer needs a different magic incantation than the BIOS installer to edit the boot options.
  # It appends `preseed/url=...` to the line `linux /install.amd/vmlinuz vga=700 --- quiet`.
  # See https://www.debian.org/releases/bullseye/amd64/apbs02.en.html for the kernel arguments and what they mean.
  boot_command = [
    "<wait><down>e<down><down><down><end>preseed/url=http://{{ .HTTPIP }}:{{ .HTTPPort }}/preseed.cfg ",
    "hostname={{ .Name }} priority=critical auto=true<f10>"
  ]
  boot_key_interval = "10ms"
  boot_wait         = "5s"
  communicator      = "ssh"
  disk_interface    = "virtio"
  disk_size         = "${var.disk_size}"
  format            = "qcow2"
  headless          = "true"
  http_directory    = "simple-uefi"
  iso_checksum      = "sha256:013f5b44670d81280b5b1bc02455842b250df2f0c6763398feb69af1a805a14f"
  iso_url           = "https://mirror.init7.net/debian-cd/12.5.0/amd64/iso-cd/debian-12.5.0-amd64-netinst.iso"
  efi_boot          = true
  cpus              = 1
  memory            = 1024
  machine_type      = "q35"
  output_directory  = "dist/simple-uefi"
  shutdown_command  = "echo 'virtomate' | sudo -S shutdown -P now"
  ssh_password      = "virtomate"
  ssh_timeout       = "4h"
  ssh_username      = "virtomate"
  vm_name           = "simple-uefi"
}

build {
  sources = ["source.qemu.simple-uefi"]
  provisioner "shell" {
    execute_command = "echo 'virtomate' | sudo -S sh -c '{{ .Vars }} {{ .Path }}'"
    script          = "simple-uefi/compact.sh"
  }
}
