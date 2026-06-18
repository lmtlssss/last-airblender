# The Last AirBlender

Fly Blender's camera with an Xbox-style controller and record the take as animation.

**Made with Codex.**

The Last AirBlender gives Blender a fast cinematic camera-flight mode: pick up a controller, fly the scene camera, record the move as keyframes, scrub/overwrite takes, and save camera screenshots beside your `.blend`.

## Install

### Linux/macOS

```bash
curl -fsSL https://raw.githubusercontent.com/lmtlssss/last-airblender/main/install.sh | sh
```

Safer inspect-first path:

```bash
curl -fsSLO https://raw.githubusercontent.com/lmtlssss/last-airblender/main/install.sh
less install.sh
sh install.sh
```

Pin a version:

```bash
LAST_AIRBLENDER_VERSION=v0.1.1 sh install.sh
```

### Windows PowerShell

```powershell
irm https://raw.githubusercontent.com/lmtlssss/last-airblender/main/install.ps1 | iex
```

Inspect-first path:

```powershell
irm https://raw.githubusercontent.com/lmtlssss/last-airblender/main/install.ps1 -OutFile install.ps1
notepad install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

### Manual downloads

Download the latest native installer from GitHub Releases:

- Ubuntu/Debian: `.deb`
- Fedora/RHEL: `.rpm`
- Windows: `.msi`
- macOS: `.pkg`
- Manual Blender add-on ZIP: `last-airblender-addon.zip`

## Quick start

```bash
last-airblender doctor
last-airblender launch your-scene.blend
```

Then pick up the controller.

## Baked controls

| Control | Action |
|---|---|
| Left stick X | Strafe left/right |
| Left stick Y | Move forward/back along camera view |
| Right stick | Viewport-locked look |
| RB / LB | Rise / fall at 75% left-stick movement speed |
| RB / LB double-tap | Auto rise/fall |
| RB / LB tap while auto | Reverse auto direction |
| RT / LT | Camera roll |
| X | Low / medium / high / xhigh speed |
| Y | Right-stick + roll invert toggle |
| A | First/third-person view toggle |
| D-pad Up | Camera screenshot |
| D-pad Down | Record / stop / overwrite from scrubbed frame |
| D-pad Left/Right | Scrub active take backward/forward |
| Select / Back | Cycle take slots 1-10 |

No remapping is required for normal use.

## Recording workflow

1. Launch with `last-airblender launch scene.blend`.
2. Fly until it feels right.
3. Press **D-pad Down** to start recording.
4. Fly the shot.
5. Press **D-pad Down** again to stop.
6. Use **D-pad Left/Right** to scrub the active take.
7. If you scrub back and press **D-pad Down**, the future is trimmed and recording overwrites from that frame.

## Screenshots

D-pad Up saves a camera-perspective PNG beside the saved project:

```text
<your-blend-folder>/drone_flight_recorder_screenshots/
```

## Troubleshooting

```bash
last-airblender doctor
```

Common issues:

- **Blender not found**: set `BLENDER=/path/to/blender`.
- **Controller not detected**: plug in an Xbox-compatible controller and rerun `doctor`.
- **Linux permissions**: install package normally and ensure your user can access game controllers.
- **Windows SmartScreen/macOS Gatekeeper**: v0.1.0 packages may be unsigned; use the inspect-first install path if preferred.

## Developer build

```bash
cargo build --release
scripts/package-deb.sh
```

Run Blender smoke tests from a machine with Blender installed:

```bash
/snap/bin/blender --background --python tests/blender/smoke_dpad_scrub_after_stop.py
```
