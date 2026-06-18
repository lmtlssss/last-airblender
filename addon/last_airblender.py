bl_info = {
    "name": "The Last AirBlender",
    "author": "Codex",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > The Last AirBlender",
    "description": "Fly Blender cameras with an Xbox-style controller and record cinematic camera takes.",
    "category": "Animation",
}

import bpy
import math
import os
import glob
import time
import struct
import fcntl
import array
import json
import socket
from mathutils import Vector, Matrix, Quaternion
import blf

JS_EVENT_FORMAT = "IhBB"
JS_EVENT_SIZE = struct.calcsize(JS_EVENT_FORMAT)
JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS = 0x02
JS_EVENT_INIT = 0x80

LAB_PREFIX = "AirBlender"
LAB_COLLECTION_NAME = "AirBlender_Camera_Fleet"
LAB_RIG_NAME = "AirBlender_Airframe"
LAB_GIMBAL_NAME = "AirBlender_Gimbal"
LAB_ROLL_NAME = "AirBlender_Horizon"
LAB_CAMERA_PREFIX = "AirBlender_Cam"
LEGACY_RIG_NAME = "Drone_Rig"
LEGACY_GIMBAL_NAME = "Drone_Gimbal"
LEGACY_ROLL_NAME = "Drone_Roll"
ICON_RUNTIME_OPERATOR = "lab.icon_runtime"



def _jsiocgname(length):
    return 0x80006A13 | (length << 16)


class LinuxJoystickBackend:
    """Small swappable backend for Linux /dev/input/js* devices."""

    def __init__(self):
        self.fd = None
        self.path = ""
        self.name = ""
        self.axes = {}
        self.buttons = {}
        self.connected = False
        self.error = ""

    @staticmethod
    def list_devices():
        devices = []
        for path in sorted(glob.glob("/dev/input/js*")):
            name = "unknown"
            axes = 0
            buttons = 0
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                buf = bytearray(256)
                try:
                    fcntl.ioctl(fd, _jsiocgname(256), buf)
                    name = buf.split(bytes([0]), 1)[0].decode(errors="replace") or "unknown"
                except Exception:
                    pass
                try:
                    a = array.array("B", [0])
                    fcntl.ioctl(fd, 0x80016A11, a, True)
                    axes = int(a[0])
                except Exception:
                    pass
                try:
                    b = array.array("B", [0])
                    fcntl.ioctl(fd, 0x80016A12, b, True)
                    buttons = int(b[0])
                except Exception:
                    pass
                os.close(fd)
                devices.append((path, name, axes, buttons))
            except Exception as ex:
                devices.append((path, "unreadable: %s" % ex, 0, 0))
        return devices

    def open(self, preferred_path=""):
        self.close()
        candidates = self.list_devices()
        if preferred_path:
            candidates = [d for d in candidates if d[0] == preferred_path] + [d for d in candidates if d[0] != preferred_path]
        else:
            def score(d):
                hay = (d[0] + " " + d[1]).lower()
                if "keyd virtual" in hay or "pointer" in hay:
                    return 100
                if any(x in hay for x in ("x-box", "xbox", "microsoft", "controller", "pad", "gamepad")):
                    return -10
                return 0
            candidates = sorted(candidates, key=score)
        if not candidates:
            self.error = "No /dev/input/js* devices found"
            return False
        last_error = ""
        for path, name, axes, buttons in candidates:
            if "keyd virtual" in name.lower() and not preferred_path:
                continue
            try:
                self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                self.path = path
                self.name = name
                self.connected = True
                self.error = ""
                self.poll()  # consume init events and seed state
                return True
            except Exception as ex:
                last_error = "%s: %s" % (path, ex)
        self.error = last_error or "Could not open joystick"
        return False

    def close(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except Exception:
                pass
        self.fd = None
        self.connected = False

    def poll(self):
        if self.fd is None:
            self.connected = False
            return
        for _ in range(256):
            try:
                data = os.read(self.fd, JS_EVENT_SIZE)
                if len(data) != JS_EVENT_SIZE:
                    break
                _t, value, typ, number = struct.unpack(JS_EVENT_FORMAT, data)
                typ = typ & ~JS_EVENT_INIT
                if typ == JS_EVENT_AXIS:
                    self.axes[int(number)] = max(-1.0, min(1.0, float(value) / 32767.0))
                elif typ == JS_EVENT_BUTTON:
                    self.buttons[int(number)] = bool(value)
            except BlockingIOError:
                break
            except Exception as ex:
                self.error = str(ex)
                self.close()
                break

    def axis(self, idx, default=0.0):
        return float(self.axes.get(int(idx), default))

    def button(self, idx):
        return bool(self.buttons.get(int(idx), False))


class BridgeJoystickBackend:
    """Localhost UDP backend fed by the cross-platform Rust `last-airblender bridge`."""

    PORT = 8765

    def __init__(self):
        self.sock = None
        self.path = "udp://127.0.0.1:%d" % self.PORT
        self.name = "The Last AirBlender Bridge"
        self.axes = {}
        self.buttons = {}
        self.connected = False
        self.error = ""
        self.last_packet = 0.0

    def open(self, _preferred_path=""):
        self.close()
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("127.0.0.1", self.PORT))
            self.sock.setblocking(False)
            self.error = "waiting for bridge packets"
            return True
        except Exception as ex:
            self.error = str(ex)
            self.close()
            return False

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None
        self.connected = False

    def poll(self):
        if self.sock is None:
            self.connected = False
            return
        got = False
        for _ in range(64):
            try:
                data, _addr = self.sock.recvfrom(8192)
            except BlockingIOError:
                break
            except Exception as ex:
                self.error = str(ex)
                self.connected = False
                return
            try:
                pkt = json.loads(data.decode("utf-8", errors="replace"))
                self.axes = {
                    0: float(pkt.get("lx", 0.0)),
                    1: float(pkt.get("ly", 0.0)),
                    2: float(pkt.get("lt", -1.0)),
                    3: float(pkt.get("rx", 0.0)),
                    4: float(pkt.get("ry", 0.0)),
                    5: float(pkt.get("rt", -1.0)),
                    6: float(pkt.get("dpad_x", 0.0)),
                    7: float(pkt.get("dpad_y", 0.0)),
                }
                self.buttons = {
                    0: bool(pkt.get("a", False)),
                    1: bool(pkt.get("b", False)),
                    2: bool(pkt.get("x", False)),
                    3: bool(pkt.get("y", False)),
                    4: bool(pkt.get("lb", False)),
                    5: bool(pkt.get("rb", False)),
                    6: bool(pkt.get("select", False)),
                    7: bool(pkt.get("start", False)),
                }
                self.last_packet = time.monotonic()
                got = True
            except Exception as ex:
                self.error = "bad bridge packet: %s" % ex
        self.connected = (time.monotonic() - self.last_packet) < 1.0 if self.last_packet else False
        if got:
            self.error = ""

    def axis(self, idx, default=0.0):
        return float(self.axes.get(int(idx), default))

    def button(self, idx):
        return bool(self.buttons.get(int(idx), False))


class HybridJoystickBackend:
    """Prefer Rust bridge packets; fall back to Linux /dev/input/js* when available."""

    def __init__(self):
        self.bridge = BridgeJoystickBackend()
        self.linux = LinuxJoystickBackend()
        self.active = None
        self.path = ""
        self.name = ""
        self.connected = False
        self.error = ""

    def open(self, preferred_path=""):
        bridge_ok = self.bridge.open(preferred_path)
        linux_ok = self.linux.open(preferred_path) if os.name == "posix" else False
        if not bridge_ok and not linux_ok:
            self.error = self.bridge.error or self.linux.error or "no controller backend available"
            self.connected = False
            return False
        self.active = self.linux if linux_ok else self.bridge
        self._sync_status()
        return True

    def close(self):
        self.bridge.close()
        self.linux.close()
        self.active = None
        self.connected = False

    def _sync_status(self):
        if self.bridge.connected:
            self.active = self.bridge
        elif self.linux.connected:
            self.active = self.linux
        elif self.bridge.sock is not None:
            self.active = self.bridge
        self.path = getattr(self.active, "path", "") if self.active else ""
        self.name = getattr(self.active, "name", "") if self.active else ""
        self.connected = bool(getattr(self.active, "connected", False)) if self.active else False
        if self.bridge.sock is not None and not self.connected:
            # Keep waiting for Rust bridge packets instead of aborting immediately.
            self.connected = True
            self.path = self.bridge.path
            self.name = self.bridge.name
        self.error = getattr(self.active, "error", "") if self.active else ""

    def poll(self):
        self.bridge.poll()
        self.linux.poll()
        self._sync_status()

    def axis(self, idx, default=0.0):
        return self.active.axis(idx, default) if self.active else default

    def button(self, idx):
        return self.active.button(idx) if self.active else False


class DroneRuntime:
    def __init__(self):
        self.operator = None
        self.backend = HybridJoystickBackend()
        self.last_buttons = {}
        self.velocity = Vector((0, 0, 0))
        self.yaw_rate = 0.0
        self.last_time = time.monotonic()
        self.record_tick = 0
        self.last_key_loc = None
        self.last_key_rot = None
        self.last_key_gim = None
        self.status = "Idle"
        self.stop_requested = False
        self.filtered = {"lx": 0.0, "ly": 0.0, "rx": 0.0, "ry": 0.0, "lt": 0.0, "rt": 0.0}
        self.timer_running = False
        self.scene_name = ""
        self.pitch_angle = 0.0
        self.roll_angle = 0.0
        self.dpad_up_active = False
        self.dpad_down_active = False
        self.dpad_left_active = False
        self.dpad_right_active = False
        self.record_max_frame = 0
        self.record_rewound = False
        self.record_scrub_hold = False
        self.record_waiting_for_input = False
        self.auto_throttle = 0.0
        self.auto_throttle_level = 0
        self.last_bumper_tap = {}
        self.bumper_tap_count = {}
        self.active_take_slot = 1
        self.last_start_tap = -999.0
        self.pending_start_single = False
        self.pending_start_time = 0.0
        self.icon_draw_handler = None
        self.icon_running = False
        self.icon_region = (22, 22, 42, 42)



RUNTIME = DroneRuntime()
CONTROL_COMMAND_PATH = os.path.expanduser("~/Desktop/blender-drone-flight-recorder/control.command")
SCREENSHOT_DIR = os.path.expanduser("~/Desktop/blender-drone-flight-recorder/screenshots")
SCREENSHOT_FOLDER_NAME = "last_airblender_screenshots"
TAKE_SLOT_COUNT = 10


