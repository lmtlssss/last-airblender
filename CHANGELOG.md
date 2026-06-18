# Changelog

## v1.0.4

- Add Start/Menu triple-tap to safely delete the current camera while keeping AirBlender armed on the next usable camera.
- Update the baked controls docs and in-Blender overlays for the single/double/triple Start camera fleet gestures.

## v1.0.3

- Finalized the controller-first AirBlender flight workflow: A toggles the controller controls overlay, B toggles the third-person side pane, R3 toggles portrait/landscape, Select single-taps through takes and double-taps to a new/empty take, and Start cycles cameras in numeric order with a shorter double-tap window.
- Fixed live hotplug by requiring real `/dev/input/js*` connectivity on Linux instead of treating a waiting UDP bridge socket as a connected controller.
- Improved recording overwrite behavior after rewinding/scrubbing and added L3+trigger focal-length control with recorded lens keyframes.
- Added subtle drone-style inertia and visual bank lag while keeping the rig path level and responsive.
- Removed duplicate/header AirBlender controls; the bottom icon is status-only and controls are shown by the controller.

## v1.0.2

- Fixed Linux autosense sessions where a stale UDP bridge could outrank the real `/dev/input/js*` controller, leaving the AirBlender icon/status armed while physical buttons such as Start did nothing. Native Linux joystick input now wins whenever Blender can see it.

## v1.0.1

- Hotfix: autosense Xbox-compatible controllers from Blender startup and auto-arm AirBlender without clicking the icon.
- Fix floating icon label to read AirBlender.

## v1.0.0

- Add no-terminal Blender startup runtime with floating controller icon.
- Add icon left-click activation and right-click native controls menu.
- Add Start/Menu camera fleet controls: single tap cycles cameras, double tap creates AirBlender cameras.
- Canonicalize AirBlender naming while preserving legacy Drone/DFR scene compatibility.
- Install startup bootstrap into supported Blender version folders.


## v0.1.2

- Hotfix: Y is now one global invert toggle from a true no-invert stock baseline.

## v0.1.1

- Hotfix: restore true no-invert stock launch defaults so Y toggles right-stick/roll inversion from the expected baseline.

## v0.1.0

- Initial public release of The Last AirBlender.
- Blender camera flight with Xbox-style controller.
- Keyframed recording, take slots, scrub/overwrite, camera screenshots.
- Rust CLI installer, launcher, doctor, and controller bridge.
