"""
actions/ac_control.py
JARVIS MT67 — Universal AC Control
Supports: Hitachi (Hi-Kumo), LG (ThinQ), Daikin, Mitsubishi, Broadlink (any brand)

Setup in config/api_keys.json:
{
    "ac_brand": "hitachi",         <- hitachi / lg / daikin / mitsubishi / broadlink
    "ac_email": "your@email.com",  <- for cloud-based brands
    "ac_password": "yourpass",     <- for cloud-based brands
    "ac_ip": "192.168.1.x",        <- for Daikin local network
    "broadlink_ip": "192.168.1.x"  <- for Broadlink IR blaster
}

Voice commands JARVIS handles:
  "Turn on the AC"             "Turn off the AC"
  "Set AC to 22 degrees"       "Set fan to silent"
  "Switch to heat mode"        "Sleep mode" / "Eco mode"
  "What's the AC status?"      "What brands are supported?"
"""

import asyncio
import json
from pathlib import Path


# ── Config loader ─────────────────────────────────────────────────────────────
def _load_config() -> dict:
    try:
        f = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _cfg(key: str, default="") -> str:
    return _load_config().get(key, default)


# ── Universal maps ────────────────────────────────────────────────────────────
FAN_MAP = {
    "auto": "AUTO", "silent": "SILENT", "quiet": "SILENT",
    "low": "LV1",   "1": "LV1",
    "medium": "LV2","mid": "LV2", "2": "LV2",
    "high": "LV3",  "3": "LV3",
    "turbo": "LV4", "max": "LV4", "4": "LV4",
}
MODE_MAP = {
    "cool": "COOLING",  "cooling": "COOLING",
    "heat": "HEATING",  "heating": "HEATING",
    "dry": "DRYING",    "dehumidify": "DRYING",
    "fan": "FAN",       "ventilate": "FAN",
    "auto": "AUTO",
}
DAIKIN_MODE = {"cool":"3","heat":"4","dry":"2","fan":"6","auto":"1"}
DAIKIN_FAN  = {"auto":"A","silent":"B","low":"3","medium":"4","high":"5","turbo":"7"}

# Numeric maps for brands with stricter requirements
MIT_MODE = {"auto": 8, "cool": 3, "heat": 1, "dry": 2, "fan": 7}
MIT_FAN  = {"auto": 0, "low": 1, "medium": 2, "high": 3, "turbo": 5}


# ══════════════════════════════════════════════════════════════════════════════
# HITACHI — Hi-Kumo cloud
# pip install aircloudy
# ══════════════════════════════════════════════════════════════════════════════
class HitachiAC:
    def __init__(self):
        try:
            from aircloudy import HitachiAirCloud # type: ignore
            self._AC = HitachiAirCloud
        except ImportError:
            raise ImportError("Hitachi requires: pip install aircloudy")
        self.email = _cfg("ac_email")
        self.pw    = _cfg("ac_password")

    async def _unit(self, ac):
        u = ac.interior_units
        if not u: raise Exception("No Hi-Kumo AC units found.")
        return u[0]

    def turn_on(self, temp=24, fan="auto", mode="cool"):
        async def _go():
            async with self._AC(self.email, self.pw) as ac:
                u = await self._unit(ac)
                await ac.set(u.id, power="ON", 
                             requested_temperature=temp,
                             fan_speed=FAN_MAP.get(fan.lower(), "AUTO"),
                             ac_mode=MODE_MAP.get(mode.lower(), "COOLING"))
                return f"✅ Hitachi AC ON — {temp}°C | {mode} | Fan: {fan}"
        return asyncio.run(_go())

    def turn_off(self):
        async def _go():
            async with self._AC(self.email, self.pw) as ac:
                u = await self._unit(ac)
                await ac.set(u.id, "OFF")
                return "✅ Hitachi AC OFF."
        return asyncio.run(_go())

    def set_temperature(self, temp):
        async def _go():
            async with self._AC(self.email, self.pw) as ac:
                u = await self._unit(ac)
                await ac.set(u.id, requested_temperature=temp)
                return f"✅ Temperature → {temp}°C"
        return asyncio.run(_go())

    def set_fan(self, speed):
        async def _go():
            async with self._AC(self.email, self.pw) as ac:
                u = await self._unit(ac)
                await ac.set(u.id, fan_speed=FAN_MAP.get(speed.lower(),"AUTO"))
                return f"✅ Fan → {speed}"
        return asyncio.run(_go())

    def set_mode(self, mode):
        async def _go():
            async with self._AC(self.email, self.pw) as ac:
                u = await self._unit(ac)
                await ac.set(u.id, ac_mode=MODE_MAP.get(mode.lower(), "COOLING"))
                return f"✅ Hitachi mode → {mode}"
        return asyncio.run(_go())

    def status(self):
        async def _go():
            async with self._AC(self.email, self.pw) as ac:
                u = await self._unit(ac)
                return (
                    f"🌡️ Hitachi AC\n"
                    f"   Power    : {getattr(u,'on_off','?')}\n"
                    f"   Set Temp : {getattr(u,'requested_temperature','?')}°C\n"
                    f"   Room Temp: {getattr(u,'indoor_temperature','?')}°C\n"
                    f"   Fan      : {getattr(u,'fan_speed','?')}\n"
                    f"   Mode     : {getattr(u,'air_conditioning_mode','?')}"
                )
        return asyncio.run(_go())