def _start_recording(scene):
    s = scene.drone_flight_recorder_settings
    ensure_take_actions(scene, int(s.active_take_slot))
    if not s.recording:
        if scene.frame_current < int(RUNTIME.record_max_frame) or RUNTIME.record_rewound or RUNTIME.record_scrub_hold:
            delete_recorded_keys_after_frame(scene, scene.frame_current, include_current=True)
        s.recording = True
        RUNTIME.record_tick = 0
        RUNTIME.record_max_frame = max(int(RUNTIME.record_max_frame), int(scene.frame_current))
        RUNTIME.record_rewound = False
        RUNTIME.record_scrub_hold = False
        RUNTIME.record_waiting_for_input = True
        RUNTIME.last_key_loc = None
        insert_record_key(scene, force=True)
        s.status = "REC | Take %d/%d" % (int(s.active_take_slot), TAKE_SLOT_COUNT)


def _stop_recording(scene):
    s = scene.drone_flight_recorder_settings
    if s.recording:
        insert_record_key(scene, force=True)
        s.recording = False
        RUNTIME.record_waiting_for_input = False
        s.status = "Stopped recording | Take %d/%d" % (int(s.active_take_slot), TAKE_SLOT_COUNT)


def _resume_recording_overwrite(scene):
    ensure_take_actions(scene, int(scene.drone_flight_recorder_settings.active_take_slot))
    delete_recorded_keys_after_frame(scene, scene.frame_current, include_current=True)
    RUNTIME.record_rewound = False
    RUNTIME.record_scrub_hold = False
    RUNTIME.record_waiting_for_input = True
    RUNTIME.record_tick = 0
    scene.drone_flight_recorder_settings.recording = True
    insert_record_key(scene, force=True)
    scene.drone_flight_recorder_settings.status = "REC overwrite | Take %d/%d | frame %d" % (int(scene.drone_flight_recorder_settings.active_take_slot), TAKE_SLOT_COUNT, int(scene.frame_current))


def process_control_command(scene):
    try:
        if not os.path.exists(CONTROL_COMMAND_PATH):
            return
        with open(CONTROL_COMMAND_PATH, "r", encoding="utf-8", errors="ignore") as f:
            cmd = f.read().strip().upper()
        try:
            os.remove(CONTROL_COMMAND_PATH)
        except OSError:
            pass
    except Exception:
        return
    if cmd in {"RECORD", "START_RECORDING", "START"}:
        _start_recording(scene)
        scene.drone_flight_recorder_settings.status = "REC via command file"
    elif cmd in {"STOP", "STOP_RECORDING", "END"}:
        _stop_recording(scene)
        scene.drone_flight_recorder_settings.status = "Recording stopped via command file"
    elif cmd in {"TOGGLE", "TOGGLE_RECORDING"}:
        if scene.drone_flight_recorder_settings.recording:
            _stop_recording(scene)
        else:
            _start_recording(scene)
    elif cmd in {"STOP_FLIGHT", "LAND"}:
        RUNTIME.stop_requested = True



def _find_view3d_context():
    wm = bpy.context.window_manager
    for window in wm.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            space = next((sp for sp in area.spaces if sp.type == "VIEW_3D"), None)
            if region and space and space.region_3d:
                return window, screen, area, region, space, space.region_3d
    return None


def _set_first_person_view(scene, enabled):
    s = scene.drone_flight_recorder_settings
    found = _find_view3d_context()
    if not found:
        s.first_person_view = bool(enabled)
        s.status = "View toggle queued: no 3D viewport context"
        return False
    _window, _screen, _area, _region, _space, rv3d = found
    rv3d.view_perspective = "CAMERA" if enabled else "PERSP"
    s.first_person_view = bool(enabled)
    s.status = "First-person camera view" if enabled else "Third-person viewport view"
    return True


def configure_drone_split_view_layout(context=None):
    """Default DFR UI mode: large camera viewport plus smaller 3rd-person viewport.

    This intentionally does not resize an already-arranged split screen; it assigns
    the expected roles to the existing 3D viewports so the user's saved layout stays
    exactly as arranged.
    """
    ctx = context or bpy.context
    screen = getattr(ctx, "screen", None)
    if screen is None and bpy.context.window_manager.windows:
        screen = bpy.context.window_manager.windows[0].screen
    if screen is None:
        return False
    view_areas = [a for a in screen.areas if a.type == "VIEW_3D"]
    if not view_areas:
        return False
    # In the user's preferred layout the left camera view is the largest 3D area.
    ranked = sorted(view_areas, key=lambda a: (a.width * a.height, -a.x), reverse=True)
    camera_area = ranked[0]
    perspective_area = ranked[1] if len(ranked) > 1 else None

    def region3d(area):
        space = next((sp for sp in area.spaces if sp.type == "VIEW_3D"), None)
        return space, getattr(space, "region_3d", None) if space else None

    cam_space, cam_r3d = region3d(camera_area)
    if cam_space and ctx.scene.camera:
        try:
            cam_space.camera = ctx.scene.camera
        except Exception:
            pass
    if cam_r3d:
        cam_r3d.view_perspective = "CAMERA"

    if perspective_area:
        persp_space, persp_r3d = region3d(perspective_area)
        if persp_r3d:
            persp_r3d.view_perspective = "PERSP"
            # Leave the user's current orbit/zoom intact; only ensure it is not camera view.
    return True


def _toggle_first_third_person(scene):
    s = scene.drone_flight_recorder_settings
    return _set_first_person_view(scene, not s.first_person_view)


def _drone_screenshot_base_dir(scene=None):
    """Canonical screenshot root: beside saved .blend, else Blender's // folder.

    If the blend has been saved, screenshots live next to it in a stable folder.
    If the blend is unsaved, Blender resolves // to its current/default save folder;
    only if that is unavailable do we fall back to the add-on workspace folder.
    """
    if bpy.data.filepath:
        base = os.path.dirname(bpy.path.abspath(bpy.data.filepath))
    else:
        try:
            base = bpy.path.abspath("//")
        except Exception:
            base = ""
        if not base:
            try:
                render_path = bpy.path.abspath((scene or bpy.context.scene).render.filepath)
                base = os.path.dirname(render_path) if render_path else ""
            except Exception:
                base = ""
        if not base:
            base = SCREENSHOT_DIR
    return os.path.join(os.path.abspath(os.path.expanduser(base)), SCREENSHOT_FOLDER_NAME)


def _drone_screenshot_path(scene):
    folder = _drone_screenshot_base_dir(scene)
    os.makedirs(folder, exist_ok=True)
    blend_name = os.path.splitext(os.path.basename(bpy.data.filepath))[0] if bpy.data.filepath else "unsaved_blend"
    safe_blend = "".join(c if (c.isalnum() or c in "_-") else "_" for c in blend_name)
    return os.path.join(folder, "%s_camera_%s_%03d.png" % (safe_blend, time.strftime("%Y%m%d_%H%M%S"), int((time.time() % 1.0) * 1000)))


def _capture_drone_screenshot(scene):
    path = _drone_screenshot_path(scene)
    s = scene.drone_flight_recorder_settings
    if not scene.camera:
        s.status = "Screenshot failed: no scene camera"
        return ""
    old_path = scene.render.filepath
    old_camera = scene.camera
    try:
        scene.camera = old_camera
        scene.render.filepath = path
        # view_context=False forces a camera-perspective OpenGL still instead of
        # grabbing the split-screen viewport area. This is fast enough for D-pad use
        # and produces the actual camera framing.
        bpy.ops.render.opengl(write_still=True, view_context=False)
        if not os.path.exists(path):
            raise RuntimeError("camera OpenGL screenshot did not create a file")
        s.last_screenshot_path = path
        s.status = "Camera screenshot saved: %s" % path
        return path
    except Exception as ex:
        # Last-resort fallback for background smoke tests or odd render contexts.
        try:
            img = bpy.data.images.new("Drone Screenshot Fallback", width=2, height=2, alpha=True)
            img.pixels = [0.02, 0.02, 0.02, 1.0] * 4
            img.filepath_raw = path
            img.file_format = "PNG"
            img.save()
            bpy.data.images.remove(img)
            s.last_screenshot_path = path
            s.status = "Screenshot fallback saved: %s" % path
            return path
        except Exception as ex2:
            s.status = "Screenshot failed: %s / fallback: %s" % (ex, ex2)
            return ""
    finally:
        scene.render.filepath = old_path
        scene.camera = old_camera


def _dpad_edge(axis_value, direction, last_active, deadzone=0.5):
    active = (axis_value * direction) > deadzone
    return active and not last_active, active

def settings(context):
    return context.scene.drone_flight_recorder_settings


def joystick_invert_mode_label(mode):
    return "ON" if int(mode) % 2 else "OFF"


def sensitivity_mode_label(settings_obj):
    labels = ("low", "medium", "high", "xhigh")
    idx = max(1, min(len(labels), int(settings_obj.global_sensitivity_level))) - 1
    return labels[idx]


GLOBAL_SENSITIVITY_MULTIPLIERS = (0.35, 0.80, 1.60, 3.10)
# Left stick needs to live one practical tier hotter than right-stick look.
# User calibration: the old X level-3 left-stick feel should happen at X level 2
# so left strafe/climb/descend matches right-stick steering fluency.
LEFT_STICK_SENSITIVITY_MULTIPLIERS = (1.20, 2.50, 5.00, 9.00)
BUMPER_VERTICAL_SPEED_FACTOR = 0.75


def global_sensitivity_multiplier(settings_obj):
    idx = max(1, min(len(GLOBAL_SENSITIVITY_MULTIPLIERS), int(settings_obj.global_sensitivity_level))) - 1
    return GLOBAL_SENSITIVITY_MULTIPLIERS[idx]


def left_stick_sensitivity_multiplier(settings_obj):
    idx = max(1, min(len(LEFT_STICK_SENSITIVITY_MULTIPLIERS), int(settings_obj.global_sensitivity_level))) - 1
    return LEFT_STICK_SENSITIVITY_MULTIPLIERS[idx]


def cycle_global_sensitivity(settings_obj):
    settings_obj.global_sensitivity_level = (int(settings_obj.global_sensitivity_level) % len(GLOBAL_SENSITIVITY_MULTIPLIERS)) + 1
    return settings_obj.global_sensitivity_level, global_sensitivity_multiplier(settings_obj)


def left_stick_movement_multiplier(settings_obj):
    # Offset left-stick movement one tier hotter than right-stick look.
    return left_stick_sensitivity_multiplier(settings_obj) * float(settings_obj.left_stick_gain)


