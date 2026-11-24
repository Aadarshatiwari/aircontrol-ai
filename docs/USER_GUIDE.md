# User guide

1. Select **Start camera** and grant Camera access in the macOS prompt. Practice in **Simulation** using the cyan preview pointer and Activity tab.
2. Select a control mode. Each mode change returns output to simulation. Select **Enable live control**, grant Accessibility access if prompted, and confirm. Point steadily again before giving commands.
3. For media, shortcuts and presentation, bring the target application to the foreground. Presentation sends left and right arrow keys.
4. Press **Control–Option–Command–Escape** or click **Stop** to disarm. **Stop camera** also ends capture.

## Tuning and modes

- Increase sensitivity if comfortable motion cannot reach the screen edges. Increase smoothing to reduce jitter. Recalibrate after changing your position. The cursor maps to the main display.
- Choose Left or Right for a consistent control hand. Auto keeps the acquired hand until tracking is interrupted. Keep your wrist visible and use even lighting.
- The virtual keyboard supports uppercase letters, digits, Space, Backspace and Enter. Compose text directly in Workspace. To type into another app, enable external typing, keep Workspace visible beside the target, and bring that target to the foreground.
- Drawing works in simulation and live control. Use **Clear canvas** to erase it. Drawing, composed text and activity are session data.
- Shortcut syntax accepts Cmd, Ctrl, Option and Shift plus a supported letter, digit, arrow, Space, Tab, Enter, Escape or Backspace. Letter combinations use physical key positions. You can save a different key combination for each gesture bound to Shortcut.
- The confidence readout reports MediaPipe’s handedness category score.

## Troubleshooting

- Camera and Accessibility permissions are under **System Settings → Privacy & Security**. When running from source, macOS may attribute a request to Terminal or VS Code. Relaunch after changing permissions if needed.
- If the global shortcut could not register, close the conflicting app or other AirControl instance and relaunch. Simulation remains available.
- AirControl uses camera index 0. If a device is unavailable, close competing camera apps or disconnect external cameras and retry.
- Media keys are routed by macOS to the current media session and output device. Test shortcuts in the application you intend to control.
