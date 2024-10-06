# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Guard against crashes caused by removing libvirt objects that are unrelated to the currently running operation. The affected operations were `domain-list`, `domain-clone`, `pool-list`, and `volume-list`.

## [0.1.0] - 2024-07-02

Initial release. Requires Python 3.10 and libvirt-python 9.0 or newer.

### Added

- Command `domain-list` to list all domains.
- Command `domain-clone` to clone a domain.
- Command `domain-iface-list` to list all network interfaces of a domain and their addresses.
- Command `guest-ping` to ping a guest.
- Command `guest-run` to run a program on a guest.
- Command `pool-list` to list all storage pools.
- Command `volume-list` to list all volumes of a storage pool.
- Command `volume-import` to import a volume into a storage pool.

[unreleased]: https://github.com/aahlenst/virtomate/compare/0.1.0...HEAD
[0.1.0]: https://github.com/aahlenst/virtomate/releases/tag/0.1.0