def effective_toggle_invert(base_invert, mode, axis_name):
    # OFF is true stock/no-invert. ON is one global inverted-pilot toggle.
    # It flips both sticks; trigger/roll direction is flipped separately where
    # roll_input is computed.
    flip = bool(int(mode) % 2) and axis_name in {"left_x", "left_y", "right_x", "right_y"}
    return bool(base_invert) ^ flip


def toggle_joystick_invert_mode(settings_obj):
    settings_obj.joystick_invert_mode = 0 if int(settings_obj.joystick_invert_mode) % 2 else 1
    return joystick_invert_mode_label(settings_obj.joystick_invert_mode)


def deadzone_value(v, dz):
    av = abs(v)
    if av <= dz:
        return 0.0
    return math.copysign((av - dz) / max(0.0001, 1.0 - dz), v)


def smooth_value(old, new, rate, dt):
    if rate <= 0:
        return new
    alpha = 1.0 - math.exp(-rate * dt)
    return old + (new - old) * alpha


def _named_object(primary, legacy=None):
    return bpy.data.objects.get(primary) or (bpy.data.objects.get(legacy) if legacy else None)


def get_rig_objects():
    return _named_object(LAB_RIG_NAME, LEGACY_RIG_NAME), _named_object(LAB_GIMBAL_NAME, LEGACY_GIMBAL_NAME)


def get_roll_object():
    return _named_object(LAB_ROLL_NAME, LEGACY_ROLL_NAME)


def get_drone_anim_objects():
    rig, gimbal = get_rig_objects()
    roll = get_roll_object()
    return tuple(o for o in (rig, gimbal, roll) if o)


def ensure_lab_collection(context=None):
    context = context or bpy.context
    col = bpy.data.collections.get(LAB_COLLECTION_NAME)
    if col is None:
        col = bpy.data.collections.new(LAB_COLLECTION_NAME)
        context.scene.collection.children.link(col)
    return col


def _link_to_lab_collection(obj, context=None):
    col = ensure_lab_collection(context)
    if obj and obj.name not in col.objects:
        try:
            col.objects.link(obj)
        except RuntimeError:
            pass
    return obj


def iter_action_fcurves(action):
    if not action:
        return []
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        return list(legacy)
    curves = []
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for channelbag in getattr(strip, "channelbags", []):
                curves.extend(list(getattr(channelbag, "fcurves", [])))
    return curves


def remove_action_fcurve(action, fcurve):
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        legacy.remove(fcurve)
        return True
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for channelbag in getattr(strip, "channelbags", []):
                fc_collection = getattr(channelbag, "fcurves", None)
                if fc_collection is None:
                    continue
                for fc in list(fc_collection):
                    if fc == fcurve:
                        fc_collection.remove(fc)
                        return True
    return False

def ensure_linear_interpolation(obj):
    ad = obj.animation_data
    if not ad or not ad.action:
        return
    for fc in iter_action_fcurves(ad.action):
        if fc.data_path in {"location", "rotation_euler"}:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"


def delete_recorded_keys_after_frame(scene, frame, include_current=False):
    """Trim recorded keys after a rewind so the next flown branch replaces them."""
    removed = 0
    eps = 1e-4
    for obj in get_drone_anim_objects():
        ad = obj.animation_data
        if not ad or not ad.action:
            continue
        for fc in iter_action_fcurves(ad.action):
            if fc.data_path not in {"location", "rotation_euler"}:
                continue
            for kp in reversed(list(fc.keyframe_points)):
                if (kp.co.x >= frame - eps) if include_current else (kp.co.x > frame + eps):
                    fc.keyframe_points.remove(kp)
                    removed += 1
            try:
                fc.update()
            except Exception:
                pass
    # Remove DFR marker/key-pose markers in the discarded future.
    for m in list(scene.timeline_markers):
        if ((m.frame >= frame) if include_current else (m.frame > frame)) and (m.name.startswith("LAB_") or m.name.startswith("DFR_")):
            scene.timeline_markers.remove(m)
    RUNTIME.record_max_frame = min(RUNTIME.record_max_frame, int(frame))
    RUNTIME.last_key_loc = None
    RUNTIME.last_key_rot = None
    RUNTIME.last_key_gim = None
    roll = get_roll_object()
    if roll and "dfr_last_key_rot" in roll:
        del roll["dfr_last_key_rot"]
    return removed


def sync_runtime_from_rig_pose():
    rig, gimbal = get_rig_objects()
    roll = get_roll_object()
    if gimbal:
        RUNTIME.pitch_angle = float(gimbal.rotation_euler.x)
    if roll:
        RUNTIME.roll_angle = float(roll.rotation_euler.z) - float(roll.get("dfr_base_z", 0.0))
    if rig:
        RUNTIME.last_key_loc = rig.location.copy()
        RUNTIME.last_key_rot = Vector(tuple(rig.rotation_euler))
    if gimbal:
        RUNTIME.last_key_gim = Vector(tuple(gimbal.rotation_euler))
    if roll:
        roll["dfr_last_key_rot"] = tuple(roll.rotation_euler)


def pilot_has_control_input(yaw_input, pitch_input, strafe, vertical, roll_input, throttle):
    return any(abs(v) > 1e-4 for v in (yaw_input, pitch_input, strafe, vertical, roll_input, throttle))


def auto_throttle_magnitude_for_level(settings_obj, level=None):
    # Bumper automove no longer has its own speed ladder. It follows the
    # current X speed mode, so X is the single speed selector for sticks + auto rise/fall.
    return 1.0


def set_auto_throttle_level(settings_obj, direction, level=None):
    direction = 1.0 if direction >= 0 else -1.0
    RUNTIME.auto_throttle_level = int(settings_obj.global_sensitivity_level)
    RUNTIME.auto_throttle = direction * auto_throttle_magnitude_for_level(settings_obj, level)


def clear_auto_throttle_state():
    RUNTIME.auto_throttle = 0.0
    RUNTIME.auto_throttle_level = 0
    RUNTIME.last_bumper_tap = {}
    RUNTIME.bumper_tap_count = {}


def take_action_name(obj, slot):
    safe = "".join(c if (c.isalnum() or c in "_-") else "_" for c in obj.name)
    return "LAB_%s_Take_%02d" % (safe, max(1, min(TAKE_SLOT_COUNT, int(slot))))


def legacy_take_action_name(obj, slot):
    safe = "".join(c if (c.isalnum() or c in "_-") else "_" for c in obj.name)
    return "DFR_%s_Take_%02d" % (safe, max(1, min(TAKE_SLOT_COUNT, int(slot))))


def find_take_action(obj, slot):
    return bpy.data.actions.get(take_action_name(obj, slot)) or bpy.data.actions.get(legacy_take_action_name(obj, slot))


def action_has_keys(action):
    if not action:
        return False
    return any(len(fc.keyframe_points) > 0 for fc in iter_action_fcurves(action))


def ensure_take_actions(scene, slot=None):
    s = scene.drone_flight_recorder_settings
    slot = int(slot or s.active_take_slot)
    slot = max(1, min(TAKE_SLOT_COUNT, slot))
    s.active_take_slot = slot
    for obj in get_drone_anim_objects():
        obj.animation_data_create()
        name = take_action_name(obj, slot)
        action = find_take_action(obj, slot) or bpy.data.actions.new(name)
        action.use_fake_user = True
        obj.animation_data.action = action
    RUNTIME.active_take_slot = slot
    return slot


def active_take_has_keys(scene, slot=None):
    slot = int(slot or scene.drone_flight_recorder_settings.active_take_slot)
    for obj in get_drone_anim_objects():
        action = find_take_action(obj, slot)
        if action_has_keys(action):
            return True
    return False


def switch_take_slot(scene, slot):
    if scene.drone_flight_recorder_settings.recording:
        scene.drone_flight_recorder_settings.status = "Select ignored while recording"
        return False
    slot = max(1, min(TAKE_SLOT_COUNT, int(slot)))
    had_keys = active_take_has_keys(scene, slot)
    ensure_take_actions(scene, slot)
    if had_keys:
        scene.frame_set(scene.frame_start)
        bpy.context.view_layer.update()
        sync_runtime_from_rig_pose()
        RUNTIME.record_max_frame = max_recorded_frame_for_active_take()
    else:
        RUNTIME.record_max_frame = int(scene.frame_current)
        sync_runtime_from_rig_pose()
    scene.drone_flight_recorder_settings.status = "Take %d/%d selected%s" % (slot, TAKE_SLOT_COUNT, "" if had_keys else " (empty)")
    return True


def max_recorded_frame_for_active_take():
    max_frame = 0
    for obj in get_drone_anim_objects():
        ad = obj.animation_data
        action = ad.action if ad else None
        if not action:
            continue
        for fc in iter_action_fcurves(action):
            for kp in fc.keyframe_points:
                max_frame = max(max_frame, int(round(kp.co.x)))
    return max_frame


def capture_live_pose():
    rig, gimbal = get_rig_objects()
    roll = get_roll_object()
    return {
        "rig_loc": rig.location.copy() if rig else None,
        "rig_rot": rig.rotation_euler.copy() if rig else None,
        "gimbal_rot": gimbal.rotation_euler.copy() if gimbal else None,
        "roll_rot": roll.rotation_euler.copy() if roll else None,
        "pitch": RUNTIME.pitch_angle,
        "roll_angle": RUNTIME.roll_angle,
    }


def restore_live_pose(pose):
    rig, gimbal = get_rig_objects()
    roll = get_roll_object()
    if rig and pose.get("rig_loc") is not None:
        rig.location = pose["rig_loc"]
        rig.rotation_euler = pose["rig_rot"]
    if gimbal and pose.get("gimbal_rot") is not None:
        gimbal.rotation_euler = pose["gimbal_rot"]
    if roll and pose.get("roll_rot") is not None:
        roll.rotation_euler = pose["roll_rot"]
    RUNTIME.pitch_angle = float(pose.get("pitch", RUNTIME.pitch_angle))
    RUNTIME.roll_angle = float(pose.get("roll_angle", RUNTIME.roll_angle))
    try:
        bpy.context.view_layer.update()
        for area in getattr(bpy.context.screen, "areas", []):
            if area.type == "VIEW_3D":
                area.tag_redraw()
    except Exception:
        pass


def advance_recording_frame_keep_live(scene, next_frame):
    pose = capture_live_pose()
    scene.frame_set(int(next_frame))
    restore_live_pose(pose)


