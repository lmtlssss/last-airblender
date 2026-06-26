# the last airblender

made with codex.

blender camera flight from an xbox controller.
record the pass. scrub the take. overwrite the bad tail. save the frame.
no cloud. no account. no weird launcher ritual.

```text
        ┌───────────────────────────────┐
        │  the last airblender          │
        ├───────────────────────────────┤
        │  xbox controller              │
        │        │                      │
        │        ▼                      │
        │  blender viewport             │
        │        │                      │
        │        ▼                      │
        │  airblender camera rig        │
        │        │                      │
        │        ├── keyframed takes    │
        │        └── png screenshots    │
        └───────────────────────────────┘
```

## install

### linux / macos

```bash
curl -fsSL https://raw.githubusercontent.com/lmtlssss/The-Last-AirBlender/main/install.sh | sh
```

inspect first if you want to see the wires:

```bash
curl -fsSLO https://raw.githubusercontent.com/lmtlssss/The-Last-AirBlender/main/install.sh
less install.sh
sh install.sh
```

pin a release:

```bash
LAST_AIRBLENDER_VERSION=v1.0.4 sh install.sh
```

### windows powershell

```powershell
irm https://raw.githubusercontent.com/lmtlssss/The-Last-AirBlender/main/install.ps1 | iex
```

inspect first:

```powershell
irm https://raw.githubusercontent.com/lmtlssss/The-Last-AirBlender/main/install.ps1 -OutFile install.ps1
notepad install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

### manual parts bin

pull the latest installer from github releases:

```text
.deb                         ubuntu / debian
.rpm                         fedora / rhel
.msi                         windows
.pkg                         macos
last-airblender-addon.zip    manual blender add-on
```

## runtime plate

open blender like normal.
plug in an xbox controller.
look for the small translucent **airblender** controller icon in the 3d viewport.

```text
┌─ blender viewport ─────────────────────────────────────────┐
│                                                           │
│   [ airblender ]  left click  : arm / activate fallback    │
│                  right click : native controls menu        │
│                                                           │
│   autosense finds the controller and arms the camera rig.  │
└───────────────────────────────────────────────────────────┘
```

normal use does not need a terminal.
the cli is for checks, packaging, and bridge fallback work:

```bash
last-airblender doctor
last-airblender launch your-scene.blend
```

## controller map

```text
┌────────────────────┬──────────────────────────────────────────────┐
│ control            │ action                                       │
├────────────────────┼──────────────────────────────────────────────┤
│ start / menu       │ cycle airblender + scene cameras             │
│ start double tap   │ create AirBlender_Cam_### at current view     │
│ start triple tap   │ delete current camera, arm the next usable    │
│ left stick x       │ strafe left / right                          │
│ left stick y       │ move forward / back along camera view         │
│ right stick        │ viewport-locked look                         │
│ rb / lb            │ rise / fall at 75% left-stick speed           │
│ rb / lb double tap │ auto rise / fall                             │
│ rb / lb while auto │ reverse auto direction                       │
│ rt / lt            │ camera roll                                  │
│ l3 + rt / lt       │ focal length                                 │
│ x                  │ speed: low / medium / high / xhigh           │
│ y                  │ invert look, roll, and rise/fall             │
│ a                  │ show / hide controls overlay                 │
│ b                  │ toggle third-person side pane                │
│ r3                 │ portrait / landscape camera frame            │
│ d-pad up           │ screenshot                                   │
│ d-pad down         │ record / stop / overwrite from scrub frame    │
│ d-pad left/right   │ scrub active take backward / forward          │
│ select / back      │ cycle take slots 1-10                        │
│ select double tap  │ jump to new / empty take slot                 │
└────────────────────┴──────────────────────────────────────────────┘
```

no remapping required.

## take deck

```text
01  plug in controller
02  open blender
03  airblender autosenses and arms
04  start double tap        -> make camera
05  fly the shot
06  d-pad down              -> record
07  fly the take
08  d-pad down              -> stop
09  d-pad left / right      -> scrub
10  d-pad down after scrub  -> trim future + overwrite
```

## screenshots

press d-pad up.
a camera-perspective png lands beside the saved `.blend`:

```text
<your-blend-folder>/last_airblender_screenshots/
```

## scene names

new v1.0 helpers use airblender names:

```text
AirBlender_Camera_Fleet
AirBlender_Airframe
AirBlender_Gimbal
AirBlender_Horizon
AirBlender_Cam_###
LAB_* actions and markers
```

old drone-flight scenes still load:

```text
Drone_Rig
Drone_Gimbal
Drone_Roll
DFR_* actions and markers
```

## doctor

```bash
last-airblender doctor
```

usual checks:

```text
blender not found       set BLENDER=/path/to/blender
controller not found    plug in the xbox controller and rerun doctor
linux permissions       install normally; make sure game controllers are readable
unsigned packages       v1.0.4 may trigger smartscreen / gatekeeper
```

## dev bench

```bash
cargo build --release
scripts/package-deb.sh
```

blender smoke test, on a machine with blender installed:

```bash
/snap/bin/blender --background --python tests/blender/smoke_dpad_scrub_after_stop.py
```
