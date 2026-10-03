#!/usr/bin/env python3
# Copyright 2026 Yong Bok Lee
# SPDX-License-Identifier: Apache-2.0
"""Build a reviewed diagnostic bundle. Building does not grant a license or publish it."""
from __future__ import annotations

import argparse
import base64
import csv
from email.parser import BytesParser
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = "release/public-files.json"


def reviewed_paths(root: Path) -> list[str]:
    record = json.loads((root / INVENTORY).read_text("utf-8"))
    if not isinstance(record, dict) or record.get("schema") != "payment-control-lab.public-inventory.v2":
        raise ValueError("Release inventory must explicitly separate public files and repository-only records.")
    paths, repository_only = record.get("files"), record.get("repository_only")
    for label, entries in (("Public files", paths), ("Repository-only records", repository_only)):
        if not isinstance(entries, list) or any(not isinstance(entry, str) for entry in entries):
            raise ValueError(f"{label} must be a list of path strings.")
        if entries != sorted(set(entries)):
            raise ValueError(f"{label} must contain sorted, unique paths.")
    if not paths:
        raise ValueError("Release inventory must contain public files.")
    if set(paths) & set(repository_only):
        raise ValueError("Public files and repository-only records must be disjoint.")
    for relative in paths + repository_only:
        parts = PurePosixPath(relative)
        if not relative or parts.as_posix() != relative or parts.is_absolute() or ".." in parts.parts or "\\" in relative or "\0" in relative:
            raise ValueError("Release path escapes the reviewed source tree.")
        path = root / relative
        if not path.is_file() or path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root.parent):
            raise ValueError(f"Release source must be a regular file: {relative}")
        if root.resolve() not in path.resolve().parents:
            raise ValueError("Release source resolves outside the reviewed tree.")
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    unexpected = sorted(set(filter(None, tracked)) - set(paths) - set(repository_only) - {"LICENSE", "NOTICE"})
    if unexpected:
        raise ValueError("Tracked files require an explicit disclosure review: " + ", ".join(unexpected))
    return paths


def license_issues(root: Path) -> list[str]:
    issues = []
    actual = root / "LICENSE"
    if not actual.is_file() or actual.is_symlink():
        issues.append("No applied root LICENSE.")
    elif hashlib.sha256(actual.read_bytes()).hexdigest() != "074e6e32c86a4c0ef8b3ed25b721ca23aca83df277cd88106ef7177c354615ff":
        issues.append("Root LICENSE differs from the reviewed Apache-2.0 text.")
    metadata = tomllib.loads((root / "pyproject.toml").read_text("utf-8"))["project"]
    if metadata.get("license") != "Apache-2.0":
        issues.append("Package metadata does not declare the applied Apache-2.0 license.")
    if metadata.get("license-files") != ["LICENSE", "NOTICE"]:
        issues.append("Package metadata must include LICENSE and NOTICE in built distributions.")
    notice = root / "NOTICE"
    if not notice.is_file() or notice.is_symlink():
        issues.append("NOTICE with the confirmed copyright licensor is absent.")
    elif not re.search(r"Copyright\s+(?:\(c\)\s+)?20\d{2}\s+\S.{2,}", notice.read_text("utf-8"), re.I):
        issues.append("NOTICE must identify the copyright year and licensor.")
    elif re.search(r"\b(?:TBD|TODO|pending|candidate|placeholder|unconfirmed)\b", notice.read_text("utf-8"), re.I):
        issues.append("NOTICE still contains an unresolved licensor.")
    status = (root / "LICENSE_STATUS.md").read_text("utf-8")
    if "No open-source `LICENSE` has been granted" in status:
        issues.append("LICENSE_STATUS still records an unlicensed development release.")
    return issues


def source_zip(root: Path, paths: list[str], target: Path, version: str) -> dict:
    hashes = {}
    prefix = f"payment-control-lab-{version}/"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in paths:
            data = (root / relative).read_bytes()
            hashes[relative] = hashlib.sha256(data).hexdigest()
            item = zipfile.ZipInfo(prefix + relative, date_time=(1980, 1, 1, 0, 0, 0))
            item.external_attr = 0o100644 << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, data)
    return hashes