def insert_record_key(scene, force=False, marker=False):
    rig, gimbal = get_rig_objects()
    roll = get_roll_object()
    if not rig or not gimbal:
        return False
    s = scene.drone_flight_recorder_settings
    frame = scene.frame_current
    loc = rig.location.copy()
    rot = Vector(tuple(rig.rotation_euler))
    gim = Vector(tuple(gimbal.rotation_euler))
    rol = Vector(tuple(roll.rotation_euler)) if roll else Vector((0.0, 0.0, 0.0))
    threshold = s.keyframe_threshold
    changed = force
    if RUNTIME.last_key_loc is None:
        changed = True
    else:
        changed = changed or (loc - RUNTIME.last_key_loc).length >= threshold
        changed = changed or (rot - RUNTIME.last_key_rot).length >= threshold * 0.25
        changed = changed or (gim - RUNTIME.last_key_gim).length >= threshold * 0.25
        if roll:
            changed = changed or (rol - Vector(tuple(roll.get("dfr_last_key_rot", (0.0, 0.0, 0.0))))).length >= threshold * 0.25
    if not changed:
        return False
    rig.keyframe_insert(data_path="location", frame=frame)
    rig.keyframe_insert(data_path="rotation_euler", frame=frame)
    gimbal.keyframe_insert(data_path="rotation_euler", frame=frame)
    if roll:
        roll.keyframe_insert(data_path="rotation_euler", frame=frame)
        ensure_linear_interpolation(roll)
        roll["dfr_last_key_rot"] = tuple(rol)
    ensure_linear_interpolation(rig)
    ensure_linear_interpolation(gimbal)
    RUNTIME.last_key_loc = loc
    RUNTIME.last_key_rot = rot
    RUNTIME.last_key_gim = gim
    if s.recording:
        RUNTIME.record_max_frame = max(int(RUNTIME.record_max_frame), int(frame))
    if marker:
        m = scene.timeline_markers.new("LAB_KeyPose_%d" % frame, frame=frame)
        m.camera = scene.camera
    return True


class DroneFlightSettings(bpy.types.PropertyGroup):
    controller_device: bpy.props.StringProperty(name="Controller Device", default="/dev/input/js0")
    controller_connected: bpy.props.BoolProperty(name="Controller Connected", default=False)
    recording: bpy.props.BoolProperty(name="Recording", default=False)
    status: bpy.props.StringProperty(name="Status", default="Idle")
    first_person_view: bpy.props.BoolProperty(name="First Person View", default=False)
    last_screenshot_path: bpy.props.StringProperty(name="Last Screenshot", default="")
    joystick_invert_mode: bpy.props.IntProperty(name="Joystick Invert", default=0, min=0, max=1)
    active_take_slot: bpy.props.IntProperty(name="Active Take", default=1, min=1, max=10)
    start_double_tap_window: bpy.props.FloatProperty(name="Start Double Tap sec", default=0.35, min=0.05, max=1.5)

    max_speed: bpy.props.FloatProperty(name="Max Speed", default=2.0, min=0.01, soft_max=20.0, unit="VELOCITY")
    vertical_speed: bpy.props.FloatProperty(name="Vertical Speed", default=1.2, min=0.01, soft_max=10.0)
    global_sensitivity_level: bpy.props.IntProperty(name="X Global Sensitivity", default=2, min=1, max=4)
    left_stick_gain: bpy.props.FloatProperty(name="Left Stick Gain", default=1.0, min=0.25, soft_max=16.0)
    yaw_speed: bpy.props.FloatProperty(name="Yaw Speed deg/s", default=70.0, min=1.0, soft_max=360.0)
    gimbal_speed: bpy.props.FloatProperty(name="Gimbal Speed deg/s", default=55.0, min=1.0, soft_max=180.0)
    roll_speed: bpy.props.FloatProperty(name="Roll Speed deg/s", default=70.0, min=1.0, soft_max=360.0)
    roll_auto_level: bpy.props.BoolProperty(name="Auto-Level Roll", default=False)
    roll_return_speed: bpy.props.FloatProperty(name="Roll Return deg/s", default=120.0, min=1.0, soft_max=720.0)
    bumper_double_tap_window: bpy.props.FloatProperty(name="Bumper Multi-Tap Window sec", default=0.35, min=0.05, max=1.5)
    auto_throttle_speed_levels: bpy.props.IntProperty(name="Automove Speed Levels", default=6, min=1, max=12)
    auto_throttle_min_multiplier: bpy.props.FloatProperty(name="Automove Slow Mult", default=0.25, min=0.01, max=1.0)
    manual_bumper_thrust_multiplier: bpy.props.FloatProperty(name="Manual Bumper Thrust Mult", default=1.0, min=0.01, max=1.0)
    auto_throttle_max_multiplier: bpy.props.FloatProperty(name="Automove Fast Mult", default=2.5, min=1.0, soft_max=8.0)
    unlimited_pitch: bpy.props.BoolProperty(name="Unlimited Pitch Orbit", default=True)
    acceleration: bpy.props.FloatProperty(name="Acceleration", default=45.0, min=0.01, soft_max=160.0)
    drag: bpy.props.FloatProperty(name="Drag", default=1.2, min=0.0, soft_max=20.0)
    deadzone: bpy.props.FloatProperty(name="Deadzone", default=0.12, min=0.0, max=0.8)
    smoothing: bpy.props.FloatProperty(name="Smoothing", default=10.0, min=0.0, soft_max=30.0)
    banking: bpy.props.FloatProperty(name="Banking deg", default=7.0, min=0.0, soft_max=45.0)
    precision_multiplier: bpy.props.FloatProperty(name="Precision Mult", default=0.25, min=0.01, max=1.0)
    boost_multiplier: bpy.props.FloatProperty(name="Boost Mult", default=2.5, min=1.0, soft_max=8.0)
    keyframe_interval: bpy.props.IntProperty(name="Keyframe Interval", default=1, min=1, soft_max=30)
    keyframe_threshold: bpy.props.FloatProperty(name="Key Threshold", default=0.002, min=0.0, soft_max=0.2)

    axis_left_x: bpy.props.IntProperty(name="Axis Left X", default=0, min=0, max=31)
    axis_left_y: bpy.props.IntProperty(name="Axis Left Y", default=1, min=0, max=31)
    axis_right_x: bpy.props.IntProperty(name="Axis Right X", default=3, min=0, max=31)
    axis_right_y: bpy.props.IntProperty(name="Axis Right Y", default=4, min=0, max=31)
    axis_left_trigger: bpy.props.IntProperty(name="Axis LT", default=2, min=0, max=31)
    axis_right_trigger: bpy.props.IntProperty(name="Axis RT", default=5, min=0, max=31)
    axis_dpad_y: bpy.props.IntProperty(name="Axis D-pad Y", default=7, min=0, max=31)
    axis_dpad_x: bpy.props.IntProperty(name="Axis D-pad X", default=6, min=0, max=31)
    dpad_up_direction: bpy.props.IntProperty(name="D-pad Up Direction", default=-1, min=-1, max=1)
    dpad_down_direction: bpy.props.IntProperty(name="D-pad Down Direction", default=1, min=-1, max=1)
    dpad_left_direction: bpy.props.IntProperty(name="D-pad Left Direction", default=-1, min=-1, max=1)
    dpad_right_direction: bpy.props.IntProperty(name="D-pad Right Direction", default=1, min=-1, max=1)
    record_scrub_frames_per_tick: bpy.props.IntProperty(name="Record Rewind/Fwd Frames", default=2, min=1, max=24)

    invert_left_y: bpy.props.BoolProperty(name="Invert Left Y", default=False)
    invert_right_y: bpy.props.BoolProperty(name="Invert Right Y", default=False)
    invert_left_x: bpy.props.BoolProperty(name="Invert Left X", default=False)
    invert_right_x: bpy.props.BoolProperty(name="Invert Right X", default=False)

    button_a: bpy.props.IntProperty(name="Button A", default=0, min=0, max=63)
    button_b: bpy.props.IntProperty(name="Button B", default=1, min=0, max=63)
    button_x: bpy.props.IntProperty(name="Button X", default=2, min=0, max=63)
    button_y: bpy.props.IntProperty(name="Button Y", default=3, min=0, max=63)
    button_lb: bpy.props.IntProperty(name="Button LB", default=4, min=0, max=63)
    button_rb: bpy.props.IntProperty(name="Button RB", default=5, min=0, max=63)
    button_select: bpy.props.IntProperty(name="Button Select/Back", default=6, min=0, max=63)
    button_start: bpy.props.IntProperty(name="Button Start/Menu", default=7, min=0, max=63)

    show_mapping: bpy.props.BoolProperty(name="Show Mapping", default=False)


class DFR_OT_create_rig(bpy.types.Operator):
    bl_idname = "dfr.create_rig"
    bl_label = "Create AirBlender Camera Rig"
    bl_description = "Create AirBlender_Airframe and AirBlender_Gimbal and parent the active scene camera while preserving its world transform"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        cam = scene.camera or (context.object if context.object and context.object.type == "CAMERA" else None)
        if not cam:
            self.report({"ERROR"}, "No active scene camera found")
            return {"CANCELLED"}
        cam_world = cam.matrix_world.copy()
        forward = cam_world.to_quaternion() @ Vector((0, 0, -1))
        if abs(forward.x) + abs(forward.y) < 1e-5:
            yaw = cam.rotation_euler.z
        else:
            yaw = math.atan2(forward.x, -forward.y)

        rig = bpy.data.objects.get(LAB_RIG_NAME) or bpy.data.objects.get(LEGACY_RIG_NAME)
        if rig is None:
            rig = bpy.data.objects.new(LAB_RIG_NAME, None)
            context.collection.objects.link(rig)
            rig.empty_display_type = "ARROWS"
            rig.empty_display_size = 0.8
        rig.rotation_mode = "XYZ"
        rig.location = cam_world.translation
        rig.rotation_euler = (0.0, 0.0, yaw)
        rig.scale = (1.0, 1.0, 1.0)
        context.view_layer.update()

        gimbal = bpy.data.objects.get(LAB_GIMBAL_NAME) or bpy.data.objects.get(LEGACY_GIMBAL_NAME)
        if gimbal is None:
            gimbal = bpy.data.objects.new(LAB_GIMBAL_NAME, None)
            context.collection.objects.link(gimbal)
            gimbal.empty_display_type = "SINGLE_ARROW"
            gimbal.empty_display_size = 0.45
        gimbal.rotation_mode = "XYZ"
        gimbal.parent = rig
        gimbal.matrix_parent_inverse.identity()
        context.view_layer.update()
        # Make the gimbal exactly occupy the camera world transform, so the
        # camera can become a zeroed child while the visible view is preserved.
        gimbal.matrix_world = cam_world
        context.view_layer.update()
        gimbal["dfr_base_x"] = float(gimbal.rotation_euler.x)
        gimbal["dfr_base_y"] = float(gimbal.rotation_euler.y)
        gimbal["dfr_base_z"] = float(gimbal.rotation_euler.z)
        RUNTIME.pitch_angle = float(gimbal.rotation_euler.x)

        roll = bpy.data.objects.get(LAB_ROLL_NAME) or bpy.data.objects.get(LEGACY_ROLL_NAME)
        if roll is None:
            roll = bpy.data.objects.new(LAB_ROLL_NAME, None)
            context.collection.objects.link(roll)
            roll.empty_display_type = "PLAIN_AXES"
            roll.empty_display_size = 0.3
        roll.rotation_mode = "XYZ"
        roll.parent = gimbal
        roll.matrix_parent_inverse.identity()
        context.view_layer.update()
        # Roll node sits exactly on the camera view transform. The camera is a
        # zeroed child; rotating Drone_Roll around local Z is true barrel roll
        # around the optical/view axis, not yaw/steer.
        roll.matrix_world = cam_world
        context.view_layer.update()
        roll["dfr_base_z"] = float(roll.rotation_euler.z)
        RUNTIME.roll_angle = 0.0

        cam.parent = roll
        cam.matrix_parent_inverse.identity()
        cam.matrix_basis.identity()
        context.view_layer.update()
        cam.matrix_world = cam_world
        context.view_layer.update()
        scene.camera = cam
        cam["lab_camera"] = True
        _link_to_lab_collection(rig, context)
        _link_to_lab_collection(gimbal, context)
        _link_to_lab_collection(roll, context)
        self.report({"INFO"}, "AirBlender rig ready for camera %s" % cam.name)
        return {"FINISHED"}



