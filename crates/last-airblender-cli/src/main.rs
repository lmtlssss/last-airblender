use anyhow::{anyhow, Context, Result};
use clap::{Parser, Subcommand};
use gilrs::{Axis, Button, Gilrs};
use serde::Serialize;
use std::fs;
use std::net::UdpSocket;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

const ADDON: &str = include_str!("../../../addon/last_airblender.py");
const STARTUP_FILE: &str = "last_airblender_startup.py";
const ADDON_MODULE: &str = "last_airblender";
const ADDON_FILE: &str = "last_airblender.py";
const BRIDGE_ADDR: &str = "127.0.0.1:8765";
const SUPPORTED_BLENDER_VERSIONS: &[&str] = &[
    "3.6", "4.0", "4.1", "4.2", "4.3", "4.4", "4.5", "5.0", "5.1", "5.2",
];

#[derive(Parser)]
#[command(
    name = "last-airblender",
    version,
    about = "Fly Blender cameras with an Xbox-style controller and record cinematic takes."
)]
struct Cli {
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Install the bundled Blender add-on into the current user's Blender scripts folder.
    Install,
    /// Remove the add-on from discovered Blender user scripts folders.
    Uninstall,
    /// Launch Blender, start the controller bridge, and arm The Last AirBlender.
    Launch { blend: Option<PathBuf> },
    /// Run only the controller bridge that feeds Blender over localhost.
    Bridge,
    /// Check Blender, add-on, controller, and bridge readiness.
    Doctor,
    /// Print package/build information.
    PackageInfo,
}

#[derive(Serialize)]
struct Packet {
    lx: f32,
    ly: f32,
    rx: f32,
    ry: f32,
    lt: f32,
    rt: f32,
    a: bool,
    b: bool,
    x: bool,
    y: bool,
    lb: bool,
    rb: bool,
    select: bool,
    start: bool,
    dpad_x: i8,
    dpad_y: i8,
    timestamp_ms: u128,
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    match cli.cmd {
        Cmd::Install => install_addon(),
        Cmd::Uninstall => uninstall_addon(),
        Cmd::Launch { blend } => launch(blend),
        Cmd::Bridge => bridge(),
        Cmd::Doctor => doctor(),
        Cmd::PackageInfo => package_info(),
    }
}

fn package_info() -> Result<()> {
    println!("The Last AirBlender {}", env!("CARGO_PKG_VERSION"));
    println!("addon module: {ADDON_MODULE}");
    println!("bridge: udp://{BRIDGE_ADDR}");
    Ok(())
}

fn blender_user_roots() -> Vec<PathBuf> {
    let mut roots = Vec::new();
    if cfg!(target_os = "windows") {
        if let Some(appdata) = std::env::var_os("APPDATA") {
            roots.push(
                PathBuf::from(appdata)
                    .join("Blender Foundation")
                    .join("Blender"),
            );
        }
    } else if cfg!(target_os = "macos") {
        if let Some(home) = dirs::home_dir() {
            roots.push(home.join("Library/Application Support/Blender"));
        }
    } else if let Some(home) = dirs::home_dir() {
        roots.push(home.join(".config/blender"));
    }
    roots
}

fn addon_dirs() -> Vec<PathBuf> {
    let mut out = Vec::new();
    for root in blender_user_roots() {
        if let Ok(entries) = fs::read_dir(&root) {
            for e in entries.flatten() {
                let p = e.path();
                if p.is_dir() {
                    out.push(p.join("scripts/addons"));
                }
            }
        }
    }
    for root in blender_user_roots() {
        for v in SUPPORTED_BLENDER_VERSIONS {
            out.push(root.join(v).join("scripts/addons"));
        }
    }
    if out.is_empty() {
        if cfg!(target_os = "windows") {
            if let Some(appdata) = std::env::var_os("APPDATA") {
                out.push(
                    PathBuf::from(appdata).join("Blender Foundation/Blender/5.1/scripts/addons"),
                );
            }
        } else if cfg!(target_os = "macos") {
            if let Some(home) = dirs::home_dir() {
                out.push(home.join("Library/Application Support/Blender/5.1/scripts/addons"));
            }
        } else if let Some(home) = dirs::home_dir() {
            out.push(home.join(".config/blender/5.1/scripts/addons"));
        }
    }
    out.sort();
    out.dedup();
    out
}

