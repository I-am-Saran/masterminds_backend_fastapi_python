#!/usr/bin/env python3
"""Flatten legacy modules, restore utils/, remove duplicate shims."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LEGACY_MAP = {
    "qa_dashboard": "app/reference_architecture/qa_dashboard/router.py",
    "convex_dashboard": "app/reference_architecture/convex_dashboard/router.py",
    "incident_register": "app/reference_architecture/incident_register/router.py",
    "risk_register": "app/reference_architecture/risk_register/router.py",
    "certifications": "app/reference_architecture/certifications/router.py",
    "bugs": "app/reference_architecture/bugs/router.py",
    "qa_master": "app/reference_architecture/qa_master/router.py",
}

UTILS_FROM_SHARED = [
    "error_handler.py",
    "api_wrapper.py",
    "permission_checker.py",
    "application_enum.py",
    "bugs_enum.py",
]


def main() -> None:
    legacy_dir = ROOT / "app" / "legacy"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "__init__.py").write_text(
        '"""Legacy / Kaizen modules — stable URLs, avoid new features here."""\n',
        encoding="utf-8",
    )

    for name, rel in LEGACY_MAP.items():
        src = ROOT / rel
        if not src.exists():
            continue
        dest = legacy_dir / f"{name}.py"
        shutil.copy2(src, dest)
        print(f"legacy: {rel} -> {dest.relative_to(ROOT)}")

    ref = ROOT / "app" / "reference_architecture"
    if ref.exists():
        shutil.rmtree(ref)

    shared = ROOT / "app" / "shared"
    utils = ROOT / "utils"
    for fname in UTILS_FROM_SHARED:
        s = shared / fname
        if s.exists():
            shutil.copy2(s, utils / fname)
            print(f"utils: restored {fname}")

    validator = ROOT / "app" / "admin" / "testcase_validator.py"
    if validator.exists():
        shutil.copy2(validator, utils / "testcase_validator.py")
        validator.unlink()

    if shared.exists():
        shutil.rmtree(shared)

    infra = ROOT / "app" / "infrastructure"
    if infra.exists():
        shutil.rmtree(infra)

    for stub in ("database.py", "security.py", "exceptions.py"):
        p = ROOT / "app" / "core" / stub
        if p.exists():
            p.unlink()

    routers = ROOT / "routers"
    if routers.exists():
        shutil.rmtree(routers)
        print("removed routers/ shims")

    app_logs = ROOT / "app" / "logs"
    if app_logs.exists() and not any(app_logs.iterdir()):
        app_logs.rmdir()

    print("done — update router_registry imports manually if script re-run")


if __name__ == "__main__":
    main()