def lab_cameras(scene):
    cams = [o for o in bpy.data.objects if o.type == "CAMERA"]
    tagged = sorted([c for c in cams if c.get("lab_camera")], key=lambda o: o.name)
    untagged = sorted([c for c in cams if not c.get("lab_camera")], key=lambda o: o.name)
    return tagged + untagged


def active_view_matrix(context=None):
    context = context or bpy.context
    found = _find_view3d_context()
    if found:
        _window, _screen, _area, _region, _space, rv3d = found
        try:
            return rv3d.view_matrix.inverted()
        except Exception:
            pass
    cam = context.scene.camera
    return cam.matrix_world.copy() if cam else Matrix.Identity(4)


def _detach_camera_preserve_world(cam):
    if not cam:
        return
    mw = cam.matrix_world.copy()
    cam.parent = None
    cam.matrix_parent_inverse.identity()
    cam.matrix_world = mw


def _active_camera_world(scene):
    cam = scene.camera
    if cam:
        return cam.matrix_world.copy()
    return active_view_matrix()


def create_airblender_camera(scene, context=None):
    context = context or bpy.context
    old = scene.camera
    mw = _active_camera_world(scene)
    if old and old.type == "CAMERA":
        old["lab_camera"] = True
        _detach_camera_preserve_world(old)
    idx = 1
    while bpy.data.objects.get("%s_%03d" % (LAB_CAMERA_PREFIX, idx)):
        idx += 1
    cam_data = bpy.data.cameras.new("%s_%03d_Data" % (LAB_CAMERA_PREFIX, idx))
    cam = bpy.data.objects.new("%s_%03d" % (LAB_CAMERA_PREFIX, idx), cam_data)
    cam.matrix_world = mw
    cam["lab_camera"] = True
    ensure_lab_collection(context).objects.link(cam)
    scene.camera = cam
    bpy.ops.dfr.create_rig()
    scene.drone_flight_recorder_settings.status = "Created %s" % cam.name
    return cam


def switch_airblender_camera(scene, direction=1, context=None):
    context = context or bpy.context
    cams = lab_cameras(scene)
    if not cams:
        return create_airblender_camera(scene, context)
    current = scene.camera
    if current and current.type == "CAMERA":
        current["lab_camera"] = True
        _detach_camera_preserve_world(current)
    try:
        idx = cams.index(current)
    except ValueError:
        idx = -1 if direction > 0 else 0
    cam = cams[(idx + direction) % len(cams)]
    scene.camera = cam
    bpy.ops.dfr.create_rig()
    scene.drone_flight_recorder_settings.status = "Camera %d/%d: %s" % (((idx + direction) % len(cams)) + 1, len(cams), cam.name)
    return cam


def handle_start_button_edge(scene, now):
    s = scene.drone_flight_recorder_settings
    if s.recording:
        s.status = "Finish recording before switching cameras"
        RUNTIME.pending_start_single = False
        return
    window = max(0.05, float(s.start_double_tap_window))
    if (now - RUNTIME.last_start_tap) <= window:
        RUNTIME.pending_start_single = False
        RUNTIME.last_start_tap = -999.0
        create_airblender_camera(scene, bpy.context)
    else:
        RUNTIME.pending_start_single = True
        RUNTIME.pending_start_time = now
        RUNTIME.last_start_tap = now


def process_pending_start_single(scene, now):
    if not RUNTIME.pending_start_single:
        return
    window = max(0.05, float(scene.drone_flight_recorder_settings.start_double_tap_window))
    if (now - RUNTIME.pending_start_time) >= window:
        RUNTIME.pending_start_single = False
        switch_airblender_camera(scene, 1, bpy.context)


def _trigger_value(v, deadzone):
    """Linux js trigger axes are usually -1 released -> +1 pressed."""
    out = max(0.0, min(1.0, (float(v) + 1.0) * 0.5))
    return 0.0 if out < deadzone else out


