import sys
from pathlib import Path
import bpy
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
# Legacy names are discovered.
rig=bpy.data.objects.new('Drone_Rig', None); gim=bpy.data.objects.new('Drone_Gimbal', None); roll=bpy.data.objects.new('Drone_Roll', None)
for o in (rig,gim,roll): bpy.context.collection.objects.link(o)
assert d.get_rig_objects()==(rig,gim)
assert d.get_roll_object()==roll
# Legacy DFR actions are reused as compatibility evidence.
scene=bpy.context.scene; scene.drone_flight_recorder_settings.active_take_slot=1
act=bpy.data.actions.new('DFR_Drone_Rig_Take_01'); rig.animation_data_create(); rig.animation_data.action=act
assert d.find_take_action(rig,1) == act
# Runtime icon/menu/operators are registered and callable enough in background.
assert hasattr(bpy.ops.lab, 'activate')
assert any(cls.__name__ == 'LAB_MT_controller_controls' for cls in d.classes)
assert d.ensure_icon_runtime() is True
print('ICON_RUNTIME_LEGACY_SMOKE_OK')