# ══════════════════════════════════════════════════════════════════════════════
# LG — ThinQ cloud
# pip install thinq2
# ══════════════════════════════════════════════════════════════════════════════
class LGAC:
    def __init__(self):
        try:
            import thinq2 # type: ignore
            self.thinq2 = thinq2
        except ImportError:
            raise ImportError("LG requires: pip install thinq2")
        self.email = _cfg("ac_email")
        self.pw    = _cfg("ac_password")

    def _ac_device(self):
        client  = self.thinq2.ThinQClient(self.email, self.pw)
        devices = client.get_devices()
        ac = next((d for d in devices if "AC" in d.type.upper()), None)
        if not ac: raise Exception("No LG AC found on ThinQ account.")
        return client, ac

    def turn_on(self, temp=24, fan="auto", mode="cool"):
        try:
            client, ac = self._ac_device()
            client.send_command(ac.id, "Operation", "operation", "On")
            client.send_command(ac.id, "BasicCtrl", "SetValues", {
                "targetTemperature": temp,
                "airConditionerMode": MODE_MAP.get(mode.lower(), "COOLING")
            })
            return f"✅ LG AC ON — {temp}°C | {mode}"
        except Exception as e:
            return f"❌ LG error: {e}"

    def turn_off(self):
        try:
            client, ac = self._ac_device()
            client.send_command(ac.id, "Operation", "operation", "Off")
            return "✅ LG AC OFF."
        except Exception as e:
            return f"❌ LG error: {e}"

    def set_temperature(self, temp):
        try:
            client, ac = self._ac_device()
            client.send_command(ac.id, "BasicCtrl", "SetValues", {"targetTemperature": temp})
            return f"✅ LG temperature → {temp}°C"
        except Exception as e:
            return f"❌ LG error: {e}"

    def set_fan(self, speed):
        try:
            client, ac = self._ac_device()
            client.send_command(ac.id, "AirFlow", "windStrength", speed.upper())
            return f"✅ LG fan → {speed}"
        except Exception as e: return f"❌ LG error: {e}"

    def set_mode(self, mode):
        try:
            client, ac = self._ac_device()
            lg_mode = MODE_MAP.get(mode.lower(), "COOLING")
            client.send_command(ac.id, "Control", "airConditionerMode", lg_mode)
            return f"✅ LG mode → {mode}"
        except Exception as e: return f"❌ LG error: {e}"

    def status(self):
        try:
            client, ac = self._ac_device()
            snap = client.get_device_snapshot(ac.id)
            return (
                f"🌡️ LG AC\n"
                f"   Power: {snap.get('Operation',{}).get('operation','?')}\n"
                f"   Temp : {snap.get('TempCurTempC','?')}°C"
            )
        except Exception as e:
            return f"❌ LG status error: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# DAIKIN — Local WiFi (no cloud)
