"""Desktop settings / icon-theme / monitor glue for SigmaOS-desktop-library
(inspired by cinnamon-desktop and cinnamon-settings-daemon).

Principles: schema-validated settings (defensive), fail-fast on unknown keys,
pure monitor-layout planning (testable without a compositor), deterministic
ordering, separation of the plan layer (pure) from the apply layer (side effects).
"""
import argparse, json, os, subprocess, sys, tempfile

ENGINE = {
    "name": "sigma-desktop",
    "summary": "Desktop settings, icon themes and monitor layout planner",
    "language": "python",
    "verbs": ["settings-get", "settings-set", "icon-theme", "monitor-plan"],
    "principles": ["Abstraction", "Defensive Programming", "Fail-Fast",
                   "Separation of Concerns", "KISS", "Deterministic Testing"],
}

cli_doc = """\
$ sigma-desktop settings-get org.sigma.desktop.icon-theme
Mint-Y
$ sigma-desktop settings-set org.sigma.desktop.clock-format 12h
org.sigma.desktop.clock-format = 12h
$ sigma-desktop icon-theme --list
$ sigma-desktop monitor-plan --monitor eDP-1:1920x1080 --monitor HDMI-1:2560x1440@1.5 --primary eDP-1
xrandr --output eDP-1 --mode 1920x1080 --pos 0x0 --scale 1.0x1.0 --primary
xrandr --output HDMI-1 --mode 2560x1440 --pos 1920x0 --scale 1.5x1.5
"""

DEFAULT_STORE = os.path.expanduser("~/.config/sigma-desktop/settings.json")

SCHEMA = {
    "org.sigma.desktop.background": str,
    "org.sigma.desktop.icon-theme": ("Mint-Y", "Mint-Y-Dark", "Mint-X", "Papirus", "hicolor"),
    "org.sigma.desktop.font": str,
    "org.sigma.desktop.clock-format": ("24h", "12h"),
    "org.sigma.desktop.workspaces": int,
}

DEFAULTS = {
    "org.sigma.desktop.background": "file:///usr/share/backgrounds/sigma.jpg",
    "org.sigma.desktop.icon-theme": "Mint-Y",
    "org.sigma.desktop.font": "Sans 10",
    "org.sigma.desktop.clock-format": "24h",
    "org.sigma.desktop.workspaces": 4,
}


class DesktopError(ValueError):
    pass


def validate_value(key, value):
    """Validate a raw setting value against the schema. Pure. Returns typed value."""
    if key not in SCHEMA:
        raise DesktopError(f"unknown key: {key}")
    spec = SCHEMA[key]
    if isinstance(spec, tuple):
        if str(value) not in spec:
            raise DesktopError(f"{key} must be one of {spec}, got {value!r}")
        return str(value)
    if spec is int:
        try:
            n = int(value)
        except (TypeError, ValueError):
            raise DesktopError(f"{key} must be an integer, got {value!r}")
        if not 1 <= n <= 32:
            raise DesktopError(f"{key} must be 1..32, got {n}")
        return n
    if not str(value).strip():
        raise DesktopError(f"{key} must be a non-empty string")
    return str(value)


def load_settings(path):
    """Return settings dict, starting from defaults, overlaid by the store."""
    settings = dict(DEFAULTS)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for k, v in data.items():
            settings[k] = validate_value(k, v)  # fail-fast on corrupt store
    return settings


def save_settings(path, settings):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".sigma-tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


def get_setting(settings, key):
    if key not in SCHEMA:
        raise DesktopError(f"unknown key: {key}")
    return settings.get(key, DEFAULTS[key])


def set_setting(settings, key, value):
    """Return a NEW settings dict with key set to a validated value (pure)."""
    out = dict(settings)
    out[key] = validate_value(key, value)
    return out


def parse_monitor(spec):
    """Parse 'NAME:WxH[@SCALE]' into a monitor dict. Pure."""
    try:
        name, geom = spec.split(":", 1)
        wxh, *rest = geom.split("@")
        w, h = (int(v) for v in wxh.split("x"))
        scale = float(rest[0]) if rest else 1.0
    except (ValueError, AttributeError) as e:
        raise DesktopError(f"bad monitor spec: {spec!r} (want NAME:WxH[@SCALE])") from e
    if not name or w <= 0 or h <= 0 or scale <= 0:
        raise DesktopError(f"bad monitor spec: {spec!r}")
    return {"name": name, "w": w, "h": h, "scale": scale}


def plan_monitors(monitors, primary=None):
    """Lay monitors out left-to-right in the given (deterministic) order."""
    if not monitors:
        raise DesktopError("no monitors given")
    names = [m["name"] for m in monitors]
    if len(set(names)) != len(names):
        raise DesktopError("duplicate monitor names")
    primary = primary or names[0]
    if primary not in names:
        raise DesktopError(f"unknown primary monitor: {primary}")
    x, plan = 0, []
    for m in monitors:
        plan.append({**m, "x": x, "y": 0, "primary": m["name"] == primary})
        x += m["w"]
    return plan