fn startup_dirs() -> Vec<PathBuf> {
    let mut out = Vec::new();
    for root in blender_user_roots() {
        if let Ok(entries) = fs::read_dir(&root) {
            for e in entries.flatten() {
                let p = e.path();
                if p.is_dir() {
                    out.push(p.join("scripts/startup"));
                }
            }
        }
    }
    for root in blender_user_roots() {
        for v in SUPPORTED_BLENDER_VERSIONS {
            out.push(root.join(v).join("scripts/startup"));
        }
    }
    if out.is_empty() {
        if cfg!(target_os = "windows") {
            if let Some(appdata) = std::env::var_os("APPDATA") {
                for v in SUPPORTED_BLENDER_VERSIONS {
                    out.push(
                        PathBuf::from(&appdata)
                            .join(format!("Blender Foundation/Blender/{v}/scripts/startup")),
                    );
                }
            }
        } else if cfg!(target_os = "macos") {
            if let Some(home) = dirs::home_dir() {
                for v in SUPPORTED_BLENDER_VERSIONS {
                    out.push(home.join(format!(
                        "Library/Application Support/Blender/{v}/scripts/startup"
                    )));
                }
            }
        } else if let Some(home) = dirs::home_dir() {
            for v in SUPPORTED_BLENDER_VERSIONS {
                out.push(home.join(format!(".config/blender/{v}/scripts/startup")));
            }
        }
    }
    out.sort();
    out.dedup();
    out
}

fn startup_bootstrap() -> String {
    format!(
        r#"# Auto-installed by The Last AirBlender. Safe if the add-on is missing.
import os, sys, bpy, addon_utils, traceback

_LAB_BOOTED = False

def _lab_boot():
    global _LAB_BOOTED
    if _LAB_BOOTED:
        return
    try:
        here = os.path.dirname(__file__)
        addons = os.path.abspath(os.path.join(here, '..', 'addons'))
        if addons not in sys.path:
            sys.path.insert(0, addons)
        if not hasattr(bpy.types.Scene, 'drone_flight_recorder_settings'):
            addon_utils.enable('{ADDON_MODULE}', default_set=True, persistent=True)
        import {ADDON_MODULE} as lab
        if hasattr(lab, 'ensure_icon_runtime'):
            lab.ensure_icon_runtime()
        _LAB_BOOTED = True
    except Exception:
        traceback.print_exc()

def register():
    _lab_boot()

def unregister():
    pass

_lab_boot()
"#
    )
}

fn install_addon() -> Result<()> {
    let dirs = addon_dirs();
    if dirs.is_empty() {
        return Err(anyhow!("could not determine Blender add-ons folder"));
    }
    for dir in dirs {
        fs::create_dir_all(&dir).with_context(|| format!("creating {}", dir.display()))?;
        let dst = dir.join(ADDON_FILE);
        fs::write(&dst, ADDON).with_context(|| format!("writing {}", dst.display()))?;
        println!("installed {}", dst.display());
    }
    for dir in startup_dirs() {
        fs::create_dir_all(&dir).with_context(|| format!("creating {}", dir.display()))?;
        let dst = dir.join(STARTUP_FILE);
        fs::write(&dst, startup_bootstrap())
            .with_context(|| format!("writing {}", dst.display()))?;
        println!("installed {}", dst.display());
    }
    Ok(())
}

fn uninstall_addon() -> Result<()> {
    for dir in addon_dirs() {
        let dst = dir.join(ADDON_FILE);
        if dst.exists() {
            fs::remove_file(&dst).with_context(|| format!("removing {}", dst.display()))?;
            println!("removed {}", dst.display());
        }
    }
    for dir in startup_dirs() {
        let dst = dir.join(STARTUP_FILE);
        if dst.exists() {
            fs::remove_file(&dst).with_context(|| format!("removing {}", dst.display()))?;
            println!("removed {}", dst.display());
        }
    }
    Ok(())
}

fn find_blender() -> Result<PathBuf> {
    if let Ok(p) = std::env::var("BLENDER") {
        let pb = PathBuf::from(p);
        if pb.exists() {
            return Ok(pb);
        }
    }
    for name in ["blender", "blender.exe"] {
        if let Ok(p) = which::which(name) {
            return Ok(p);
        }
    }
    for p in [
        "/snap/bin/blender",
        "/usr/bin/blender",
        "/Applications/Blender.app/Contents/MacOS/Blender",
    ] {
        let pb = PathBuf::from(p);
        if pb.exists() {
            return Ok(pb);
        }
    }
    Err(anyhow!("Blender not found; set BLENDER=/path/to/blender"))
}

fn launch(blend: Option<PathBuf>) -> Result<()> {
    install_addon()?;
    let blender = find_blender()?;
    let mut bridge_child = spawn_bridge()?;
    let script = arm_script()?;
    let mut cmd = Command::new(blender);
    if let Some(blend) = blend {
        cmd.arg(blend);
    }
    cmd.arg("--python").arg(&script);
    let status = cmd.status().context("launching Blender")?;
    let _ = bridge_child.kill();
    if !status.success() {
        return Err(anyhow!("Blender exited with status {status}"));
    }
    Ok(())
}

fn spawn_bridge() -> Result<Child> {
    let exe = std::env::current_exe()?;
    Command::new(exe)
        .arg("bridge")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .context("starting controller bridge")
}