# pip install pydaikin
# ══════════════════════════════════════════════════════════════════════════════
class DaikinAC:
    def __init__(self):
        try:
            from pydaikin.daikin_base import Appliance # type: ignore
            self._App = Appliance
        except ImportError:
            raise ImportError("Daikin requires: pip install pydaikin")
        self.ip = _cfg("ac_ip")
        if not self.ip:
            raise Exception("Add 'ac_ip' to config/api_keys.json (Daikin's local IP)")

    def _d(self): return self._App(self.ip)

    def turn_on(self, temp=24, fan="auto", mode="cool"):
        try:
            self._d().set({
                "pow":    "1",
                "stemp":  str(temp),
                "f_rate": DAIKIN_FAN.get(fan.lower(),"A"),
                "mode":   DAIKIN_MODE.get(mode.lower(),"3"),
            })
            return f"✅ Daikin AC ON — {temp}°C | {mode}"
        except Exception as e:
            return f"❌ Daikin error: {e}"

    def turn_off(self):
        try:
            self._d().set({"pow":"0"})
            return "✅ Daikin AC OFF."
        except Exception as e:
            return f"❌ Daikin error: {e}"

    def set_temperature(self, temp):
        try:
            self._d().set({"stemp":str(temp),"pow":"1"})
            return f"✅ Daikin temperature → {temp}°C"
        except Exception as e:
            return f"❌ Daikin error: {e}"

    def set_fan(self, speed):
        try:
            self._d().set({"f_rate":DAIKIN_FAN.get(speed.lower(),"A"),"pow":"1"})
            return f"✅ Daikin fan → {speed}"
        except Exception as e:
            return f"❌ Daikin error: {e}"

    def set_mode(self, mode):
        try:
            self._d().set({"mode":DAIKIN_MODE.get(mode.lower(),"3"),"pow":"1"})
            return f"✅ Daikin mode → {mode}"
        except Exception as e:
            return f"❌ Daikin error: {e}"

    def status(self):
        try:
            info = self._d().values
            return (
                f"🌡️ Daikin AC\n"
                f"   Power    : {'ON' if info.get('pow')=='1' else 'OFF'}\n"
                f"   Set Temp : {info.get('stemp','?')}°C\n"
                f"   Room Temp: {info.get('htemp','?')}°C\n"
                f"   Fan      : {info.get('f_rate','?')}\n"
                f"   Mode     : {info.get('mode','?')}"
            )
        except Exception as e:
            return f"❌ Daikin status error: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# MITSUBISHI — MELCloud
# pip install pymelcloud
# ══════════════════════════════════════════════════════════════════════════════
class MitsubishiAC:
    def __init__(self):
        try:
            import pymelcloud # type: ignore
            self.pmc = pymelcloud
        except ImportError:
            raise ImportError("Mitsubishi requires: pip install pymelcloud")
        self.email = _cfg("ac_email")
        self.pw    = _cfg("ac_password")

    def _run(self, coro): return asyncio.run(coro)

    def turn_on(self, temp=24, fan="auto", mode="cool"):
        try:
            token   = self._run(self.pmc.login(self.email, self.pw))
            devices = self._run(self.pmc.get_devices(token))
            ac = devices[self.pmc.DEVICE_TYPE_ACA][0]
            self._run(ac.update())
            self._run(ac.set({
                "power": True,
                "set_temperature": temp,
                "operation_mode": MIT_MODE.get(mode.lower(), 3),
                "fan_speed": MIT_FAN.get(fan.lower(), 0)
            }))
            return f"✅ Mitsubishi AC ON — {temp}°C | {mode}"
        except Exception as e:
            return f"❌ Mitsubishi error: {e}"

    def turn_off(self):
        try:
            token   = self._run(self.pmc.login(self.email, self.pw))
            devices = self._run(self.pmc.get_devices(token))
            ac = devices[self.pmc.DEVICE_TYPE_ACA][0]
            self._run(ac.update())
            self._run(ac.set({"power": False}))
            return "✅ Mitsubishi AC OFF."
        except Exception as e:
            return f"❌ Mitsubishi error: {e}"

    def set_temperature(self, temp):
        try:
            token   = self._run(self.pmc.login(self.email, self.pw))
            devices = self._run(self.pmc.get_devices(token))
            ac = devices[self.pmc.DEVICE_TYPE_ACA][0]
            self._run(ac.update())
            self._run(ac.set({"set_temperature": temp}))
            return f"✅ Mitsubishi temperature → {temp}°C"
        except Exception as e:
            return f"❌ Mitsubishi error: {e}"

    def set_fan(self, speed):
        try:
            token   = self._run(self.pmc.login(self.email, self.pw))
            devices = self._run(self.pmc.get_devices(token))
            ac = devices[self.pmc.DEVICE_TYPE_ACA][0]
            self._run(ac.set({"fan_speed": MIT_FAN.get(speed.lower(), 0)}))
            return f"✅ Mitsubishi fan → {speed}"
        except Exception as e: return f"❌ Mitsubishi error: {e}"

    def set_mode(self, mode):
        try:
            token   = self._run(self.pmc.login(self.email, self.pw))
            devices = self._run(self.pmc.get_devices(token))
            ac = devices[self.pmc.DEVICE_TYPE_ACA][0]
            self._run(ac.set({"operation_mode": MIT_MODE.get(mode.lower(), 3)}))
            return f"✅ Mitsubishi mode → {mode}"
        except Exception as e: return f"❌ Mitsubishi error: {e}"

    def status(self):
        try:
            token   = self._run(self.pmc.login(self.email, self.pw))
            devices = self._run(self.pmc.get_devices(token))
            ac = devices[self.pmc.DEVICE_TYPE_ACA][0]
            self._run(ac.update())
            return (
                f"🌡️ Mitsubishi AC\n"
                f"   Power    : {'ON' if ac.power else 'OFF'}\n"
                f"   Set Temp : {ac.set_temperature}°C\n"
                f"   Room Temp: {ac.room_temperature}°C"
            )
        except Exception as e: return f"❌ Mitsubishi error: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# BROADLINK — Universal IR blaster (ANY brand)
