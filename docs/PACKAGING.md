# Package for macOS

On an Apple Silicon Mac with native Python 3.12, run:

```bash
./scripts/install.sh
./scripts/package.sh
open "dist/AirControl AI.app"
```

The build embeds the model, guide and icons, targets arm64, and includes the Camera usage description. Check the bundle on a Mac with fresh permissions. Run the physical acceptance checks below before distribution.

For public distribution, keep the bundle identifier stable, review and include third-party license notices and satisfy their redistribution requirements. Sign the finished bundle and nested native code with your Developer ID, include the camera entitlement if enabling the hardened runtime, submit for Apple notarization, and staple the ticket. The standard script produces a local build.

## Physical acceptance checks

- In simulation, verify a mirrored preview and 21 landmark dots per visible hand. Show both hands and verify the preferred-hand setting.
- Calibrate, move to each main-display corner, and test click, double click, right click and scrolling in a disposable window.
- Start a drag and remove the hand. Verify mouse-up and that the next pinch sends no input until you point again.
- Test slides, media keys and shortcuts in their target apps. Test local keyboard composition, focused-app typing and canvas strokes.
- With another app focused, press the emergency shortcut during a drag. Verify the drag releases and the UI returns to Simulation.
- Revoke Accessibility, then try arming. Deny Camera access and check the recovery message. Re-enable permissions and check normal operation after relaunch.
