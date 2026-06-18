# The Last AirBlender

Fly Blender's camera with an Xbox-style controller and record the take as animation.

**Made with Codex.**

The Last AirBlender gives Blender a fast cinematic camera-flight mode: pick up a controller, fly the scene camera, record the move as keyframes, scrub/overwrite takes, and save camera screenshots beside your `.blend`.

## Install

### Linux/macOS

```bash
curl -fsSL https://raw.githubusercontent.com/lmtlssss/The-Last-AirBlender/main/install.sh | sh
```

Safer inspect-first path:

```bash
curl -fsSLO https://raw.githubusercontent.com/lmtlssss/The-Last-AirBlender/main/install.sh
less install.sh
sh install.sh
```

Pin a version:

```bash
LAST_AIRBLENDER_VERSION=v1.0.2 sh install.sh
```

### Windows PowerShell

```powershell
irm https://raw.githubusercontent.com/lmtlssss/The-Last-AirBlender/main/install.ps1 | iex
```

Inspect-first path:

```powershell
irm https://raw.githubusercontent.com/lmtlssss/The-Last-AirBlender/main/install.ps1 -OutFile install.ps1
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

### Normal no-terminal Blender runtime

After install, open Blender normally. A small translucent controller icon labeled **AirBlender** appears in the 3D viewport. If an Xbox-compatible controller is visible to Blender, AirBlender autosenses it and arms camera flight automatically.

- **Autosense**: plugging in an Xbox-compatible controller automatically activates The Last AirBlender, creates/attaches the camera rig, and switches to the split camera/third-person layout.
- **Left-click the controller icon**: fallback manual activate if autosense has not armed yet.
- **Right-click the controller icon**: show the native controls menu.
- No terminal or background CLI is required for normal Blender use on systems where Blender can read the controller directly.

The CLI is still useful for install, doctor, packaging, and optional bridge fallback:

```bash
last-airblender doctor
last-airblender launch your-scene.blend   # optional bridge launcher
```

## Baked controls

| Control | Action |
|---|---|
| Start/Menu | Cycle available AirBlender/scene cameras |
| Start/Menu double-tap | Create a new `AirBlender_Cam_###` at the current flown/view transform |
| Left stick X | Strafe left/right |
| Left stick Y | Move forward/back along camera view |
| Right stick | Viewport-locked look |
| RB / LB | Rise / fall at 75% left-stick movement speed |
| RB / LB double-tap | Auto rise/fall |
| RB / LB tap while auto | Reverse auto direction |
| RT / LT | Camera roll |
| X | Low / medium / high / xhigh speed |
| Y | Global invert toggle: both sticks + roll direction |
| A | First/third-person view toggle |
| D-pad Up | Camera screenshot |
| D-pad Down | Record / stop / overwrite from scrubbed frame |
| D-pad Left/Right | Scrub active take backward/forward |
| Select / Back | Cycle take slots 1-10 |

No remapping is required for normal use.

## Recording workflow

1. Open Blender normally with the controller plugged in; AirBlender autosenses it and arms itself.
2. Use **Start/Menu double-tap** to create cameras, or **Start/Menu single tap** to cycle existing cameras.
3. Fly until it feels right.
4. Press **D-pad Down** to start recording.
5. Fly the shot.
6. Press **D-pad Down** again to stop.
7. Use **D-pad Left/Right** to scrub the active take.
8. If you scrub back and press **D-pad Down**, the future is trimmed and recording overwrites from that frame.

## Screenshots

D-pad Up saves a camera-perspective PNG beside the saved project:

```text
<your-blend-folder>/last_airblender_screenshots/
```

## Naming and compatibility

v1.0 uses canonical AirBlender names for new helpers:

- `AirBlender_Camera_Fleet`
- `AirBlender_Airframe`
- `AirBlender_Gimbal`
- `AirBlender_Horizon`
- `AirBlender_Cam_###`
- `LAB_*` actions and markers

Older scenes using `Drone_Rig`, `Drone_Gimbal`, `Drone_Roll`, or `DFR_*` actions/markers remain supported for compatibility.

## Troubleshooting

```bash
last-airblender doctor
```

Common issues:

- **Blender not found**: set `BLENDER=/path/to/blender`.
- **Controller not detected**: plug in an Xbox-compatible controller and rerun `doctor`.
- **Linux permissions**: install package normally and ensure your user can access game controllers.
- **Windows SmartScreen/macOS Gatekeeper**: v1.0.2 packages may be unsigned; use the inspect-first install path if preferred.

## Developer build

```bash
cargo build --release
scripts/package-deb.sh
```

Run Blender smoke tests from a machine with Blender installed:

```bash
/snap/bin/blender --background --python tests/blender/smoke_dpad_scrub_after_stop.py
```
