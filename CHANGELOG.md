# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Nothing yet.

### Changed

- Nothing yet.

### Fixed

- Nothing yet.

## [0.1.0] - 2025-09-25

The 0.1.0 release turns the project from a game-specific clicker into
**QuickScript Studio**, a general-purpose keyboard/mouse automation tool.

### Added

- **Four-layer architecture** for script execution: action layer (mouse and
  keyboard primitives), flow layer (wait / loop / label jump / stop),
  trigger layer (color and image conditions) and target layer (coordinate
  resolution against the screen or a bound window).
- **Script format v2**: scripts are now plain JSON carrying a `version` field,
  so future format revisions can be detected and migrated automatically.
- `docs/script-format.md` documenting every step type, its parameters and the
  on-disk JSON layout.
- **Per-step remarks**: every step can carry a free-text note that is shown in
  the step list and preserved across save / load / export.
- **Environment self-check** covering simulated-input availability, process
  privilege level (UIPI), IME state, and global hotkey occupancy.
- **Administrator launcher** for driving target programs that run with elevated
  privileges.
- **Open-source scaffolding**: `LICENSE`, `README`, `CONTRIBUTING.md` and the
  GitHub Actions build workflow.
- Capability list is now fully generic: mouse move (with duration and jitter),
  click (with press duration, repeat count and interval), drag and wheel;
  keyboard press (including combos such as `ctrl+shift+a`), key down / key up
  and key repeat; global hotkeys `F8` (pick coordinates), `F9` (run) and `F10`
  (emergency stop).

### Changed

- **Project renamed to QuickScript Studio** (previously a tool dedicated to one
  specific game).
- **Refactored from a game-specific tool into a generic keyboard/mouse
  automation tool**: the engine, GUI and script model no longer reference any
  particular game or website.
- **Script format upgraded from `schema: 1` to `version: 2`**; existing
  `schema: 1` scripts are migrated automatically on load.

### Removed

- Removed all game-related wording, examples and assets from the code base,
  the UI and the documentation.

### Fixed

- Elevation failed when the installation path contained Chinese characters.
- Target programs running as administrator could not be automated because of
  Windows UIPI restrictions.
- Chinese IME could swallow simulated key presses.
- UI elements were clipped at high DPI settings.

[Unreleased]: https://github.com/reeeezec/QuickScript-Studio/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/reeeezec/QuickScript-Studio/releases/tag/v0.1.0