fn arm_script() -> Result<PathBuf> {
    let f = tempfile::Builder::new()
        .prefix("last_airblender_arm_")
        .suffix(".py")
        .tempfile()?;
    let (_file, path) = f.keep()?;
    let py = format!(
        r#"
import bpy, addon_utils, traceback
try:
    addon_utils.enable('{ADDON_MODULE}', default_set=True, persistent=True)
    import {ADDON_MODULE} as lab
    s = bpy.context.scene.drone_flight_recorder_settings
    s.recording = False
    s.first_person_view = False
    s.controller_device = 'bridge'
    s.deadzone = 0.08
    s.smoothing = 8.0
    s.max_speed = 2.0
    s.global_sensitivity_level = 2
    s.left_stick_gain = 1.0
    s.acceleration = 45.0
    s.active_take_slot = 1
    s.manual_bumper_thrust_multiplier = 1.0
    s.yaw_speed = 85.0
    s.gimbal_speed = 70.0
    s.roll_speed = 70.0
    s.roll_auto_level = False
    s.axis_dpad_y = 7
    s.dpad_up_direction = -1
    s.dpad_down_direction = 1
    s.invert_left_x = False
    s.invert_left_y = False
    s.invert_right_x = False
    s.invert_right_y = False
    s.joystick_invert_mode = 0
    bpy.ops.dfr.create_rig()
    ok = lab.start_controller_flight(bpy.context)
    layout_ok = lab.configure_drone_split_view_layout(bpy.context)
    print('LAST_AIRBLENDER_ARMED', ok, s.status)
    print('LAST_AIRBLENDER_SPLIT_VIEW', layout_ok)
except Exception:
    traceback.print_exc()
"#
    );
    fs::write(&path, py)?;
    Ok(path)
}

fn bridge() -> Result<()> {
    let mut gilrs = Gilrs::new().map_err(|e| anyhow!("gamepad init failed: {e}"))?;
    let sock = UdpSocket::bind("127.0.0.1:0")?;
    println!("The Last AirBlender bridge sending to {BRIDGE_ADDR}");
    loop {
        while gilrs.next_event().is_some() {}
        let packet = first_gamepad_packet(&gilrs);
        if let Some(pkt) = packet {
            let data = serde_json::to_vec(&pkt)?;
            let _ = sock.send_to(&data, BRIDGE_ADDR);
        }
        thread::sleep(Duration::from_millis(16));
    }
}

fn first_gamepad_packet(gilrs: &Gilrs) -> Option<Packet> {
    let (_id, gp) = gilrs.gamepads().find(|(_, g)| g.is_connected())?;
    let dpad_x = if gp.is_pressed(Button::DPadRight) {
        1
    } else if gp.is_pressed(Button::DPadLeft) {
        -1
    } else {
        0
    };
    let dpad_y = if gp.is_pressed(Button::DPadDown) {
        1
    } else if gp.is_pressed(Button::DPadUp) {
        -1
    } else {
        0
    };
    Some(Packet {
        lx: gp.value(Axis::LeftStickX),
        ly: -gp.value(Axis::LeftStickY),
        rx: gp.value(Axis::RightStickX),
        ry: -gp.value(Axis::RightStickY),
        lt: trigger_to_linux(gp.value(Axis::LeftZ)),
        rt: trigger_to_linux(gp.value(Axis::RightZ)),
        a: gp.is_pressed(Button::South),
        b: gp.is_pressed(Button::East),
        x: gp.is_pressed(Button::West),
        y: gp.is_pressed(Button::North),
        lb: gp.is_pressed(Button::LeftTrigger),
        rb: gp.is_pressed(Button::RightTrigger),
        select: gp.is_pressed(Button::Select),
        start: gp.is_pressed(Button::Start),
        dpad_x,
        dpad_y,
        timestamp_ms: SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis(),
    })
}

fn trigger_to_linux(v: f32) -> f32 {
    // Blender add-on expects Linux joystick trigger convention: -1 released, +1 pressed.
    (v.clamp(0.0, 1.0) * 2.0) - 1.0
}

fn doctor() -> Result<()> {
    println!("The Last AirBlender doctor");
    match find_blender() {
        Ok(p) => println!("✓ Blender: {}", p.display()),
        Err(e) => println!("✗ Blender: {e}"),
    }
    let dirs = addon_dirs();
    println!("add-on dirs:");
    for d in &dirs {
        let installed = d.join(ADDON_FILE).exists();
        println!("{} {}", if installed { "✓" } else { "-" }, d.display());
    }
    println!("startup runtimes:");
    for d in startup_dirs() {
        let installed = d.join(STARTUP_FILE).exists();
        println!("{} {}", if installed { "✓" } else { "-" }, d.display());
    }
    match Gilrs::new() {
        Ok(g) => {
            let pads: Vec<_> = g
                .gamepads()
                .filter(|(_, gp)| gp.is_connected())
                .map(|(_, gp)| gp.name().to_string())
                .collect();
            if pads.is_empty() {
                println!("- controller: none currently detected by gilrs");
            } else {
                println!("✓ controller: {}", pads.join(", "));
            }
        }
        Err(e) => println!("✗ controller backend: {e}"),
    }
    match UdpSocket::bind(BRIDGE_ADDR) {
        Ok(_) => println!("✓ bridge port available: {BRIDGE_ADDR}"),
        Err(e) => println!("- bridge port busy/unavailable: {e}"),
    }
    Ok(())
}
