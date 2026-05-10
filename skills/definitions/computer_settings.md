---
name: computer_settings
trigger: When the user wants to adjust volume, brightness, WiFi, power settings, or system shortcuts
freedom: low
gotchas:
  - Windows-only (pycaw for audio, pywinauto for UI automation)
  - Some settings require admin privileges
  - Brightness control requires dedicated hardware support
---

Actions: volume_up, volume_down, mute, brightness_up, brightness_down, wifi_toggle, power_sleep, power_shutdown, shortcut
Use pycaw for audio: AudioUtilities.GetSpeakers().Activate().IChannel.SetMasterVolume()
Use powercfg for power plans on Windows.