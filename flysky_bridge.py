"""FlySky FS-i6X -> sanal Xbox 360 kolu köprüsü (Bodycam FPV dronu için).

Kullanım:
  python flysky_bridge.py            Köprüyü çalıştırır (ayar yoksa önce kalibrasyon yapar)
  python flysky_bridge.py --calibrate  Yalnızca kalibrasyon yapar
  python flysky_bridge.py --assign-spawn  Yalnızca drone çıkarma anahtarını atar
  python flysky_bridge.py --seconds N  N saniye çalışıp çıkar (test için)

Oyundaki kol düzeni: sol çubuk = gaz/yaw, sağ çubuk = pitch/roll, LB = uçuş modu.
"""
import argparse
import ctypes
import json
import sys
import threading
import time
import winsound
from ctypes import wintypes
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("flysky_config.json")
VID, PID = 0x284E, 0x79A1
AXES = "XYZRUV"
JOY_RETURNALL = 255
DEADZONE = 0.02
LB_PULSE_S = 0.08
MIN_DELTA = 8000

# Drone çıkarma makrosu: kumanda anahtarı -> 5 tuşu, kısa bekleme, sol tık
SPAWN_CLICK_DELAY_S = 0.6  # Drone eline gelmeden tıklanıyorsa bu süreyi artır
TAP_HOLD_S = 0.05
GAME_EXE = "bodycam-win64-shipping.exe"
SCANCODE_5 = 0x06
KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x0002, 0x0008
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

winmm = ctypes.WinDLL("winmm")
user32 = ctypes.WinDLL("user32")
kernel32 = ctypes.WinDLL("kernel32")
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def send_input(item):
    return user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(INPUT))


def key_event(scancode, flags=0):
    item = INPUT(type=INPUT_KEYBOARD)
    item.u.ki = KEYBDINPUT(wScan=scancode, dwFlags=KEYEVENTF_SCANCODE | flags)
    return send_input(item)


def mouse_event(flags):
    item = INPUT(type=INPUT_MOUSE)
    item.u.mi = MOUSEINPUT(dwFlags=flags)
    return send_input(item)


