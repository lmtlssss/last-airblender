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

def make_cam(name, loc):
    data=bpy.data.cameras.new(name+'_Data'); obj=bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj); obj.location=loc; obj.rotation_euler=(0.1,0.2,0.3); return obj
cam1=make_cam('Cam_A',(1,2,3)); cam2=make_cam('Cam_B',(4,5,6))
scene=bpy.context.scene; scene.camera=cam1; bpy.context.view_layer.update()
bpy.ops.dfr.create_rig(); s=scene.drone_flight_recorder_settings
s.deadzone=0.0; s.smoothing=0.0; s.drag=0.0; s.acceleration=999.0; s.start_double_tap_window=0.25
class FB:
    connected=True; path='/dev/input/js-test'; error=''
    def __init__(self): self.axes={i:0.0 for i in range(8)}; self.buttons={i:False for i in range(16)}
    def poll(self): pass
    def axis(self,idx,*args): return self.axes.get(idx,0.0)
    def button(self,idx): return self.buttons.get(idx,False)
fb=FB(); d.RUNTIME.backend=fb
def tick(dt=0.1):
    d.RUNTIME.last_time=time.monotonic()-dt; d._flight_step(scene)
def press_start():
    fb.buttons[s.button_start]=True; tick(0.06); fb.buttons[s.button_start]=False; tick(0.06)
for i in range(8): fb.axes[i]=0.0
fb.axes[s.axis_left_trigger]=-1.0; fb.axes[s.axis_right_trigger]=-1.0
d.RUNTIME.last_buttons={}; d.RUNTIME.pending_start_single=False; d.RUNTIME.last_start_tap=-999.0
# Single tap waits the double-tap window, then cycles to Cam_B.
press_start(); time.sleep(0.30); tick(0.30)
print('AFTER_SINGLE', scene.camera.name)
assert scene.camera.name == 'Cam_B', scene.camera.name
assert scene.camera.parent == d.get_roll_object()
# Double tap creates a new AirBlender camera and makes it active.
before=set(o.name for o in bpy.data.objects if o.type=='CAMERA')
press_start(); press_start(); tick(0.05)
after=[o for o in bpy.data.objects if o.type=='CAMERA' and o.name not in before]
print('AFTER_DOUBLE', [o.name for o in after], scene.camera.name)
assert len(after)==1 and after[0].name.startswith('AirBlender_Cam_')
assert scene.camera == after[0]
assert scene.camera.get('lab_camera') is True
assert scene.camera.parent == d.get_roll_object()
# Recording blocks switch/create.
current=scene.camera
s.recording=True
press_start(); time.sleep(0.30); tick(0.30)
assert scene.camera == current
s.recording=False
print('START_MENU_CAMERA_FLEET_SMOKE_OK')