def render_xrandr(plan):
    """Pure renderer: plan -> xrandr command list."""
    cmds = []
    for m in plan:
        cmd = (f"xrandr --output {m['name']} --mode {m['w']}x{m['h']}"
               f" --pos {m['x']}x{m['y']} --scale {m['scale']}x{m['scale']}")
        if m["primary"]:
            cmd += " --primary"
        cmds.append(cmd)
    return cmds


def apply_monitors(plan, runner=None):
    """Execute layer: run the commands against the real display server.

    self_test NEVER calls this without an injected (recording) runner.
    """
    cmds = render_xrandr(plan)
    if runner is None:
        runner = lambda cmd: subprocess.run(cmd.split(), check=True)
    for cmd in cmds:
        runner(cmd)
    return len(cmds)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=ENGINE["name"], description=ENGINE["summary"])
    p.add_argument("--store", default=DEFAULT_STORE, help="settings store (JSON)")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("settings-get", help="print a setting")
    g.add_argument("key")
    s = sub.add_parser("settings-set", help="validate & set a setting")
    s.add_argument("key")
    s.add_argument("value")
    it = sub.add_parser("icon-theme", help="get/set the icon theme")
    it.add_argument("--list", action="store_true", help="list known themes")
    it.add_argument("theme", nargs="?", help="theme to set (omit to print current)")
    mp = sub.add_parser("monitor-plan", help="plan monitor layout (pure)")
    mp.add_argument("--monitor", action="append", required=True,
                    help="monitor spec NAME:WxH[@SCALE] (repeatable)")
    mp.add_argument("--primary", default=None)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "settings-get":
            print(get_setting(load_settings(args.store), args.key))
        elif args.cmd == "settings-set":
            settings = set_setting(load_settings(args.store), args.key, args.value)
            save_settings(args.store, settings)
            print(f"{args.key} = {settings[args.key]}")
        elif args.cmd == "icon-theme":
            settings = load_settings(args.store)
            key = "org.sigma.desktop.icon-theme"
            if args.list:
                for t in SCHEMA[key]:
                    print(t)
            elif args.theme:
                settings = set_setting(settings, key, args.theme)
                save_settings(args.store, settings)
                print(f"{key} = {settings[key]}")
            else:
                print(get_setting(settings, key))
        elif args.cmd == "monitor-plan":
            monitors = [parse_monitor(s) for s in args.monitor]
            for cmd in render_xrandr(plan_monitors(monitors, args.primary)):
                print(cmd)
        return 0
    except (DesktopError, OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def self_test() -> None:
    # settings (pure)
    s = set_setting(DEFAULTS, "org.sigma.desktop.clock-format", "12h")
    assert get_setting(s, "org.sigma.desktop.clock-format") == "12h"
    assert get_setting(s, "org.sigma.desktop.workspaces") == 4
    for bad_key, bad_val in (("nope.key", "x"),
                             ("org.sigma.desktop.clock-format", "25h"),
                             ("org.sigma.desktop.workspaces", "0"),
                             ("org.sigma.desktop.font", "   ")):
        try:
            set_setting(DEFAULTS, bad_key, bad_val)
        except DesktopError:
            pass
        else:
            raise AssertionError(f"should reject {bad_key}={bad_val!r}")
    # persistence round-trip (tempdir only)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "settings.json")
        save_settings(path, s)
        assert load_settings(path)["org.sigma.desktop.clock-format"] == "12h"
        missing = os.path.join(d, "missing.json")
        assert load_settings(missing)["org.sigma.desktop.workspaces"] == 4
    # monitor planning (pure, deterministic)
    mons = [parse_monitor("eDP-1:1920x1080"), parse_monitor("HDMI-1:2560x1440@1.5")]
    plan = plan_monitors(mons, primary="HDMI-1")
    assert [m["x"] for m in plan] == [0, 1920]
    assert [m["primary"] for m in plan] == [False, True]
    assert plan[1]["scale"] == 1.5
    cmds = render_xrandr(plan)
    assert cmds[1] == "xrandr --output HDMI-1 --mode 2560x1440 --pos 1920x0 --scale 1.5x1.5 --primary"
    assert apply_monitors(plan, runner=lambda cmd: None) == 2  # injected sink
    for bad in ("eDP-1", "eDP-1:0x0", ":1920x1080", "eDP-1:wide"):
        try:
            parse_monitor(bad)
        except DesktopError:
            pass
        else:
            raise AssertionError(f"should reject monitor spec {bad!r}")
    try:
        plan_monitors(mons, primary="DP-9")
    except DesktopError:
        pass
    else:
        raise AssertionError("unknown primary not caught")
    try:
        plan_monitors([mons[0], mons[0]])
    except DesktopError:
        pass
    else:
        raise AssertionError("duplicate monitors not caught")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