# pip install broadlink
# Hardware: Broadlink RM4 Mini (~₹2500)
# ══════════════════════════════════════════════════════════════════════════════
class BroadlinkAC:
    """
    Works with literally any AC brand via IR.
    User records IR codes from their own remote once,
    saved to config/broadlink_codes.json.
    """
    def __init__(self):
        try:
            import broadlink # type: ignore
            self.bl = broadlink
        except ImportError:
            raise ImportError("Broadlink requires: pip install broadlink")
        self.ip     = _cfg("broadlink_ip")
        self._codes = self._load_codes()

    def _load_codes(self) -> dict:
        try:
            f = Path(__file__).resolve().parent.parent / "config" / "broadlink_codes.json"
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_codes(self):
        f = Path(__file__).resolve().parent.parent / "config" / "broadlink_codes.json"
        f.parent.mkdir(exist_ok=True)
        f.write_text(json.dumps(self._codes, indent=2))

    def _device(self):
        devs = self.bl.discover(timeout=5)
        if not devs: raise Exception("No Broadlink device found. Check WiFi.")
        dev = devs[0]
        dev.auth()
        return dev

    def _send(self, key: str) -> str:
        if key not in self._codes:
            return (f"❌ IR code '{key}' not recorded yet.\n"
                    f"   Say: 'JARVIS record IR code {key}'")
        try:
            self._device().send_data(bytes.fromhex(self._codes[key]))
            return f"✅ IR sent: {key}"
        except Exception as e:
            return f"❌ Broadlink error: {e}"

    def turn_on(self, temp=24, fan="auto", mode="cool"):
        key = f"on_{temp}c" if f"on_{temp}c" in self._codes else "power_on"
        return self._send(key)

    def turn_off(self):       return self._send("power_off")
    def set_temperature(self, temp): return self._send(f"temp_{temp}c")
    def set_fan(self, speed): return self._send(f"fan_{speed.lower()}")
    def set_mode(self, mode): return self._send(f"mode_{mode.lower()}")
    def status(self):         return "ℹ️ Broadlink IR — cannot read AC status (send only)."

    def record_code(self, code_name: str) -> str:
        """Point remote at Broadlink device and press the button."""
        import time
        try:
            dev = self._device()
            dev.enter_learning()
            print(f"⏳ Point remote at Broadlink and press button for '{code_name}'...")
            time.sleep(6)
            code = dev.check_data()
            if code:
                self._codes[code_name] = code.hex()
                self._save_codes()
                return f"✅ IR code '{code_name}' recorded!"
            return "❌ No signal detected. Try again closer to the device."
        except Exception as e:
            return f"❌ Recording error: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# DISPATCHER — Auto-picks brand from config