def verify_wheel(wheel: Path, source_hashes: dict[str, str], version: str) -> dict[str, str]:
    """Require every runtime byte to match the reviewed source, including RECORD."""
    prefix = f"haltseal_payment_control_lab-{version}.dist-info/"
    metadata_names = {prefix + name for name in ("METADATA", "WHEEL", "entry_points.txt", "top_level.txt", "RECORD")}
    expected = {name: sha for name, sha in source_hashes.items() if name.startswith("payment_control_lab/")}
    checked = {}
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Wheel contains duplicate paths.")
        for item in archive.infolist():
            name = item.filename
            if item.is_dir() or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Wheel must contain regular files only.")
            source_name = name.removeprefix(prefix + "licenses/") if name.startswith(prefix + "licenses/") else name
            if name in metadata_names:
                continue
            if source_name not in source_hashes or (name == source_name and name not in expected):
                raise ValueError(f"Wheel contains an unreviewed file: {name}")
            actual = hashlib.sha256(archive.read(name)).hexdigest()
            if actual != source_hashes[source_name]:
                raise ValueError(f"Wheel differs from reviewed source: {name}")
            checked[name] = actual
        if not set(expected).issubset(checked):
            raise ValueError("Wheel omits a reviewed runtime module or data file.")
        metadata = BytesParser().parsebytes(archive.read(prefix + "METADATA"))
        if metadata["Name"] != "haltseal-payment-control-lab" or metadata["Version"] != version:
            raise ValueError("Wheel metadata differs from the release identity.")
        for name in ("LICENSE", "NOTICE"):
            if name in source_hashes and prefix + "licenses/" + name not in checked:
                raise ValueError("Wheel omits the applied license or attribution.")
        rows = list(csv.reader(io.StringIO(archive.read(prefix + "RECORD").decode("utf-8"))))
        if any(len(row) != 3 for row in rows) or len({row[0] for row in rows}) != len(rows) or {row[0] for row in rows} != set(names):
            raise ValueError("Wheel RECORD must account for each file exactly once.")
        for name, checksum, size in rows:
            if name == prefix + "RECORD":
                if checksum or size:
                    raise ValueError("Wheel RECORD must leave its own checksum and size empty.")
                continue
            data = archive.read(name)
            encoded = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
            if checksum != "sha256=" + encoded or size != str(len(data)):
                raise ValueError(f"Wheel RECORD integrity mismatch: {name}")
    return checked


