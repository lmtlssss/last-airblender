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
s.deadzone=0.0; s.smoothing=0.0; s.drag=0.0; s.acceleration=9999.0; s.max_speed=2.0; s.global_sensitivity_level=2; s.left_stick_gain=1.0; s.manual_bumper_thrust_multiplier=0.25; s.auto_throttle_min_multiplier=0.25
class FB:
    connected=True; path='/dev/input/js-test'; error=''
    def __init__(self): self.axes={i:0.0 for i in range(8)}; self.buttons={i:False for i in range(16)}
    def poll(self): pass
    def axis(self,idx,*args): return self.axes.get(idx,0.0)
    def button(self,idx): return self.buttons.get(idx,False)
fb=FB(); d.RUNTIME.backend=fb

def reset():
    rig.location=(0,0,0); rig.rotation_euler=(0,0,0); gimbal.rotation_euler=(0,0,0)
    if roll: roll.rotation_euler=(0,0,0)
    d.RUNTIME.velocity=Vector((0,0,0)); d.RUNTIME.filtered={}; d.RUNTIME.last_buttons={}; d.clear_auto_throttle_state(); d.RUNTIME.record_rewound=False; d.RUNTIME.record_scrub_hold=False
    for k in fb.axes: fb.axes[k]=0.0
    for k in fb.buttons: fb.buttons[k]=False
    fb.axes[s.axis_left_trigger] = -1.0; fb.axes[s.axis_right_trigger] = -1.0
    s.joystick_invert_mode=0

def tick(dt=0.1):
    d.RUNTIME.last_time=time.monotonic()-dt
    d._flight_step(scene)

# RB/LB manual thrust is now vertical rise/fall, not forward/back.
reset(); fb.buttons[s.button_rb]=True; tick(); rb=rig.location.copy(); print('RB_LOC', tuple(round(v,4) for v in rb)); assert rb.z > 0.01 and abs(rb.x) < 1e-6 and abs(rb.y) < 1e-6
reset(); fb.buttons[s.button_lb]=True; tick(); lb=rig.location.copy(); print('LB_LOC', tuple(round(v,4) for v in lb)); assert lb.z < -0.01 and abs(lb.x) < 1e-6 and abs(lb.y) < 1e-6
# Left stick Y is now forward/back along view, not vertical.
reset(); view_vec=( (roll or gimbal).matrix_world.to_quaternion() @ Vector((0,0,-1)) ).normalized(); fb.axes[s.axis_left_y] = -1.0; tick(); fwd=rig.location.copy(); print('LEFTY_UP_LOC', tuple(round(v,4) for v in fwd), 'VIEW', tuple(round(v,4) for v in view_vec)); assert fwd.length > 0.01 and abs(fwd.normalized().dot(view_vec)) > 0.99
# Y is now a global invert toggle, so left stick Y reverses too.
normal=fwd.copy(); reset(); s.joystick_invert_mode=1; fb.axes[s.axis_left_y] = -1.0; tick(); inv=rig.location.copy(); print('LEFTY_INVERT_LOC', tuple(round(v,4) for v in inv)); assert normal.dot(inv) < -0.01
# Left X still strafes.
reset(); fb.axes[s.axis_left_x]=1.0; tick(); strafe=rig.location.copy(); print('LEFTX_LOC', tuple(round(v,4) for v in strafe)); assert abs(strafe.x) > 0.01 and abs(strafe.z) < 1e-6
# Automove RB level 1 also rises.
reset(); d.set_auto_throttle_level(s, 1.0, 1); tick(); auto=rig.location.copy(); print('AUTO_RISE_LOC', tuple(round(v,4) for v in auto)); assert auto.z > 0.01 and abs(auto.y) < 1e-6 and 0.70 < abs(auto.z / strafe.x) < 0.80
print('BUMPERS_VERTICAL_LEFT_FORWARD_SMOKE_OK')
