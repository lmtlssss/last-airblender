import sys, time
from pathlib import Path
import bpy
from mathutils import Vector
ADDON_DIR = Path(__file__).resolve().parents[2] / 'addon'
sys.path.insert(0, str(ADDON_DIR))
if 'last_airblender' in sys.modules:
    try:
        sys.modules['last_airblender'].unregister()
    except Exception:
        pass
    del sys.modules['last_airblender']
import last_airblender as d
if hasattr(bpy.types.Scene, 'drone_flight_recorder_settings'):
    try:
        d.unregister()
    except Exception:
        pass
d.register()
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete()
cam_data=bpy.data.cameras.new('Smoke_Cam_Data'); cam=bpy.data.objects.new('Smoke_Cam', cam_data)
bpy.context.collection.objects.link(cam); bpy.context.scene.camera=cam; bpy.context.view_layer.update()
bpy.ops.dfr.create_rig(); scene=bpy.context.scene; s=scene.drone_flight_recorder_settings
rig,gimbal=d.get_rig_objects(); roll=d.get_roll_object()
s.deadzone=0.0; s.smoothing=0.0; s.drag=0.0; s.acceleration=999.0; s.max_speed=2.0; s.global_sensitivity_level=2; s.left_stick_gain=5.0; s.manual_bumper_thrust_multiplier=0.25; s.bumper_double_tap_window=0.35
class FB:
    connected=True; path='/dev/input/js-test'; error=''
    def __init__(self): self.axes={i:0.0 for i in range(8)}; self.buttons={i:False for i in range(16)}
    def poll(self): pass
    def axis(self,idx,*args): return self.axes.get(idx,0.0)
    def button(self,idx): return self.buttons.get(idx,False)
fb=FB(); d.RUNTIME.backend=fb

def reset():
    rig.location=(0,0,0); d.RUNTIME.velocity=Vector((0,0,0)); d.RUNTIME.filtered={}; d.RUNTIME.last_buttons={}; d.clear_auto_throttle_state()
    for k in fb.axes: fb.axes[k]=0.0
    for k in fb.buttons: fb.buttons[k]=False
    fb.axes[s.axis_left_trigger] = -1.0; fb.axes[s.axis_right_trigger] = -1.0

def tick(dt=0.08):
    d.RUNTIME.last_time=time.monotonic()-dt
    d._flight_step(scene)

def tap(btn, pause=0.04):
    fb.buttons[btn]=True; tick(0.08)
    fb.buttons[btn]=False; tick(0.04)
    if pause: time.sleep(pause)
reset()
# Double-tap RB starts auto rise. Level/status follows current X mode, not old auto ladder.
tap(s.button_rb,0.04); tap(s.button_rb,0.40)
print('AUTO_START', d.RUNTIME.auto_throttle, d.RUNTIME.auto_throttle_level, s.global_sensitivity_level)
assert d.RUNTIME.auto_throttle > 0 and d.RUNTIME.auto_throttle_level == s.global_sensitivity_level
# Single tap again reverses direction. Same for the other bumper; no speed cycling.
tap(s.button_rb,0.40)
print('AUTO_REVERSE_1', d.RUNTIME.auto_throttle, d.RUNTIME.auto_throttle_level)
assert d.RUNTIME.auto_throttle < 0 and d.RUNTIME.auto_throttle_level == s.global_sensitivity_level
tap(s.button_lb,0.40)
print('AUTO_REVERSE_2', d.RUNTIME.auto_throttle, d.RUNTIME.auto_throttle_level)
assert d.RUNTIME.auto_throttle > 0 and d.RUNTIME.auto_throttle_level == s.global_sensitivity_level
# Changing X mode changes automove travel speed without any bumper-specific level.
def auto_dist(level):
    reset(); s.global_sensitivity_level=level; d.set_auto_throttle_level(s, 1.0); tick(0.1); return rig.location.z
z1=auto_dist(1); z4=auto_dist(4); print('AUTO_X_DIST', z1, z4); assert z4 > z1 * 7.0
print('BUMPER_XMODE_REVERSE_SMOKE_OK')