# ══════════════════════════════════════════════════════════════════════════════
BRANDS = {
    "hitachi":    HitachiAC,
    "lg":         LGAC,
    "daikin":     DaikinAC,
    "mitsubishi": MitsubishiAC,
    "broadlink":  BroadlinkAC,
    "any":        BroadlinkAC,
}

def _ac():
    brand = _cfg("ac_brand", "hitachi").lower().strip()
    cls   = BRANDS.get(brand)
    if not cls:
        raise Exception(f"Unknown ac_brand '{brand}'. Supported: {', '.join(BRANDS)}")
    return cls()


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC FUNCTIONS — JARVIS calls these
# ══════════════════════════════════════════════════════════════════════════════

def turn_on(temp: int = 24, fan: str = "auto", mode: str = "cool") -> str:
    if not (16 <= temp <= 32):
        return f"❌ Temp {temp}°C out of range (16–32°C)"
    try: return _ac().turn_on(temp=temp, fan=fan, mode=mode)
    except Exception as e: return f"❌ AC error: {e}"

def turn_off() -> str:
    try: return _ac().turn_off()
    except Exception as e: return f"❌ AC error: {e}"

def set_temperature(temp: int) -> str:
    if not (16 <= temp <= 32):
        return f"❌ Temp {temp}°C out of range (16–32°C)"
    try: return _ac().set_temperature(temp)
    except Exception as e: return f"❌ AC error: {e}"

def set_fan_speed(speed: str) -> str:
    if speed.lower() not in FAN_MAP:
        return f"❌ Unknown speed '{speed}'. Try: auto, low, medium, high, silent, turbo"
    try: return _ac().set_fan(speed)
    except Exception as e: return f"❌ AC error: {e}"

def set_mode(mode: str) -> str:
    if mode.lower() not in MODE_MAP:
        return f"❌ Unknown mode '{mode}'. Try: cool, heat, dry, fan, auto"
    try: return _ac().set_mode(mode)
    except Exception as e: return f"❌ AC error: {e}"

def sleep_mode() -> str:
    try: return _ac().turn_on(temp=26, fan="silent", mode="cool")
    except Exception as e: return f"❌ AC error: {e}"

def eco_mode() -> str:
    try: return _ac().turn_on(temp=28, fan="low", mode="cool")
    except Exception as e: return f"❌ AC error: {e}"

def get_status() -> str:
    try: return _ac().status()
    except Exception as e: return f"❌ AC error: {e}"

def record_ir_code(code_name: str) -> str:
    try:
        ac = _ac()
        if not isinstance(ac, BroadlinkAC):
            return "❌ IR recording only works with Broadlink. Set ac_brand to 'broadlink'."
        return ac.record_code(code_name)
    except Exception as e: return f"❌ Error: {e}"

def list_brands() -> str:
    return (
        "🌡️ Supported AC Brands:\n"
        "   hitachi    → Hi-Kumo app     (pip install aircloudy)\n"
        "   lg         → LG ThinQ app    (pip install thinq2)\n"
        "   daikin     → Local WiFi      (pip install pydaikin)\n"
        "   mitsubishi → MELCloud app    (pip install pymelcloud)\n"
        "   broadlink  → Any brand IR    (pip install broadlink)\n\n"
        "Set 'ac_brand' in config/api_keys.json"
    )


# ── Tool descriptor for JARVIS agent ─────────────────────────────────────────
TOOL_DESCRIPTION = """
Universal AC Control — Controls any AC brand via voice.
Brands: hitachi, lg, daikin, mitsubishi, broadlink (any brand via IR)
Config: set 'ac_brand', 'ac_email', 'ac_password' in api_keys.json

Functions: turn_on, turn_off, set_temperature, set_fan_speed,
           set_mode, sleep_mode, eco_mode, get_status, list_brands

Voice triggers:
  "turn on/off the AC", "set AC to X degrees",
  "fan low/high/silent", "cool/heat/dry mode",
  "sleep mode", "eco mode", "AC status"
"""

if __name__ == "__main__":
    print(list_brands())
    print(get_status())