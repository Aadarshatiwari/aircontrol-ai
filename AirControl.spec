from PyInstaller.utils.hooks import collect_dynamic_libs

analysis = Analysis(
    ["launcher.py"],
    binaries=collect_dynamic_libs("mediapipe"),
    datas=[
        ("assets/hand_landmarker.task", "assets"),
        ("assets/icon.png", "assets"),
        ("docs/GESTURES.md", "docs"),
    ],
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz, analysis.scripts, [], exclude_binaries=True,
    name="AirControl AI", console=False, target_arch="arm64",
)
collection = COLLECT(exe, analysis.binaries, analysis.datas, name="AirControl AI")
app = BUNDLE(
    collection,
    name="AirControl AI.app",
    icon="assets/AirControl.icns",
    bundle_identifier="org.aircontrolai.desktop",
    info_plist={
        "NSCameraUsageDescription": "AirControl uses the camera to recognize hand gestures on this Mac.",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "15.0",
        "NSHighResolutionCapable": True,
    },
)
