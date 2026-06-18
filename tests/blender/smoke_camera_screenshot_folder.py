import sys, os, shutil
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
cam_data=bpy.data.cameras.new('Smoke_Cam_Data'); cam=bpy.data.objects.new('Smoke_Cam', cam_data)
bpy.context.collection.objects.link(cam); bpy.context.scene.camera=cam
bpy.context.scene.render.resolution_x=64; bpy.context.scene.render.resolution_y=64; bpy.context.scene.eevee.taa_render_samples=1 if hasattr(bpy.context.scene, 'eevee') else 1
root=Path('/home/lmtlssss/Desktop/last-airblender-release/tmp/smoke_screenshot_project')
if root.exists(): shutil.rmtree(root)
root.mkdir(parents=True)
bpy.ops.wm.save_as_mainfile(filepath=str(root/'smoke_project.blend'))
folder=d._drone_screenshot_base_dir(bpy.context.scene)
print('SCREENSHOT_FOLDER', folder)
assert folder == str(root/'last_airblender_screenshots')
path=d._capture_drone_screenshot(bpy.context.scene)
print('SCREENSHOT_PATH', path)
assert path.startswith(folder + os.sep)
assert os.path.exists(path) and os.path.getsize(path) > 0
assert os.path.basename(path).startswith('smoke_project_camera_')
assert bpy.context.scene.drone_flight_recorder_settings.last_screenshot_path == path
print('CAMERA_SCREENSHOT_FOLDER_SMOKE_OK')