def _flight_step(scene):
    s = scene.drone_flight_recorder_settings
    now = time.monotonic()
    dt = max(0.0001, min(0.1, now - RUNTIME.last_time))
    RUNTIME.last_time = now
    rig, gimbal = get_rig_objects()
    roll = get_roll_object()
    if not rig or not gimbal:
        s.status = "Stopped: missing AirBlender rig/gimbal"
        RUNTIME.stop_requested = True
        return
    RUNTIME.backend.poll()
    s.controller_connected = RUNTIME.backend.connected
    if not RUNTIME.backend.connected:
        s.status = "Controller disconnected: " + RUNTIME.backend.error
        RUNTIME.stop_requested = True
        return
    process_control_command(scene)

    b = RUNTIME.backend.button
    def edge(idx):
        val = b(idx)
        old = RUNTIME.last_buttons.get(idx, False)
        RUNTIME.last_buttons[idx] = val
        return val and not old

    if edge(s.button_a):
        _toggle_first_third_person(scene)
    if edge(s.button_select):
        if s.recording:
            s.status = "Select ignored while recording"
        else:
            switch_take_slot(scene, (int(s.active_take_slot) % TAKE_SLOT_COUNT) + 1)
    if edge(s.button_start):
        handle_start_button_edge(scene, now)
    process_pending_start_single(scene, now)

    dpad_y = RUNTIME.backend.axis(s.axis_dpad_y)
    up_edge, RUNTIME.dpad_up_active = _dpad_edge(dpad_y, s.dpad_up_direction or -1, RUNTIME.dpad_up_active)
    down_edge, RUNTIME.dpad_down_active = _dpad_edge(dpad_y, s.dpad_down_direction or 1, RUNTIME.dpad_down_active)
    if up_edge:
        _capture_drone_screenshot(scene)
        return
    if down_edge:
        if s.recording and (RUNTIME.record_scrub_hold or RUNTIME.record_rewound):
            _resume_recording_overwrite(scene)
        elif s.recording:
            _stop_recording(scene)
        else:
            _start_recording(scene)
        return

    # While recording, D-pad Left/Right behaves like a racing-game live-track
    # rewind/forward. It scrubs through already-recorded frames without writing
    # new keys; once the pilot flies from a rewound frame, future keys are cut.
    dpad_x = RUNTIME.backend.axis(s.axis_dpad_x)
    left_active = (dpad_x * (s.dpad_left_direction or -1)) > 0.5
    right_active = (dpad_x * (s.dpad_right_direction or 1)) > 0.5
    record_scrub_active = False
    scrub_available = s.recording or active_take_has_keys(scene, int(s.active_take_slot)) or int(RUNTIME.record_max_frame) > int(scene.frame_start)
    if scrub_available and (left_active or right_active):
        step = max(1, int(s.record_scrub_frames_per_tick))
        cur = int(scene.frame_current)
        take_max = max_recorded_frame_for_active_take()
        max_frame = max(int(RUNTIME.record_max_frame), int(take_max), cur if s.recording else int(scene.frame_start))
        if left_active and not right_active:
            target = max(int(scene.frame_start), cur - step)
            if target < cur:
                RUNTIME.record_rewound = True
                RUNTIME.record_scrub_hold = True
        elif right_active and not left_active:
            target = min(max_frame, cur + step)
            RUNTIME.record_scrub_hold = True
        else:
            target = cur
        if target != cur:
            scene.frame_set(target)
            bpy.context.view_layer.update()
            sync_runtime_from_rig_pose()
        RUNTIME.velocity = Vector((0, 0, 0))
        RUNTIME.yaw_rate = 0.0
        RUNTIME.auto_throttle = 0.0
        RUNTIME.auto_throttle_level = 0
        record_scrub_active = True
        RUNTIME.record_max_frame = max(int(RUNTIME.record_max_frame), int(max_frame))
        s.status = "%s | D-pad %s track %d/%d" % ("REC" if s.recording else "PLAY", "LEFT rewind" if left_active else "RIGHT forward", scene.frame_current, RUNTIME.record_max_frame)
        return

    if edge(s.button_x):
        level, mul = cycle_global_sensitivity(s)
        s.status = "Global sensitivity L%d x%.2f" % (level, mul)
    if edge(s.button_y):
        label = toggle_joystick_invert_mode(s)
        s.status = "Joystick invert: " + label

    lb_edge = edge(s.button_lb)
    rb_edge = edge(s.button_rb)

    def bumper_auto_tap(button_idx, direction):
        if direction == 0.0:
            return
        direction = 1.0 if direction > 0.0 else -1.0
        last = RUNTIME.last_bumper_tap.get(button_idx, -999.0)
        window = max(0.05, float(s.bumper_double_tap_window))
        is_double = (now - last) <= window
        current_dir = 1.0 if RUNTIME.auto_throttle > 0.0 else (-1.0 if RUNTIME.auto_throttle < 0.0 else 0.0)

        if abs(RUNTIME.auto_throttle) <= 0.0:
            # Automove off: double-tap either bumper starts auto rise/fall in
            # that bumper's direction. Speed follows the current X mode.
            if is_double:
                set_auto_throttle_level(s, direction)
                RUNTIME.last_bumper_tap = {}
            else:
                RUNTIME.last_bumper_tap = {button_idx: now}
            RUNTIME.bumper_tap_count = {}
            return

        # Automove on: every bumper tap reverses direction. No old per-bumper
        # speed cycling; X is now the only speed selector.
        set_auto_throttle_level(s, -current_dir if current_dir else direction)
        RUNTIME.last_bumper_tap = {button_idx: now}
        RUNTIME.bumper_tap_count = {}

    if rb_edge:
        bumper_auto_tap(s.button_rb, 1.0)
    if lb_edge:
        bumper_auto_tap(s.button_lb, -1.0)

    brake = b(s.button_b)
    button_back = b(s.button_lb)
    button_forward = b(s.button_rb)
    if button_back and button_forward:
        clear_auto_throttle_state()
    mult = 1.0

    def ax(idx, inv=False):
        v = RUNTIME.backend.axis(idx)
        if inv:
            v = -v
        return deadzone_value(v, s.deadzone)

    raw = {
        "lx": ax(s.axis_left_x, effective_toggle_invert(s.invert_left_x, s.joystick_invert_mode, "left_x")),
        "ly": ax(s.axis_left_y, effective_toggle_invert(s.invert_left_y, s.joystick_invert_mode, "left_y")),
        "rx": ax(s.axis_right_x, effective_toggle_invert(s.invert_right_x, s.joystick_invert_mode, "right_x")),
        "ry": ax(s.axis_right_y, effective_toggle_invert(s.invert_right_y, s.joystick_invert_mode, "right_y")),
        "lt": _trigger_value(RUNTIME.backend.axis(s.axis_left_trigger), s.deadzone),
        "rt": _trigger_value(RUNTIME.backend.axis(s.axis_right_trigger), s.deadzone),
    }
    for k, v in raw.items():
        RUNTIME.filtered[k] = smooth_value(RUNTIME.filtered.get(k, 0.0), v, s.smoothing, dt)

    # Cinematic Drone v5 mapping:
    # - RB/LB are true vertical rise/fall. The same bumper
    #   tap logic still applies: double-tap toggles automove, same-direction
    #   taps cycle speed, opposite bumper switches direction at the same speed.
    # - RT/LT are analog barrel-roll/bank controls; trigger position controls roll speed.
    # - Right stick steers view direction: X yaw, Y pitch.
    # - Left stick is screen-locked translation: X strafe, Y forward/back along
    #   the camera view direction. Y-invert mode does not affect the left stick.
    yaw_input = RUNTIME.filtered["rx"]
    pitch_input = RUNTIME.filtered["ry"]
    strafe = RUNTIME.filtered["lx"]
    forward_back = RUNTIME.filtered["ly"]
    roll_input = RUNTIME.filtered["lt"] - RUNTIME.filtered["rt"]
    if int(s.joystick_invert_mode) % 2:
        roll_input = -roll_input
    manual_throttle = ((1.0 if button_forward else 0.0) - (1.0 if button_back else 0.0))
    throttle = RUNTIME.auto_throttle if abs(RUNTIME.auto_throttle) > 0.0 else manual_throttle

    pilot_active = pilot_has_control_input(yaw_input, pitch_input, strafe, forward_back, roll_input, throttle)
    if s.recording and (RUNTIME.record_scrub_hold or RUNTIME.record_waiting_for_input) and not pilot_active:
        RUNTIME.velocity = Vector((0, 0, 0))
        RUNTIME.yaw_rate = 0.0
        s.status = "%s | D-pad live track parked %d/%d" % ("REC", scene.frame_current, RUNTIME.record_max_frame)
        return
    if s.recording and RUNTIME.record_rewound and scene.frame_current < RUNTIME.record_max_frame and pilot_active:
        delete_recorded_keys_after_frame(scene, scene.frame_current)
        RUNTIME.record_rewound = False
        RUNTIME.record_scrub_hold = False
        RUNTIME.record_waiting_for_input = False
    elif pilot_active:
        RUNTIME.record_scrub_hold = False
        RUNTIME.record_waiting_for_input = False

    if brake:
        RUNTIME.velocity *= max(0.0, 1.0 - 12.0 * dt)
        yaw_input = 0.0
        pitch_input = 0.0
        roll_input = 0.0
        throttle = 0.0
        clear_auto_throttle_state()

    # Right stick look is viewport-locked, not Blender/world yaw. Horizontal
    # look rotates around the current screen-up axis; vertical look rotates
    # around the current screen-right axis. This stays intuitive while banked.
    view_obj_for_look = roll or gimbal
    look_q = view_obj_for_look.matrix_world.to_quaternion()
    screen_up_axis = (look_q @ Vector((0, 1, 0))).normalized()
    screen_right_axis = (look_q @ Vector((1, 0, 0))).normalized()
    sense = global_sensitivity_multiplier(s)
    yaw_delta = yaw_input * math.radians(s.yaw_speed) * dt * mult * sense
    pitch_delta = pitch_input * math.radians(s.gimbal_speed) * dt * mult * sense
    if abs(yaw_delta) > 1e-8 or abs(pitch_delta) > 1e-8:
        loc = gimbal.matrix_world.translation.copy()
        current_q = gimbal.matrix_world.to_quaternion()
        delta_q = Quaternion(screen_up_axis, yaw_delta) @ Quaternion(screen_right_axis, pitch_delta)
        new_q = delta_q @ current_q
        new_world = new_q.to_matrix().to_4x4()
        new_world.translation = loc
        gimbal.matrix_world = new_world
        RUNTIME.pitch_angle = float(gimbal.rotation_euler.x)
        RUNTIME.yaw_rate = yaw_delta / max(dt, 1e-6)
    else:
        RUNTIME.yaw_rate = smooth_value(RUNTIME.yaw_rate, 0.0, s.smoothing, dt)
    rig.rotation_euler.x = 0.0
    rig.rotation_euler.y = 0.0

    # LT/RT are analog visual barrel-roll/bank controls on the dedicated Drone_Roll node.
    # By default roll latches where the pilot leaves it; optional auto-level is available in settings.
    roll_delta = roll_input * math.radians(s.roll_speed) * dt * sense
    if abs(roll_input) > 1e-5:
        RUNTIME.roll_angle += roll_delta
    elif s.roll_auto_level:
        step = math.radians(s.roll_return_speed) * dt
        if abs(RUNTIME.roll_angle) <= step:
            RUNTIME.roll_angle = 0.0
        else:
            RUNTIME.roll_angle -= math.copysign(step, RUNTIME.roll_angle)
    if roll:
        roll.rotation_euler.x = 0.0
        roll.rotation_euler.y = 0.0
        roll.rotation_euler.z = float(roll.get("dfr_base_z", 0.0)) + RUNTIME.roll_angle
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass

    # Direction of travel is pegged to the perspective. Use the rolled camera
    # frame so left/right/forward/back match the tilted viewport image while banked.
    view_obj = roll or gimbal
    q = view_obj.matrix_world.to_quaternion()
    view_vec = (q @ Vector((0, 0, -1))).normalized()
    right_vec = (q @ Vector((1, 0, 0))).normalized()
    up_vec = Vector((0, 0, 1))
    left_move_speed = s.max_speed * left_stick_movement_multiplier(s)
    # Bumper rise/fall uses the same movement speed as the left stick so
    # vertical control no longer feels lethargic relative to strafe/forward.
    desired = (view_vec * (forward_back * left_move_speed * mult) +
               right_vec * (strafe * left_move_speed * mult) +
               up_vec * (throttle * left_move_speed * BUMPER_VERTICAL_SPEED_FACTOR * mult))
    diff = desired - RUNTIME.velocity
    max_delta = s.acceleration * mult * dt
    if diff.length > max_delta and diff.length > 1e-6:
        RUNTIME.velocity += diff.normalized() * max_delta
    else:
        RUNTIME.velocity = desired
    RUNTIME.velocity *= max(0.0, 1.0 - s.drag * dt * (0.25 if desired.length > 0.001 else 1.0))
    rig.location += RUNTIME.velocity * dt

    if s.recording:
        RUNTIME.record_tick += 1
        advance_recording_frame_keep_live(scene, scene.frame_current + 1)
        if RUNTIME.record_tick % max(1, s.keyframe_interval) == 0:
            insert_record_key(scene)
    if abs(RUNTIME.auto_throttle) > 0.0:
        RUNTIME.auto_throttle_level = int(s.global_sensitivity_level)
    auto = " AUTO%s X%d" % ("↑" if RUNTIME.auto_throttle > 0 else "↓", int(s.global_sensitivity_level)) if abs(RUNTIME.auto_throttle) > 0.0 else ""
    s.status = "%s T%d%s | %s R%.2f L%.2f | RB/LB rise/fall, RT/LT roll | %s | vel %.2f" % ("REC" if s.recording else "Flying", int(s.active_take_slot), auto, sensitivity_mode_label(s), global_sensitivity_multiplier(s), left_stick_sensitivity_multiplier(s), RUNTIME.backend.path, RUNTIME.velocity.length)


def _flight_timer_tick():
    if RUNTIME.stop_requested or not RUNTIME.timer_running:
        scene = bpy.data.scenes.get(RUNTIME.scene_name) or bpy.context.scene
        if scene and hasattr(scene, "drone_flight_recorder_settings"):
            stop_controller_flight(scene)
        return None
    scene = bpy.data.scenes.get(RUNTIME.scene_name) or bpy.context.scene
    if not scene or not hasattr(scene, "drone_flight_recorder_settings"):
        RUNTIME.stop_requested = True
        return 0.1
    try:
        _flight_step(scene)
    except Exception as ex:
        scene.drone_flight_recorder_settings.status = "Flight error: %s" % ex
        RUNTIME.stop_requested = True
    return 1.0 / 30.0


