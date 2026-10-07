"""Foundation layout test (C-01 task 1.1) — synthetic paths only."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"

EXPECTED_DIRS = [
    "domain",
    "application",
    "infrastructure",
    "api",
    "worker",
    "shared",
]


def test_app_package_exists():
    assert (ROOT / "backend" / "app" / "__init__.py").is_file()
    assert (ROOT / "backend" / "tests" / "__init__.py").is_file()


def test_all_bounded_context_packages_exist_with_init():
    for pkg in EXPECTED_DIRS:
        assert (APP / pkg).is_dir(), f"missing package dir: {pkg}"
        assert (APP / pkg / "__init__.py").is_file(), f"missing __init__.py: {pkg}"