def build_reviewed_wheel(source: Path, out: Path, version: str, source_hashes: dict[str, str]) -> tuple[Path, dict[str, str]]:
    # Build only from the reviewed ZIP. An untracked module or stale build/
    # in the working checkout must never enter the candidate wheel.
    with tempfile.TemporaryDirectory(prefix="payment-lab-build-") as tmp:
        with zipfile.ZipFile(source) as archive:
            archive.extractall(tmp)
        reviewed = Path(tmp) / f"payment-control-lab-{version}"
        env = {**os.environ, "SOURCE_DATE_EPOCH": "315532800"}
        result = subprocess.run(
            [sys.executable, "-c", "import setuptools.build_meta as b; b.build_wheel(__import__('sys').argv[1])", str(out)],
            cwd=reviewed, env=env, text=True, capture_output=True,
        )
        if result.returncode:
            raise ValueError("Wheel build failed. Inspect the local build environment.")
    wheels = list(out.glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError("Expected exactly one built wheel.")
    return wheels[0], verify_wheel(wheels[0], source_hashes, version)


def smoke_install(wheel: Path, bundle: Path, version: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="payment-lab-install-") as tmp:
        home = Path(tmp)
        venv = home / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)], cwd=home, check=True, stdout=subprocess.DEVNULL)
        console = venv / ("Scripts/payment-control-lab.exe" if os.name == "nt" else "bin/payment-control-lab")
        printed = subprocess.check_output([str(console), "--version"], cwd=home, text=True)
        if version not in printed:
            raise ValueError("Installed console entrypoint differs from the release version.")
        subprocess.run([str(python), "-I", "-m", "payment_control_lab", "demo", "--out", str(home / "demo")], cwd=home, check=True, stdout=subprocess.DEVNULL)
        report = json.loads((home / "demo/report.json").read_text("utf-8"))
        if report["tool_version"] != version or report["summary"]["diagnoses_reproduced"] != 16:
            raise ValueError("Installed resources did not reproduce all 16 trace diagnoses.")
        with zipfile.ZipFile(bundle) as archive:
            archive.extractall(home / "source")
        source = home / "source" / f"payment-control-lab-{version}"
        for code, before, after in ((0, "route_retry_policy", "fixture_policy"), (2, "fixture_policy", "route_retry_policy")):
            result = subprocess.run([str(python), "-I", "-m", "payment_control_lab", "compare-policy", f"examples.{before}:decide", f"examples.{after}:decide", "--out", str(home / f"compare-{code}")], cwd=source, stdout=subprocess.DEVNULL)
            if result.returncode != code:
                raise ValueError("Installed comparison returned an unexpected diagnostic exit.")
            comparison = json.loads((home / f"compare-{code}/report.json").read_text("utf-8"))
            if comparison["comparison"]["case_count"] != 16 or comparison["comparison"]["uncertain_count"]:
                raise ValueError("Installed comparison is incomplete.")
            if code == 0 and (comparison["summary"]["verdict"] != "EXPECTATIONS_MET" or comparison["comparison"]["regressed_count"]):
                raise ValueError("Installed repaired candidate did not meet the absolute contract.")
            if code == 2 and not comparison["comparison"]["regressed_count"]:
                raise ValueError("Installed comparison did not preserve the deliberate regression.")
        for output in (home / "demo", home / "compare-0", home / "compare-2"):
            if not all((output / name).is_file() for name in ("report.html", "report.json", "owner-summary.html")):
                raise ValueError("Installed workflow omitted a report bundle file.")
        checks = subprocess.run([str(python), "-I", "-m", "unittest", "discover"], cwd=source, text=True, capture_output=True)
        count = re.search(r"Ran ([1-9][0-9]*) tests", checks.stderr)
        if checks.returncode or not count:
            raise ValueError("Reviewed source ZIP did not reproduce its diagnostic regression tests.")
    return {"fresh_venv": "PASS", "installed_demo": "16/16", "installed_comparison": "0 and 2", "source_zip_regressions": f"{count.group(1)} passed", "report_bundle": "3 files per result", "external_human_reproduction": "not performed"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "out/release-candidate")
    parser.add_argument("--require-public-license", action="store_true")
    args = parser.parse_args()
    try:
        paths = reviewed_paths(ROOT)
        issues = license_issues(ROOT)
        if args.require_public_license and issues:
            print("Public distribution blocked:\n" + "\n".join(issues), file=sys.stderr)
            return 2
        if args.require_public_license and subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
            raise ValueError("Freeze a clean licensed commit before building a public distribution.")
        out = args.out.resolve()
        if ROOT.resolve() == out or ROOT.resolve() in out.parents and not (ROOT / "out").resolve() in (out, *out.parents):
            raise ValueError("Use an output directory under out/ or outside the source tree.")
        out.mkdir(parents=True, exist_ok=True)
        if any(out.iterdir()):
            raise ValueError("Release output must be empty; use a fresh directory.")
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]
        version = metadata["version"]
        if not re.fullmatch(r"[0-9A-Za-z.]+", version):
            raise ValueError("Version cannot be used as a release filename.")
        if not issues:
            paths = sorted(set(paths) | {"LICENSE", "NOTICE"})
        source = out / f"payment-control-lab-{version}-source.zip"
        hashes = source_zip(ROOT, paths, source, version)
        wheel, wheel_hashes = build_reviewed_wheel(source, out, version, hashes)
        smoke = smoke_install(wheel, source, version)
        smoke["wheel_source_match"] = f"{len(wheel_hashes)} reviewed files; every runtime byte matched"
        source_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, text=True).strip())
        artifacts = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (source, wheel)}
        manifest = {"schema": "payment-control-lab.release-candidate.v1", "version": version, "source_commit": source_sha, "tracked_source_dirty": dirty, "distribution": "private candidate" if issues else "licensed candidate; publication remains a separate action", "publication_blockers": issues, "artifacts": artifacts, "source_files": hashes, "wheel_files": wheel_hashes, "verification": smoke, "payment_authority": False}
        (out / "release-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", "utf-8")
        checksums = "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in sorted(out.iterdir()) if path.is_file())
        (out / "SHA256SUMS").write_text(checksums, "utf-8")
        print(json.dumps({"out": str(out), "verification": smoke, "publication_blockers": issues}, indent=2))
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError, zipfile.BadZipFile, UnicodeError) as exc:
        print(f"Release preparation error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
