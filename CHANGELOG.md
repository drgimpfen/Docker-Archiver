# Changelog

## [0.8.1] - 2025-12-26
### Fixed
- Startup race where scheduler tried to load schedules before DB schema was visible (added schema readiness check and scheduler resilience).

## [0.8.0] - 2025-12-25
### Added
- Release workflows for Docker Hub and GHCR including short tag generation (vMAJOR, vMAJOR.MINOR) and edge scheduled builds.
- `TROUBLESHOOTING.md` and `API.md` reference docs (moved content from README).

### Changed
- Bumped app version to **0.8.0**.
- Removed legacy `/local` stack discovery fallback and consolidated bind-mount guidance.
- Notifications module refactored into `helpers`, `sender`, `handlers`.

### Fixed
- Dashboard job status live update bug; improved polling behavior.

### CI
- Added `publish-release.yml` and `publish-edge.yml` workflows; granted packages write permission for GHCR publishing.