def start_controller_flight(context, reporter=None):
    if RUNTIME.timer_running:
        if reporter:
            reporter({"WARNING"}, "Drone controller flight is already running")
        return False
    rig, gimbal = get_rig_objects()
    roll = get_roll_object()
    if not rig or not gimbal or not roll:
        bpy.ops.dfr.create_rig()
        rig, gimbal = get_rig_objects()
        roll = get_roll_object()
    if not rig or not gimbal:
        if reporter:
            reporter({"ERROR"}, "Could not create/find AirBlender rig/gimbal")
        return False
    s = settings(context)
    if not RUNTIME.backend.open(s.controller_device):
        s.controller_connected = False
        s.status = "Controller error: " + RUNTIME.backend.error
        if reporter:
            reporter({"ERROR"}, s.status)
        return False
    s.controller_device = RUNTIME.backend.path
    s.controller_connected = True
    ensure_take_actions(context.scene, int(s.active_take_slot))
    s.status = "Flying: %s (Take %d/%d, RB/LB rise/fall, RT/LT analog roll, viewport-locked right stick)" % (RUNTIME.backend.name, int(s.active_take_slot), TAKE_SLOT_COUNT)
    RUNTIME.operator = None
    RUNTIME.timer_running = True
    RUNTIME.scene_name = context.scene.name
    RUNTIME.stop_requested = False
    RUNTIME.last_time = time.monotonic()
    RUNTIME.last_buttons = dict(getattr(getattr(RUNTIME.backend, "active", RUNTIME.backend), "buttons", {}))
    RUNTIME.velocity = Vector((0, 0, 0))
    RUNTIME.yaw_rate = 0.0
    RUNTIME.record_tick = 0
    _rig, _gimbal = get_rig_objects()
    _roll = get_roll_object()
    RUNTIME.pitch_angle = float(_gimbal.rotation_euler.x) if _gimbal else 0.0
    RUNTIME.roll_angle = 0.0
    if _roll:
        _roll.rotation_euler.x = 0.0
        _roll.rotation_euler.y = 0.0
        _roll.rotation_euler.z = float(_roll.get("dfr_base_z", _roll.rotation_euler.z))
    RUNTIME.filtered = {"lx": 0.0, "ly": 0.0, "rx": 0.0, "ry": 0.0, "lt": 0.0, "rt": 0.0}
    RUNTIME.dpad_up_active = False
    RUNTIME.dpad_down_active = False
    RUNTIME.dpad_left_active = False
    RUNTIME.dpad_right_active = False
    RUNTIME.auto_throttle = 0.0
    RUNTIME.auto_throttle_level = 0
    RUNTIME.last_bumper_tap = {}
    RUNTIME.bumper_tap_count = {}
    RUNTIME.pending_start_single = False
    RUNTIME.last_start_tap = -999.0
    bpy.app.timers.register(_flight_timer_tick, first_interval=0.01, persistent=False)
    return True


def stop_controller_flight(scene=None):
    scene = scene or bpy.context.scene
    if scene and hasattr(scene, "drone_flight_recorder_settings"):
        s = scene.drone_flight_recorder_settings
        if s.recording:
            insert_record_key(scene, force=True)
            s.recording = False
        s.controller_connected = False
        s.status = "Stopped"
    RUNTIME.backend.close()
    RUNTIME.operator = None
    RUNTIME.timer_running = False
    RUNTIME.stop_requested = False
    return True

class DFR_OT_start_flight(bpy.types.Operator):
    bl_idname = "dfr.start_controller_flight"
    bl_label = "Start Controller Flight"
    bl_description = "Start modal drone flight from the connected controller"

    _timer = None

    def invoke(self, context, event):
        return {"FINISHED"} if start_controller_flight(context, self.report) else {"CANCELLED"}

    def execute(self, context):
        return {"FINISHED"} if start_controller_flight(context, self.report) else {"CANCELLED"}

    def modal(self, context, event):
        s = settings(context)
        if RUNTIME.stop_requested or event.type == "ESC":
            return self.finish(context)
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        now = time.monotonic()
        dt = max(0.0001, min(0.1, now - RUNTIME.last_time))
        RUNTIME.last_time = now
        rig, gimbal = get_rig_objects()
        if not rig or not gimbal:
            s.status = "Stopped: missing AirBlender rig/gimbal"
            return self.finish(context)
        RUNTIME.backend.poll()
        s.controller_connected = RUNTIME.backend.connected
        if not RUNTIME.backend.connected:
            s.status = "Controller disconnected: " + RUNTIME.backend.error
            return self.finish(context)

        b = RUNTIME.backend.button
        def edge(idx):
            val = b(idx)
            old = RUNTIME.last_buttons.get(idx, False)
            RUNTIME.last_buttons[idx] = val
            return val and not old

        if edge(s.button_a):
            _toggle_first_third_person(context.scene)
        if edge(s.button_x):
            level, mul = cycle_global_sensitivity(s)
            s.status = "Global sensitivity L%d x%.2f" % (level, mul)
        if edge(s.button_y):
            insert_record_key(context.scene, force=True, marker=True)
        brake = b(s.button_b)
        precision = b(s.button_lb)
        boost = b(s.button_rb)
        mult = 1.0
        if precision:
            mult *= s.precision_multiplier
        if boost:
            mult *= s.boost_multiplier

        def ax(idx, inv=False):
            v = RUNTIME.backend.axis(idx)
            if inv:
                v = -v
            return deadzone_value(v, s.deadzone)

        raw = {
            "lx": ax(s.axis_left_x, effective_toggle_invert(s.invert_left_x, s.joystick_invert_mode, "left_x")),
            "ly": ax(s.axis_left_y, effective_toggle_invert(s.invert_left_y, s.joystick_invert_mode, "left_y")),
            "rx": ax(s.axis_right_x, effective_toggle_invert(s.invert_right_x, s.joystick_invert_mode, "right_x")),
            "ry": ax(s.axis_right_y, effective_toggle_invert(s.invert_right_y, s.joystick_invert_mode, "right_y")),
            "lt": (RUNTIME.backend.axis(s.axis_left_trigger) + 1.0) * 0.5,
            "rt": (RUNTIME.backend.axis(s.axis_right_trigger) + 1.0) * 0.5,
        }
        for k, v in raw.items():
            if k in ("lt", "rt"):
                v = 0.0 if v < s.deadzone else v
            RUNTIME.filtered[k] = smooth_value(RUNTIME.filtered.get(k, 0.0), v, s.smoothing, dt)

        forward_back = RUNTIME.filtered["ly"]
        yaw_input = RUNTIME.filtered["lx"]
        strafe = RUNTIME.filtered["rx"]
        forward = RUNTIME.filtered["ry"]
        if brake:
            RUNTIME.velocity *= max(0.0, 1.0 - 12.0 * dt)
            yaw_input = 0.0
        rig_q = rig.matrix_world.to_quaternion()
        right_vec = rig_q @ Vector((1, 0, 0))
        forward_vec = rig_q @ Vector((0, -1, 0))
        thrust_speed = s.max_speed * global_sensitivity_multiplier(s)
        left_move_speed = s.max_speed * left_stick_movement_multiplier(s)
        desired = (right_vec * (strafe * left_move_speed * mult) +
                   forward_vec * (forward * left_move_speed * mult) +
                   Vector((0, 0, vertical * thrust_speed * mult)))
        diff = desired - RUNTIME.velocity
        max_delta = s.acceleration * mult * dt
        if diff.length > max_delta and diff.length > 1e-6:
            RUNTIME.velocity += diff.normalized() * max_delta
        else:
            RUNTIME.velocity = desired
        RUNTIME.velocity *= max(0.0, 1.0 - s.drag * dt * (0.25 if desired.length > 0.001 else 1.0))
        rig.location += RUNTIME.velocity * dt

        desired_yaw = yaw_input * math.radians(s.yaw_speed) * mult
        RUNTIME.yaw_rate = smooth_value(RUNTIME.yaw_rate, desired_yaw, s.smoothing, dt)
        rig.rotation_euler.x = 0.0
        rig.rotation_euler.y = 0.0
        rig.rotation_euler.z += RUNTIME.yaw_rate * dt

        tilt_delta = (RUNTIME.filtered["rt"] - RUNTIME.filtered["lt"]) * math.radians(s.gimbal_speed) * dt
        RUNTIME.pitch_angle += tilt_delta
        if not s.unlimited_pitch:
            RUNTIME.pitch_angle = max(math.radians(-89.0), min(math.radians(45.0), RUNTIME.pitch_angle))
        gimbal.rotation_euler.x = RUNTIME.pitch_angle
        base_y = float(gimbal.get("dfr_base_y", 0.0))
        target_bank = math.radians(s.banking) * (-strafe * 0.75 - yaw_input * 0.25)
        gimbal.rotation_euler.y = smooth_value(gimbal.rotation_euler.y, base_y + target_bank, s.smoothing, dt)
        gimbal.rotation_euler.z = float(gimbal.get("dfr_base_z", gimbal.rotation_euler.z))

        if s.recording:
            RUNTIME.record_tick += 1
            advance_recording_frame_keep_live(context.scene, context.scene.frame_current + 1)
            if RUNTIME.record_tick % max(1, s.keyframe_interval) == 0:
                insert_record_key(context.scene)
        s.status = "%s | %s | vel %.2f" % ("REC" if s.recording else "Flying", RUNTIME.backend.path, RUNTIME.velocity.length)
        return {"PASS_THROUGH"}

    def finish(self, context):
        s = settings(context)
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        RUNTIME.backend.close()
        RUNTIME.operator = None
        RUNTIME.stop_requested = False
        s.controller_connected = False
        if s.recording:
            insert_record_key(context.scene, force=True)
            s.recording = False
        s.status = "Stopped"
        return {"CANCELLED"}


class DFR_OT_stop_flight(bpy.types.Operator):
    bl_idname = "dfr.stop_controller_flight"
    bl_label = "Stop Controller Flight"
    bl_description = "Stop the modal controller flight loop"

    def execute(self, context):
        RUNTIME.stop_requested = True
        stop_controller_flight(context.scene)
        return {"FINISHED"}


class DFR_OT_toggle_recording(bpy.types.Operator):
    bl_idname = "dfr.toggle_recording"
    bl_label = "Toggle Recording"

    def execute(self, context):
        s = settings(context)
        if s.recording:
            _stop_recording(context.scene)
        else:
            _start_recording(context.scene)
        return {"FINISHED"}


class DFR_OT_clear_path(bpy.types.Operator):
    bl_idname = "dfr.clear_recorded_path"
    bl_label = "Clear Recorded Path"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        for obj in get_drone_anim_objects():
            if obj and obj.animation_data and obj.animation_data.action:
                action = obj.animation_data.action
                for fc in list(iter_action_fcurves(action)):
                    if fc.data_path in {"location", "rotation_euler"}:
                        remove_action_fcurve(action, fc)
        for m in list(context.scene.timeline_markers):
            if (m.name.startswith("LAB_") or m.name.startswith("DFR_")):
                context.scene.timeline_markers.remove(m)
        RUNTIME.last_key_loc = None
        self.report({"INFO"}, "Drone recorded path cleared")
        return {"FINISHED"}


