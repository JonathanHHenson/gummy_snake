# Changelog

## Unreleased

### Added

- plugin registry with deterministic lifecycle and event hooks
- plugin API extension and cleanup support
- explicit golden and parity test layers
- user-facing getting started, lifecycle, backend, compatibility, events, images/pixels, plugin, testing, and release docs
- CI workflow and `Makefile` quality shortcuts
- `scripts/bump_version.py` helper and Makefile targets for synchronized package/crate version bumps

### Changed

- packaging metadata now includes richer classifier/keyword/build configuration
- package builds now use Maturin so published wheels include the required `p5.rust._canvas` extension for canvas-owned assets/rendering
- README now documents installation, examples, and development commands
