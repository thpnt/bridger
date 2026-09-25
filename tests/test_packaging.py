from __future__ import annotations

import subprocess
import tarfile
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "src" / "bridger"
LICENSE_FILES = (
    "LICENSE",
    "THIRD_PARTY_NOTICES/Graphify/LICENSE",
    "THIRD_PARTY_NOTICES/Graphify/LICENSE-MIT",
    "THIRD_PARTY_NOTICES/Graphify/NOTICE",
    "THIRD_PARTY_NOTICES/Graphify/ATTRIBUTION.md",
)


def _package_files() -> set[str]:
    return {
        (Path("bridger") / path.relative_to(PACKAGE_ROOT)).as_posix()
        for path in PACKAGE_ROOT.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }


def test_built_distributions_include_runtime_files_and_notices(
    tmp_path: Path,
) -> None:
    subprocess.run(
        [
            "uv",
            "build",
            "--no-sources",
            "--out-dir",
            str(tmp_path),
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    wheel_path = tmp_path / "usebridger-0.1.0-py3-none-any.whl"
    sdist_path = tmp_path / "usebridger-0.1.0.tar.gz"
    assert wheel_path.is_file()
    assert sdist_path.is_file()

    package_files = _package_files()
    with zipfile.ZipFile(wheel_path) as wheel:
        wheel_files = set(wheel.namelist())
        assert package_files <= wheel_files

        metadata_path = next(
            name for name in wheel_files if name.endswith(".dist-info/METADATA")
        )
        dist_info = metadata_path.removesuffix("/METADATA")
        wheel_licenses = {f"{dist_info}/licenses/{path}" for path in LICENSE_FILES}
        assert wheel_licenses <= wheel_files
        metadata = wheel.read(metadata_path).decode("utf-8")
        assert "Name: usebridger\n" in metadata
        assert "Version: 0.1.0\n" in metadata
        assert "License-Expression: Apache-2.0\n" in metadata
        assert "Requires-Dist: black" not in metadata

        entry_points = wheel.read(f"{dist_info}/entry_points.txt").decode("utf-8")
        assert "bridger = bridger.cli:app" in entry_points

    with tarfile.open(sdist_path, "r:gz") as sdist:
        source_files = set(sdist.getnames())
        prefix = "usebridger-0.1.0"
        sdist_package_files = {f"{prefix}/src/{path}" for path in package_files}
        sdist_license_files = {f"{prefix}/{path}" for path in LICENSE_FILES}
        assert sdist_package_files <= source_files
        assert sdist_license_files <= source_files