class DFR_OT_simplify_path(bpy.types.Operator):
    bl_idname = "dfr.simplify_recorded_path"
    bl_label = "Smooth/Simplify Path"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        threshold = max(0.0, settings(context).keyframe_threshold)
        removed = 0
        for obj in get_drone_anim_objects():
            if not obj or not obj.animation_data or not obj.animation_data.action:
                continue
            for fc in iter_action_fcurves(obj.animation_data.action):
                if fc.data_path not in {"location", "rotation_euler"}:
                    continue
                changed = True
                while changed and len(fc.keyframe_points) > 2:
                    changed = False
                    pts = fc.keyframe_points
                    for i in range(len(pts) - 2, 0, -1):
                        p0, p1, p2 = pts[i - 1], pts[i], pts[i + 1]
                        span = p2.co.x - p0.co.x
                        if abs(span) < 1e-6:
                            continue
                        t = (p1.co.x - p0.co.x) / span
                        expected = p0.co.y + (p2.co.y - p0.co.y) * t
                        if abs(p1.co.y - expected) <= threshold:
                            pts.remove(p1)
                            removed += 1
                            changed = True
                    fc.update()
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"
        self.report({"INFO"}, "Simplified drone path; removed %d keys" % removed)
        return {"FINISHED"}


class DFR_OT_cycle_take(bpy.types.Operator):
    bl_idname = "dfr.cycle_take"
    bl_label = "Cycle Take Slot"
    bl_description = "Switch to the next take slot"

    def execute(self, context):
        switch_take_slot(context.scene, (int(settings(context).active_take_slot) % TAKE_SLOT_COUNT) + 1)
        return {"FINISHED"}


class DFR_OT_probe_controller(bpy.types.Operator):
    bl_idname = "dfr.probe_controller"
    bl_label = "Probe Controller"

    def execute(self, context):
        devs = LinuxJoystickBackend.list_devices()
        s = settings(context)
        if not devs:
            s.status = "No /dev/input/js* controller found"
            s.controller_connected = False
            self.report({"ERROR"}, s.status)
            return {"CANCELLED"}
        chosen = devs[0]
        for d in devs:
            hay = (d[0] + " " + d[1]).lower()
            if "keyd virtual" not in hay and any(x in hay for x in ("x-box", "xbox", "microsoft", "controller", "pad", "gamepad")):
                chosen = d
                break
        s.controller_device = chosen[0]
        s.status = "Found %s: %s (%d axes, %d buttons)" % chosen
        self.report({"INFO"}, s.status)
        return {"FINISHED"}


class LAB_OT_activate(bpy.types.Operator):
    bl_idname = "lab.activate"
    bl_label = "Activate The Last AirBlender"
    bl_description = "Arm AirBlender split-view camera flight"

    def execute(self, context):
        if not context.scene.camera:
            cams = [o for o in bpy.data.objects if o.type == "CAMERA"]
            if cams:
                context.scene.camera = sorted(cams, key=lambda o: o.name)[0]
        if not context.scene.camera:
            create_airblender_camera(context.scene, context)
        else:
            bpy.ops.dfr.create_rig()
        configure_drone_split_view_layout(context)
        start_controller_flight(context, self.report)
        return {"FINISHED"}


class LAB_MT_controller_controls(bpy.types.Menu):
    bl_label = "The Last AirBlender Controls"
    bl_idname = "LAB_MT_controller_controls"

    def draw(self, context):
        layout = self.layout
        for text in CONTROL_HELP_LINES:
            layout.label(text=text)
        layout.separator()
        layout.operator("lab.activate", text="Activate / Split View", icon="PLAY")
        layout.operator("dfr.stop_controller_flight", text="Stop Flight", icon="PAUSE")
        layout.operator("dfr.toggle_recording", text="Toggle Recording", icon="REC")


CONTROL_HELP_LINES = (
    "Start/Menu: cycle cameras",
    "Start/Menu double-tap: create camera",
    "A: first/third-person view",
    "B: brake",
    "X: speed low/medium/high/xhigh",
    "Y: global invert",
    "Left stick: strafe + forward/back",
    "Right stick: viewport-locked look",
    "RB/LB: rise/fall; double-tap auto",
    "RT/LT: analog roll",
    "D-pad Up: camera screenshot",
    "D-pad Down: record/stop/overwrite",
    "D-pad Left/Right: scrub take",
    "Select/Back: cycle take slots",
)


def _draw_controller_icon():
    try:
        x, y, w, h = RUNTIME.icon_region
        font_id = 0
        blf.size(font_id, 26)
        blf.color(font_id, 1.0, 1.0, 1.0, 0.48)
        blf.position(font_id, x, y, 0)
        blf.draw(font_id, "🎮")
        blf.size(font_id, 10)
        blf.color(font_id, 1.0, 1.0, 1.0, 0.42)
        blf.position(font_id, x + 4, y - 10, 0)
        blf.draw(font_id, "Air")
    except Exception:
        pass


class LAB_OT_icon_runtime(bpy.types.Operator):
    bl_idname = ICON_RUNTIME_OPERATOR
    bl_label = "The Last AirBlender Icon Runtime"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        if RUNTIME.icon_running:
            return {"FINISHED"}
        RUNTIME.icon_draw_handler = bpy.types.SpaceView3D.draw_handler_add(_draw_controller_icon, (), "WINDOW", "POST_PIXEL")
        RUNTIME.icon_running = True
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type in {"LEFTMOUSE", "RIGHTMOUSE"} and event.value == "PRESS":
            x, y, w, h = RUNTIME.icon_region
            mx = getattr(event, "mouse_region_x", -9999)
            my = getattr(event, "mouse_region_y", -9999)
            if x - 6 <= mx <= x + w and y - 16 <= my <= y + h:
                if event.type == "LEFTMOUSE":
                    bpy.ops.lab.activate()
                else:
                    bpy.ops.wm.call_menu(name="LAB_MT_controller_controls")
                return {"RUNNING_MODAL"}
        if event.type == "ESC" and event.value == "PRESS":
            return {"PASS_THROUGH"}
        return {"PASS_THROUGH"}


def ensure_icon_runtime():
    if RUNTIME.icon_running:
        return True
    def _start():
        try:
            bpy.ops.lab.icon_runtime("INVOKE_DEFAULT")
        except Exception:
            return 1.0
        return None
    bpy.app.timers.register(_start, first_interval=0.5, persistent=True)
    return True


class DFR_PT_panel(bpy.types.Panel):
    bl_label = "The Last AirBlender"
    bl_idname = "DFR_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AirBlender"

    def draw(self, context):
        layout = self.layout
        s = settings(context)
        col = layout.column(align=True)
        col.label(text="Status: %s" % s.status)
        col.label(text="Controller: %s" % ("connected" if s.controller_connected else "disconnected"))
        col.label(text="Recording: %s" % ("ON" if s.recording else "off"))
        col.label(text="Take: %d / %d" % (s.active_take_slot, TAKE_SLOT_COUNT))
        col.label(text="A = first/third-person view")
        col.label(text="Y = global invert")
        col.label(text="Invert: " + joystick_invert_mode_label(s.joystick_invert_mode))
        col.label(text="D-pad Up = camera screenshot")
        col.label(text="D-pad Down = record / overwrite")
        col.label(text="Start = cycle cameras; double-tap creates camera")
        col.label(text="Select = cycle takes 1-10")
        col.label(text="D-pad Left/Right = rewind/forward active take")
        if s.last_screenshot_path:
            col.label(text="Last shot: " + os.path.basename(s.last_screenshot_path))
        col.label(text="RB/LB = rise/fall; double-tap auto; tap reverses")
        col.label(text="Right stick = viewport-locked look")
        col.label(text="Left stick = strafe + forward/back")
        col.label(text="RT/LT = analog camera barrel roll")
        col.label(text="X = low / medium / high / xhigh")
        col.label(text="Click 🎮 icon to arm; right-click for controls")
        col.operator("dfr.probe_controller", icon="VIEWZOOM")
        col.prop(s, "controller_device")
        layout.separator()
        row = layout.row(align=True)
        row.operator("dfr.create_rig", icon="EMPTY_ARROWS")
        row.operator("dfr.start_controller_flight", icon="PLAY")
        layout.operator("dfr.stop_controller_flight", icon="PAUSE")
        layout.operator("dfr.toggle_recording", icon="REC")
        layout.operator("dfr.cycle_take", icon="NEXT_KEYFRAME")
        row = layout.row(align=True)
        row.operator("dfr.clear_recorded_path", icon="TRASH")
        row.operator("dfr.simplify_recorded_path", icon="MOD_SMOOTH")
        layout.separator()
        box = layout.box()
        box.label(text="Flight Settings")
        for prop in ("max_speed", "vertical_speed", "global_sensitivity_level", "left_stick_gain", "yaw_speed", "gimbal_speed", "roll_speed", "roll_auto_level", "roll_return_speed", "bumper_double_tap_window", "manual_bumper_thrust_multiplier", "record_scrub_frames_per_tick", "start_double_tap_window", "joystick_invert_mode", "unlimited_pitch", "acceleration", "drag", "deadzone", "smoothing", "banking", "keyframe_interval", "keyframe_threshold"):
            box.prop(s, prop)
        layout.prop(s, "show_mapping", toggle=True)
        if s.show_mapping:
            box = layout.box()
            box.label(text="Axis/Button Mapping")
            box.label(text="Defaults: Start/Menu camera fleet, Left stick move, Right stick look, RB/LB rise/fall, RT/LT roll")
            for prop in ("axis_left_x", "axis_left_y", "axis_right_x", "axis_right_y", "axis_left_trigger", "axis_right_trigger", "axis_dpad_y", "axis_dpad_x", "dpad_up_direction", "dpad_down_direction", "dpad_left_direction", "dpad_right_direction", "invert_left_x", "invert_left_y", "invert_right_x", "invert_right_y"):
                box.prop(s, prop)
            for prop in ("button_a", "button_b", "button_x", "button_y", "button_lb", "button_rb", "button_select", "button_start", "precision_multiplier", "boost_multiplier"):
                box.prop(s, prop)


classes = (
    DroneFlightSettings,
    DFR_OT_create_rig,
    DFR_OT_start_flight,
    DFR_OT_stop_flight,
    DFR_OT_toggle_recording,
    DFR_OT_clear_path,
    DFR_OT_simplify_path,
    DFR_OT_cycle_take,
    DFR_OT_probe_controller,
    LAB_OT_activate,
    LAB_OT_icon_runtime,
    LAB_MT_controller_controls,
    DFR_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.drone_flight_recorder_settings = bpy.props.PointerProperty(type=DroneFlightSettings)
    ensure_icon_runtime()


def unregister():
    if RUNTIME.operator is not None:
        RUNTIME.stop_requested = True
    if RUNTIME.icon_draw_handler is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(RUNTIME.icon_draw_handler, "WINDOW")
        except Exception:
            pass
        RUNTIME.icon_draw_handler = None
        RUNTIME.icon_running = False
    if hasattr(bpy.types.Scene, "drone_flight_recorder_settings"):
        del bpy.types.Scene.drone_flight_recorder_settings
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass


if __name__ == "__main__":
    register()
