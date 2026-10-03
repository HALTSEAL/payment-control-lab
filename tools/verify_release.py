#!/usr/bin/env python3
# Copyright 2026 Yong Bok Lee
# SPDX-License-Identifier: Apache-2.0
"""Verify downloaded candidate bytes. Checksums establish integrity, not ownership."""
from __future__ import annotations

import argparse
import configparser
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tomllib
import zipfile

from build_release import smoke_install, verify_wheel

MAX_BYTES = 50 * 1024 * 1024
MAX_FILES = 5000


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_path(name: str) -> bool:
    p = PurePosixPath(name)
    return bool(name) and p.as_posix() == name and not p.is_absolute() and not any(
        part in {"..", "."} or ":" in part for part in p.parts
    ) and "\\" not in name and not any(ord(c) < 32 for c in name)


def read_json(data: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Release JSON contains duplicate keys.")
            result[key] = value
        return result
    value = json.loads(data, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("Release manifest must be an object.")
    return value


def archive_files(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(names) > MAX_FILES or len(names) != len(set(names)) or len(names) != len({n.casefold() for n in names}):
            raise ValueError("Archive contains too many files or duplicate/colliding paths.")
        if sum(entry.file_size for entry in entries) > MAX_BYTES:
            raise ValueError("Archive exceeds the diagnostic release size limit.")
        for entry in entries:
            kind = stat.S_IFMT(entry.external_attr >> 16)
            if not safe_path(entry.filename) or entry.is_dir() or kind not in (0, stat.S_IFREG) or entry.flag_bits & 1:
                raise ValueError("Archive contains an unsafe or non-regular entry.")
        return {name: archive.read(name) for name in names}


def hash_inventory(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise ValueError("Release hash inventory must be a nonempty object.")
    for name, digest in value.items():
        if not isinstance(name, str) or not safe_path(name) or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Release hash inventory contains an unsafe path or invalid digest.")
    if len(value) != len({name.casefold() for name in value}):
        raise ValueError("Release inventory contains case-colliding paths.")
    return value


def verify_bundle(directory: Path, expected_manifest_sha256: str | None = None, install: bool = False) -> dict:
    directory = directory.resolve()
    manifest_path = directory / "release-manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink() or manifest_path.stat().st_size > MAX_BYTES:
        raise ValueError("Release manifest must be a bounded regular file.")
    raw = manifest_path.read_bytes()
    if expected_manifest_sha256 is not None:
        if not re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha256) or sha256(raw) != expected_manifest_sha256:
            raise ValueError("Release manifest differs from the independently supplied digest.")
    manifest = read_json(raw)
    if manifest.get("schema") != "payment-control-lab.release-candidate.v1" or manifest.get("payment_authority") is not False:
        raise ValueError("Unexpected release schema or payment-authority claim.")
    version = manifest.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){2}", version):
        raise ValueError("Unexpected release version.")
    if not re.fullmatch(r"[0-9a-f]{40}", str(manifest.get("source_commit", ""))):
        raise ValueError("Release source commit is absent or invalid.")
    source_name = f"payment-control-lab-{version}-source.zip"
    wheel_name = f"haltseal_payment_control_lab-{version}-py3-none-any.whl"
    expected = {"release-manifest.json", source_name, wheel_name, "SHA256SUMS"}
    if {p.name for p in directory.iterdir()} != expected:
        raise ValueError("Release directory must contain exactly the four declared assets.")
    for name in expected:
        path = directory / name
        if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_BYTES:
            raise ValueError("Release assets must be bounded regular files.")
    sums = {}
    for line in (directory / "SHA256SUMS").read_text("utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        if not match or match[2] in sums:
            raise ValueError("SHA256SUMS contains malformed or duplicate entries.")
        sums[match[2]] = match[1]
    if set(sums) != expected - {"SHA256SUMS"}:
        raise ValueError("SHA256SUMS must account for each release asset exactly once.")
    for name, digest in sums.items():
        if sha256((directory / name).read_bytes()) != digest:
            raise ValueError("Release asset checksum mismatch: " + name)
    artifacts = hash_inventory(manifest.get("artifacts"))
    if set(artifacts) != {source_name, wheel_name}:
        raise ValueError("Trusted manifest must bind the exact source ZIP and wheel.")
    for name, digest in artifacts.items():
        if sha256((directory / name).read_bytes()) != digest:
            raise ValueError("Release asset differs from the trusted manifest: " + name)
    source_hashes = hash_inventory(manifest.get("source_files"))
    wheel_hashes = hash_inventory(manifest.get("wheel_files"))
    prefix = f"payment-control-lab-{version}/"
    zipped = archive_files(directory / source_name)
    if set(zipped) != {prefix + name for name in source_hashes}:
        raise ValueError("Source ZIP does not exactly match the reviewed inventory.")
    for name, digest in source_hashes.items():
        if sha256(zipped[prefix + name]) != digest:
            raise ValueError("Source ZIP content differs from its inventory: " + name)
    project = tomllib.loads(zipped[prefix + "pyproject.toml"].decode("utf-8"))["project"]
    if project.get("name") != "haltseal-payment-control-lab" or project.get("version") != version or project.get("dependencies") != []:
        raise ValueError("Source package identity or zero-dependency contract differs.")
    wheel_bytes = archive_files(directory / wheel_name)
    verified = verify_wheel(directory / wheel_name, source_hashes, version)
    if verified != wheel_hashes:
        raise ValueError("Wheel content differs from the release manifest.")
    info = f"haltseal_payment_control_lab-{version}.dist-info/"
    metadata_raw = wheel_bytes[info + "METADATA"]
    metadata = BytesParser().parsebytes(metadata_raw)
    for field in ("Name", "Version", "Requires-Python", "License-Expression"):
        if len(metadata.get_all(field, [])) > 1:
            raise ValueError("Wheel contains duplicate identity or licensing metadata.")
    if metadata.get_all("Requires-Dist", []) or metadata.get("Requires-Python") != project.get("requires-python"):
        raise ValueError("Wheel dependency or Python support metadata differs from the reviewed project.")
    if metadata.get("License-Expression") != project.get("license"):
        raise ValueError("Wheel license metadata differs from the reviewed project.")
    description = re.split(br"\r?\n\r?\n", metadata_raw, maxsplit=1)
    if project.get("readme") != "README.md" or len(description) != 2 or description[1].rstrip(b"\n") != zipped[prefix + "README.md"].rstrip(b"\n"):
        raise ValueError("Wheel description differs from the reviewed README.")
    wheel_metadata = BytesParser().parsebytes(wheel_bytes[info + "WHEEL"])
    if wheel_metadata.get("Root-Is-Purelib") != "true" or wheel_metadata.get_all("Tag", []) != ["py3-none-any"]:
        raise ValueError("Wheel no longer declares the reviewed pure-Python distribution.")
    entrypoints = configparser.ConfigParser(interpolation=None)
    entrypoints.read_string(wheel_bytes[info + "entry_points.txt"].decode("utf-8"))
    if list(entrypoints.sections()) != ["console_scripts"] or dict(entrypoints["console_scripts"]) != {"payment-control-lab": "payment_control_lab.cli:main"}:
        raise ValueError("Wheel console entrypoint differs from the reviewed CLI.")
    checks = {
        "checksums": "PASS", "artifact_manifest_binding": "PASS", "source_inventory": f"{len(source_hashes)} files matched",
        "wheel_source_and_record": f"{len(verified)} files matched",
        "independent_digest": "matched" if expected_manifest_sha256 else "not supplied; compare with the trusted release record",
        "licensing_authority": "not established by byte verification",
        "publication": "not established by local verification", "payment_authority": False,
    }
    if install:
        checks["fresh_install"] = smoke_install(directory / wheel_name, directory / source_name, version)
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--expected-manifest-sha256")
    parser.add_argument("--install", action="store_true", help="Run code only from a trusted release in a fresh virtual environment")
    args = parser.parse_args()
    try:
        print(json.dumps(verify_bundle(args.directory, args.expected_manifest_sha256, args.install), indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile, subprocess.CalledProcessError, configparser.Error) as exc:
        print(f"Release verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
