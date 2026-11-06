"""Render portable LaunchAgent templates and register the current checkout."""
from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
import sys
from pathlib import Path

from .config import APP_ROOT


def render_agents(repo_root: Path) -> list[tuple[Path, dict]]:
    python = repo_root / ".venv" / "bin" / "python"
    if not python.is_file():
        raise SystemExit("Missing .venv/bin/python. Run uv sync --locked first.")
    agents = []
    for template in sorted((repo_root / "launchd").glob("*.example.plist")):
        payload = plistlib.loads(template.read_bytes())

        def expand(value):
            if isinstance(value, str):
                return value.replace("@REPO_ROOT@", str(repo_root)).replace(
                    "@PYTHON@", str(python)
                )
            if isinstance(value, list):
                return [expand(item) for item in value]
            if isinstance(value, dict):
                return {key: expand(item) for key, item in value.items()}
            return value

        payload = expand(payload)
        payload["WorkingDirectory"] = str(repo_root)
        agents.append((template.with_name(template.name.replace(".example", "")), payload))
    if len(agents) != 2:
        raise SystemExit("Expected exactly two LaunchAgent templates.")
    return agents


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render-only", action="store_true")
    args = parser.parse_args()
    if sys.platform != "darwin" and not args.render_only:
        raise SystemExit("LaunchAgent registration requires macOS.")

    agents = render_agents(APP_ROOT)
    destination = Path.home() / "Library" / "LaunchAgents"
    domain = f"gui/{os.getuid()}"
    if not args.render_only:
        # Check conflicts before unloading or replacing either job.
        for path, _ in agents:
            link = destination / path.name
            if os.path.lexists(link) and (
                not link.is_symlink() or link.resolve() != path.resolve()
            ):
                raise SystemExit(f"Refusing to replace unrelated LaunchAgent: {link}")
        subprocess.run(["launchctl", "print", domain], check=True, stdout=subprocess.DEVNULL)
        for _, payload in agents:
            service = f"{domain}/{payload['Label']}"
            loaded = subprocess.run(
                ["launchctl", "print", service],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            if loaded.returncode == 0:
                subprocess.run(["launchctl", "bootout", service], check=True)

    (APP_ROOT / ".local" / "logs").mkdir(parents=True, exist_ok=True)
    for path, payload in agents:
        # Parse and serialize XML so repository paths containing & remain valid.
        temporary = path.with_suffix(".plist.tmp")
        temporary.write_bytes(plistlib.dumps(payload, sort_keys=False))
        temporary.replace(path)
        print(f"Rendered {path.name}: {payload['Label']}")

    if not args.render_only:
        destination.mkdir(parents=True, exist_ok=True)
        for path, payload in agents:
            link = destination / path.name
            if not os.path.lexists(link):
                link.symlink_to(path)
            subprocess.run(["launchctl", "bootstrap", domain, str(link)], check=True)
            print(f"Registered {payload['Label']} (RunAtLoad starts it immediately)")


if __name__ == "__main__":
    main()
