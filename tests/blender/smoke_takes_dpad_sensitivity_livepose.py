import sys, time, os
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
# clean
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete()
for action in list(bpy.data.actions):
    if action.name.startswith('DFR_'):
        bpy.data.actions.remove(action)
cam_data=bpy.data.cameras.new('Smoke_Cam_Data'); cam=bpy.data.objects.new('Smoke_Cam', cam_data)
bpy.context.collection.objects.link(cam); bpy.context.scene.camera=cam; bpy.context.view_layer.update()
bpy.ops.dfr.create_rig(); scene=bpy.context.scene; s=scene.drone_flight_recorder_settings
s.deadzone=0.0; s.smoothing=0.0; s.drag=0.0; s.acceleration=9999.0; s.max_speed=2.0; s.global_sensitivity_level=1; s.left_stick_gain=1.0; s.keyframe_interval=1; s.keyframe_threshold=0.0; s.active_take_slot=1
rig,gimbal=d.get_rig_objects(); roll=d.get_roll_object()
class FB:
    connected=True; path='/dev/input/js-test'; error=''
    def __init__(self): self.axes={i:0.0 for i in range(8)}; self.buttons={i:False for i in range(16)}
    def poll(self): pass
    def axis(self,idx,*args): return self.axes.get(idx,0.0)
    def button(self,idx): return self.buttons.get(idx,False)
fb=FB(); d.RUNTIME.backend=fb; d.RUNTIME.filtered={}; d.RUNTIME.last_buttons={}; d.RUNTIME.velocity=Vector((0,0,0)); d.clear_auto_throttle_state(); d.RUNTIME.timer_running=False
fb.axes[s.axis_left_trigger] = -1.0; fb.axes[s.axis_right_trigger] = -1.0

def reset_inputs():
    for k in fb.axes: fb.axes[k]=0.0
    for k in fb.buttons: fb.buttons[k]=False
    fb.axes[s.axis_left_trigger] = -1.0; fb.axes[s.axis_right_trigger] = -1.0
    d.RUNTIME.last_buttons={}

def tick(dt=0.1):
    d.RUNTIME.last_time=time.monotonic()-dt
    d._flight_step(scene)

# Sensitivity: exact tiers, X cycles, and high tier moves much farther.
assert tuple(round(d.global_sensitivity_multiplier(type('S',(),{'global_sensitivity_level':i})()),2) for i in (1,2,3,4)) == (0.35,0.80,1.60,3.10)
reset_inputs(); fb.buttons[s.button_x]=True; tick(); fb.buttons[s.button_x]=False; tick(); assert s.global_sensitivity_level == 2
fb.buttons[s.button_x]=True; tick(); fb.buttons[s.button_x]=False; tick(); assert s.global_sensitivity_level == 3
fb.buttons[s.button_x]=True; tick(); fb.buttons[s.button_x]=False; tick(); assert s.global_sensitivity_level == 4
fb.buttons[s.button_x]=True; tick(); fb.buttons[s.button_x]=False; tick(); assert s.global_sensitivity_level == 1

def move_len(level):
    reset_inputs(); rig.location=(0,0,0); d.RUNTIME.velocity=Vector((0,0,0)); d.RUNTIME.filtered={}; s.global_sensitivity_level=level; fb.axes[s.axis_left_x]=1.0; tick(0.1); return rig.location.length
l1=move_len(1); l2=move_len(2); l3=move_len(3); l4=move_len(4); print('SENSE_LEFT_LEN', l1, l2, l3, l4); assert 0.20 <= l1 <= 0.30 and l2 >= l1 * 1.9 and l3 >= l2 * 1.8 and l4 >= l3 * 1.7

# D-pad swap: Up screenshot, Down recording.
shots=[]
d._capture_drone_screenshot=lambda sc: shots.append(int(sc.frame_current)) or setattr(sc.drone_flight_recorder_settings, 'last_screenshot_path', '/tmp/fake.png')
reset_inputs(); s.recording=False; fb.axes[s.axis_dpad_y]=-1.0; tick(); fb.axes[s.axis_dpad_y]=0.0; tick(); assert shots and not s.recording
fb.axes[s.axis_dpad_y]=1.0; tick(); fb.axes[s.axis_dpad_y]=0.0; tick(); assert s.recording
fb.axes[s.axis_dpad_y]=1.0; tick(); fb.axes[s.axis_dpad_y]=0.0; tick(); assert not s.recording
print('DPAD_SWAP_OK')

# Select cycles take slots and actions are separate.
reset_inputs(); s.recording=False; s.active_take_slot=1; d.ensure_take_actions(scene,1); a1=d.take_action_name(rig,1)
fb.buttons[s.button_select]=True; tick(); fb.buttons[s.button_select]=False; tick(); assert s.active_take_slot == 2
assert rig.animation_data.action.name == d.take_action_name(rig,2) and rig.animation_data.action.name != a1
# Record into take 2.
scene.frame_set(1); rig.location=(2,0,0); d._start_recording(scene); d.insert_record_key(scene, force=True); d._stop_recording(scene); assert d.action_has_keys(bpy.data.actions[d.take_action_name(rig,2)])
d.switch_take_slot(scene,3); assert not d.action_has_keys(bpy.data.actions[d.take_action_name(rig,3)])
d.switch_take_slot(scene,2); assert d.action_has_keys(rig.animation_data.action)
print('TAKES_OK')

# Live-pose restore over frame advance: evaluated frame 2 would be 99, helper keeps live 7.
d.ensure_take_actions(scene,2); scene.frame_set(1); rig.location=(99,0,0); rig.keyframe_insert(data_path='location', frame=2); rig.location=(7,0,0); pose_before=rig.location.copy(); d.advance_recording_frame_keep_live(scene,2); assert (rig.location - pose_before).length < 1e-6
print('LIVE_POSE_RESTORE_OK')

# Overwrite after rewind: create future keys, resume overwrite at frame 2 removes >/= 2 then writes frame 2.
d.ensure_take_actions(scene,4); scene.frame_set(1); rig.location=(1,0,0); d.insert_record_key(scene, force=True)
scene.frame_set(2); rig.location=(2,0,0); d.insert_record_key(scene, force=True)
scene.frame_set(5); rig.location=(5,0,0); d.insert_record_key(scene, force=True); d.RUNTIME.record_max_frame=5
scene.frame_set(2); bpy.context.view_layer.update(); d.RUNTIME.record_rewound=True; d.RUNTIME.record_scrub_hold=True; s.recording=True; d._resume_recording_overwrite(scene)
frames=sorted({round(kp.co.x) for fc in d.iter_action_fcurves(rig.animation_data.action) if fc.data_path=='location' for kp in fc.keyframe_points})
print('OVERWRITE_FRAMES', frames); assert frames == [1,2]
print('TAKES_DPAD_SENSITIVITY_LIVEPOSE_SMOKE_OK')
