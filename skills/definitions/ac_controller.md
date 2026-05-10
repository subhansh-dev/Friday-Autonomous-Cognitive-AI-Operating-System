---
name: ac_controller
trigger: When the user wants to control the air conditioner
freedom: low
gotchas:
  - Requires AC brand config in config/ac_brands.json
  - Broadlink RM must be on same network as AC
  - Some ACs use IR, others use WiFi — know the type
---

action: "on", "off", "set_temp", "set_mode", "swing"
temperature: number — target temperature (16-30°C)
mode: "cool", "heat", "fan", "auto"
Uses Broadlink RM Mini 3 for IR or AC WiFi control.