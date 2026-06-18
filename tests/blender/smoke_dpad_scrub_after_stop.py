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
s.deadzone=0.0; s.smoothing=0.0; s.drag=0.0; s.acceleration=9999.0; s.max_speed=2.0; s.global_sensitivity_level=2; s.left_stick_gain=1.0; s.keyframe_interval=1; s.keyframe_threshold=0.0; s.active_take_slot=1; s.record_scrub_frames_per_tick=2
class FB:
    connected=True; path='/dev/input/js-test'; error=''
    def __init__(self): self.axes={i:0.0 for i in range(8)}; self.buttons={i:False for i in range(16)}
    def poll(self): pass
    def axis(self,idx,*args): return self.axes.get(idx,0.0)
    def button(self,idx): return self.buttons.get(idx,False)
fb=FB(); d.RUNTIME.backend=fb; d.RUNTIME.last_buttons={}; d.RUNTIME.filtered={}; d.RUNTIME.velocity=Vector((0,0,0)); d.clear_auto_throttle_state()
fb.axes[s.axis_left_trigger] = -1.0; fb.axes[s.axis_right_trigger] = -1.0

def tick(dt=0.1):
    d.RUNTIME.last_time=time.monotonic()-dt
    d._flight_step(scene)
# Build a recorded take then stop.
d.ensure_take_actions(scene,1)
for f in (1,3,5,7):
    scene.frame_set(f); rig.location=(f,0,0); d.insert_record_key(scene, force=True)
d.RUNTIME.record_max_frame=7; s.recording=False; scene.frame_set(7); bpy.context.view_layer.update()
# D-pad left should scrub back even while not recording.
fb.axes[s.axis_dpad_x] = -1.0; tick(); fb.axes[s.axis_dpad_x]=0.0; tick()
print('AFTER_LEFT', scene.frame_current, s.status)
assert scene.frame_current == 5 and not s.recording and d.RUNTIME.record_scrub_hold and d.RUNTIME.record_rewound
# D-pad right should scrub forward while not recording.
fb.axes[s.axis_dpad_x] = 1.0; tick(); fb.axes[s.axis_dpad_x]=0.0; tick()
print('AFTER_RIGHT', scene.frame_current, s.status)
assert scene.frame_current == 7 and not s.recording
# From scrubbed/stopped frame, Down starts overwrite recording and trims future.
scene.frame_set(5); d.RUNTIME.record_scrub_hold=True; d.RUNTIME.record_rewound=True; fb.axes[s.axis_dpad_y]=1.0; tick(); fb.axes[s.axis_dpad_y]=0.0; tick()
frames=sorted({round(kp.co.x) for fc in d.iter_action_fcurves(rig.animation_data.action) if fc.data_path=='location' for kp in fc.keyframe_points})
print('AFTER_DOWN_OVERWRITE', s.recording, frames)
assert s.recording and frames == [1,3,5]
print('DPAD_SCRUB_AFTER_STOP_SMOKE_OK')