def game_is_foreground():
    """Öndeki pencere Bodycam mi? Makro başka pencereye tıklamasın diye kontrol edilir."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return False
    try:
        size = wintypes.DWORD(1024)
        path = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
            return False
        return path.value.lower().endswith(GAME_EXE)
    finally:
        kernel32.CloseHandle(handle)


def spawn_macro(done):
    """5 tuşuna basar, drone ele gelene kadar bekler, sol tıklar."""
    try:
        key_event(SCANCODE_5)
        time.sleep(TAP_HOLD_S)
        key_event(SCANCODE_5, KEYEVENTF_KEYUP)
        time.sleep(SPAWN_CLICK_DELAY_S)
        if game_is_foreground():  # Bekleme sırasında alt-tab yapıldıysa tıklama
            mouse_event(MOUSEEVENTF_LEFTDOWN)
            time.sleep(TAP_HOLD_S)
            mouse_event(MOUSEEVENTF_LEFTUP)
    finally:
        done.set()


class JOYINFOEX(ctypes.Structure):
    _fields_ = [(n, wintypes.DWORD) for n in (
        "dwSize", "dwFlags", "X", "Y", "Z", "R", "U", "V", "dwButtons",
        "dwButtonNumber", "dwPOV", "dwReserved1", "dwReserved2")]


class JOYCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid", wintypes.WORD), ("wPid", wintypes.WORD),
        ("szPname", wintypes.WCHAR * 32),
        ("rest", ctypes.c_byte * 660),  # joyGetDevCapsW tam 728 bayt ister
    ]


def find_joystick():
    """Kumandanın winmm kimliğini VID/PID ile bulur; bulamazsa None döner."""
    for joy_id in range(16):
        caps = JOYCAPSW()
        if winmm.joyGetDevCapsW(joy_id, ctypes.byref(caps), ctypes.sizeof(caps)) != 0:
            continue
        if caps.wMid == VID and caps.wPid == PID:
            info = JOYINFOEX(dwSize=ctypes.sizeof(JOYINFOEX), dwFlags=JOY_RETURNALL)
            if winmm.joyGetPosEx(joy_id, ctypes.byref(info)) == 0:
                return joy_id
    return None


def read(joy_id):
    """(6 eksen listesi, düğme bit maskesi) döner; kumanda koptuysa None."""
    info = JOYINFOEX(dwSize=ctypes.sizeof(JOYINFOEX), dwFlags=JOY_RETURNALL)
    if winmm.joyGetPosEx(joy_id, ctypes.byref(info)) != 0:
        return None
    return [info.X, info.Y, info.Z, info.R, info.U, info.V], info.dwButtons


def wait_for_joystick():
    joy_id = find_joystick()
    if joy_id is None:
        print("Kumanda bulunamadı: kabloyu ve kumandanın açık olduğunu kontrol et...")
    while joy_id is None:
        time.sleep(1)
        joy_id = find_joystick()
    # Sürücü açılışta ilk okumalarda boş değer döndürür; gerçek veri gelene kadar at.
    end = time.time() + 0.5
    while time.time() < end:
        read(joy_id)
        time.sleep(0.02)
    return joy_id


def countdown(seconds):
    for left in range(seconds, 0, -1):
        print(f"  {left}...", flush=True)
        winsound.Beep(800, 80)
        time.sleep(0.92)


def averaged_axes(joy_id, duration=0.5):
    samples, end = [], time.time() + duration
    while time.time() < end:
        state = read(joy_id)
        if state:
            samples.append(state[0])
        time.sleep(0.01)
    return [sum(col) / len(col) for col in zip(*samples)]


def detect_axis(joy_id, baseline, used, instruction):
    """Talimattaki hareketin hangi ekseni, hangi yönde değiştirdiğini bulur."""
    while True:
        print(f"\n>>> {instruction}")
        countdown(5)
        held = averaged_axes(joy_id)
        deltas = [(abs(h - b), i, h - b) for i, (h, b) in enumerate(zip(held, baseline))
                  if i not in used]
        size, axis, delta = max(deltas)
        winsound.Beep(1200, 150)
        if size >= MIN_DELTA:
            print(f"  Algılandı: {AXES[axis]} ekseni ({'ters' if delta < 0 else 'düz'})")
            print("  Çubuğu bırak.")
            time.sleep(2)
            return axis, delta < 0
        print("  Hareket algılanmadı, tekrar deniyoruz.")


def detect_switch(joy_id, used, purpose, skip_message, ignored_buttons=0):
    """Bir görev için anahtarı algılar. (tür, numara) döner; atlanırsa None."""
    print(f"\n>>> {purpose} için kullanacağın 2 konumlu ANAHTARI (örn. SWA) 6 saniye içinde çevir.")
    print("    Anahtar kullanmak istemiyorsan hiçbir şeye dokunma.")
    start_axes, start_buttons = read(joy_id)
    end = time.time() + 6
    while time.time() < end:
        axes, buttons = read(joy_id)
        changed = (buttons ^ start_buttons) & ~ignored_buttons
        if changed:
            bit = (changed & -changed).bit_length() - 1
            print(f"  Algılandı: düğme {bit}")
            return {"type": "button", "index": bit}
        for i, (now, first) in enumerate(zip(axes, start_axes)):
            if i not in used and abs(now - first) >= MIN_DELTA:
                print(f"  Algılandı: {AXES[i]} ekseni")
                return {"type": "axis", "index": i}
        time.sleep(0.01)
    print(f"  Anahtar seçilmedi; {skip_message}")
    return None


def save_config(config):
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


def assign_spawn_switch(joy_id, config):
    """Drone çıkarma anahtarını sorar; uçuş modu anahtarıyla çakışmasına izin vermez."""
    used = {entry["axis"] for entry in config["axes"].values()}
    ignored_buttons = 0
    mode = config.get("mode_switch")
    if mode and mode["type"] == "axis":
        used.add(mode["index"])
    elif mode:
        ignored_buttons = 1 << mode["index"]
    spawn = detect_switch(joy_id, used, "Drone çıkarma",
                          "drone çıkarma makrosu kapalı kalacak.", ignored_buttons)
    if spawn:
        config["spawn_switch"] = spawn
        save_config(config)
    return config


def calibrate():
    joy_id = wait_for_joystick()
    print("=== FS-i6X KALİBRASYON ===")
    print("Mode 1 düzeni: sağ çubuk gaz+roll, sol çubuk pitch+yaw.")
    print("\n>>> Sol çubuğu bırak, GAZI (sağ çubuk) EN ALTA indir.")
    countdown(5)
    baseline = averaged_axes(joy_id)

    mapping, used = {}, set()
    for name, instruction in (
        ("roll", "Sağ çubuğu tamamen SAĞA it ve tut (gaz altta kalsın)."),
        ("pitch", "Sol çubuğu tamamen YUKARI it ve tut."),
        ("yaw", "Sol çubuğu tamamen SAĞA it ve tut."),
        ("throttle", "Gazı (sağ çubuk) tamamen YUKARI it ve tut."),
    ):
        axis, invert = detect_axis(joy_id, baseline, used, instruction)
        used.add(axis)
        mapping[name] = {"axis": axis, "invert": invert}

    print("\n>>> Sıradaki 10 saniye boyunca iki çubuğu da köşelerde tam daire çevir.")
    winsound.Beep(1000, 200)
    low, high = list(baseline), list(baseline)
    end = time.time() + 10
    while time.time() < end:
        axes, _ = read(joy_id)
        low = [min(a, b) for a, b in zip(low, axes)]
        high = [max(a, b) for a, b in zip(high, axes)]
        time.sleep(0.005)
    for name, entry in mapping.items():
        i = entry["axis"]
        if high[i] - low[i] < MIN_DELTA * 2:
            raise SystemExit(f"{name} ekseninde yeterli hareket görülmedi; kalibrasyonu tekrarla.")
        entry.update(min=low[i], max=high[i], center=baseline[i])

    print("\n>>> Çubukları bırak, gazı indir.")
    time.sleep(2)
    mode_switch = detect_switch(joy_id, used, "Uçuş modu",
                                "uçuş modunu klavye veya oyun içinden değiştirirsin.")
    config = {"axes": mapping, "mode_switch": mode_switch}
    save_config(config)
    time.sleep(1)
    assign_spawn_switch(joy_id, config)
    print(f"\nKalibrasyon kaydedildi: {CONFIG_PATH}")
    winsound.Beep(1500, 300)
    return config


def centered(value, entry):
    """Ortası yaylı bir ekseni -1..1 aralığına çevirir."""
    center = entry["center"]
    span = (entry["max"] - center) if value >= center else (center - entry["min"])
    out = (value - center) / max(span, 1)
    if abs(out) < DEADZONE:
        out = 0.0
    out = max(-1.0, min(1.0, out))
    return -out if entry["invert"] else out


def throttle(value, entry):
    """Gazı tüm stroku kullanarak çevirir: en alt -1, en üst +1."""
    out = (value - entry["min"]) / max(entry["max"] - entry["min"], 1) * 2 - 1
    out = max(-1.0, min(1.0, out))
    return -out if entry["invert"] else out


def switch_state(axes, buttons, switch):
    if switch["type"] == "button":
        return bool(buttons >> switch["index"] & 1)
    return axes[switch["index"]] > 32767


def run(config, seconds=None):
    import vgamepad as vg

    pad = vg.VX360Gamepad()
    lb = vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER
    mapping, switch = config["axes"], config["mode_switch"]
    winmm.timeBeginPeriod(1)
    joy_id = wait_for_joystick()
    print("Köprü çalışıyor: Bodycam sanal Xbox kolunu görüyor. Çıkış için Ctrl+C.")
    spawn_switch = config.get("spawn_switch")
    if spawn_switch:
        print("Drone anahtarını her çevirişte drone çıkar (5 + sol tık, yalnızca oyun öndeyken).")
    else:
        print("Drone anahtarı atanmadı; atamak için Drone_Anahtari_Ata.bat dosyasını çalıştır.")

    last_switch, lb_until, last_print, started = None, 0.0, 0.0, time.time()
    last_spawn = None
    macro_idle = threading.Event()
    macro_idle.set()
    try:
        while seconds is None or time.time() - started < seconds:
            state = read(joy_id)
            if state is None:
                pad.reset()
                pad.left_joystick_float(0.0, -1.0)  # Bağlantı koptu: gazı kes
                pad.update()
                print("\nKumanda koptu, gaz kesildi; yeniden bağlanması bekleniyor...")
                joy_id = wait_for_joystick()
                last_switch = None
                last_spawn = None
                continue
            axes, buttons = state

            if spawn_switch:
                current_spawn = switch_state(axes, buttons, spawn_switch)
                if (last_spawn is not None and current_spawn != last_spawn
                        and macro_idle.is_set() and game_is_foreground()):
                    macro_idle.clear()
                    threading.Thread(target=spawn_macro, args=(macro_idle,), daemon=True).start()
                last_spawn = current_spawn

            rx = centered(axes[mapping["roll"]["axis"]], mapping["roll"])
            ry = centered(axes[mapping["pitch"]["axis"]], mapping["pitch"])
            lx = centered(axes[mapping["yaw"]["axis"]], mapping["yaw"])
            ly = throttle(axes[mapping["throttle"]["axis"]], mapping["throttle"])
            pad.left_joystick_float(lx, ly)
            pad.right_joystick_float(rx, ry)

            now = time.time()
            if switch:
                current = switch_state(axes, buttons, switch)
                if last_switch is not None and current != last_switch:
                    lb_until = now + LB_PULSE_S
                last_switch = current
                if now < lb_until:
                    pad.press_button(lb)
                else:
                    pad.release_button(lb)
            pad.update()

            if now - last_print > 0.1:
                print(f"\rGaz {ly:+.2f}  Yaw {lx:+.2f}  Pitch {ry:+.2f}  Roll {rx:+.2f}  "
                      f"LB {'ON ' if now < lb_until else 'off'}", end="", flush=True)
                last_print = now
            time.sleep(0.004)
    except KeyboardInterrupt:
        pass
    finally:
        pad.reset()
        pad.update()
        winmm.timeEndPeriod(1)
        print("\nKöprü durdu.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--assign-spawn", action="store_true")
    parser.add_argument("--seconds", type=float)
    args = parser.parse_args()
    if args.calibrate:
        calibrate()
        return
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else calibrate()
    if args.assign_spawn or "spawn_switch" not in config:
        config = assign_spawn_switch(wait_for_joystick(), config)
    if args.assign_spawn:
        return
    run(config, args.seconds)


if __name__ == "__main__":
    sys.exit(main())
