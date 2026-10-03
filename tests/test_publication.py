# Copyright 2026 Yong Bok Lee
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import verify_release as verifier


class PublicationTests(unittest.TestCase):
    def fixture(self, root):
        source = {"pyproject.toml": b'[project]\nname="haltseal-payment-control-lab"\nversion="0.2.0"\ndependencies=[]\nrequires-python=">=3.11"\nreadme="README.md"\n',
                  "README.md": b"Synthetic release.\n", "payment_control_lab/__init__.py": b'__version__="0.2.0"\n'}
        prefix = "haltseal_payment_control_lab-0.2.0.dist-info/"
        wheel = {"payment_control_lab/__init__.py": source["payment_control_lab/__init__.py"],
                 prefix + "METADATA": b"Metadata-Version: 2.4\nName: haltseal-payment-control-lab\nVersion: 0.2.0\nRequires-Python: >=3.11\n\nSynthetic release.\n",
                 prefix + "WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
                 prefix + "entry_points.txt": b"[console_scripts]\npayment-control-lab = payment_control_lab.cli:main\n"}
        rows = []
        for name, data in wheel.items():
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            rows.append([name, "sha256=" + digest, str(len(data))])
        rows.append([prefix + "RECORD", "", ""])
        stream = io.StringIO(); csv.writer(stream, lineterminator="\n").writerows(rows)
        wheel[prefix + "RECORD"] = stream.getvalue().encode()
        wheel_path = root / "haltseal_payment_control_lab-0.2.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel_path, "w") as archive:
            for name, data in wheel.items(): archive.writestr(name, data)
        source_path = root / "payment-control-lab-0.2.0-source.zip"
        with zipfile.ZipFile(source_path, "w") as archive:
            for name, data in source.items(): archive.writestr("payment-control-lab-0.2.0/" + name, data)
        manifest = {"schema": "payment-control-lab.release-candidate.v1", "version": "0.2.0", "source_commit": "1" * 40,
                    "payment_authority": False, "source_files": {k: verifier.sha256(v) for k, v in source.items()},
                    "artifacts": {p.name: verifier.sha256(p.read_bytes()) for p in (source_path, wheel_path)},
                    "wheel_files": {"payment_control_lab/__init__.py": verifier.sha256(source["payment_control_lab/__init__.py"])}}
        (root / "release-manifest.json").write_text(json.dumps(manifest))
        self.sums(root)
        return manifest

    def sums(self, root):
        (root / "SHA256SUMS").write_text("".join(f"{verifier.sha256(p.read_bytes())}  {p.name}\n" for p in sorted(root.iterdir()) if p.name != "SHA256SUMS"))

    def rebind_fixture(self, root):
        path = root / "release-manifest.json"
        manifest = json.loads(path.read_text())
        manifest["artifacts"] = {p.name: verifier.sha256(p.read_bytes()) for p in root.iterdir() if p.suffix in {".whl", ".zip"}}
        path.write_text(json.dumps(manifest))
        self.sums(root)

    def test_independent_verifier_accepts_exact_asset_set_and_trusted_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            result = verifier.verify_bundle(root, verifier.sha256((root / "release-manifest.json").read_bytes()))
            self.assertEqual(result["checksums"], "PASS")
            self.assertEqual(result["independent_digest"], "matched")
            self.assertEqual(result["artifact_manifest_binding"], "PASS")
            self.assertFalse(result["payment_authority"])

    def test_trusted_manifest_rejects_replaced_asset_despite_recomputed_side_checksums(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            digest = verifier.sha256((root / "release-manifest.json").read_bytes())
            wheel = next(root.glob("*.whl"))
            wheel.write_bytes(wheel.read_bytes() + b"replacement")
            self.sums(root)
            with self.assertRaisesRegex(ValueError, "differs from the trusted manifest"):
                verifier.verify_bundle(root, digest)

    def test_manifest_must_bind_both_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); manifest = self.fixture(root)
            manifest["artifacts"].pop(next(iter(manifest["artifacts"])))
            (root / "release-manifest.json").write_text(json.dumps(manifest)); self.sums(root)
            with self.assertRaisesRegex(ValueError, "bind the exact source ZIP and wheel"):
                verifier.verify_bundle(root)

    def test_independent_digest_rejects_rewritten_manifest_even_with_recomputed_checksums(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); manifest = self.fixture(root)
            digest = verifier.sha256((root / "release-manifest.json").read_bytes())
            manifest["source_commit"] = "2" * 40
            (root / "release-manifest.json").write_text(json.dumps(manifest)); self.sums(root)
            with self.assertRaisesRegex(ValueError, "independently supplied"):
                verifier.verify_bundle(root, digest)

    def test_verifier_rejects_changed_asset_and_unlisted_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            wheel = next(root.glob("*.whl")); original = wheel.read_bytes()
            wheel.write_bytes(original + b"changed")
            with self.assertRaisesRegex(ValueError, "checksum"):
                verifier.verify_bundle(root)
            wheel.write_bytes(original); (root / "unreviewed.txt").write_text("unexpected")
            with self.assertRaisesRegex(ValueError, "exactly the four"):
                verifier.verify_bundle(root)

    def test_recomputed_checksums_do_not_hide_extra_source_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            with zipfile.ZipFile(root / "payment-control-lab-0.2.0-source.zip", "a") as archive:
                archive.writestr("payment-control-lab-0.2.0/private-review.md", "private")
            self.rebind_fixture(root)
            with self.assertRaisesRegex(ValueError, "exactly match"):
                verifier.verify_bundle(root)

    def test_source_archive_never_accepts_traversal_or_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            path = root / "payment-control-lab-0.2.0-source.zip"
            with zipfile.ZipFile(path, "a") as archive:
                archive.writestr("../outside.txt", "unsafe")
            self.rebind_fixture(root)
            with self.assertRaisesRegex(ValueError, "unsafe"):
                verifier.verify_bundle(root)
            path.unlink()
            with zipfile.ZipFile(path, "w") as archive:
                entry = zipfile.ZipInfo("linked.txt"); entry.external_attr = 0o120777 << 16
                archive.writestr(entry, "/outside")
            with self.assertRaisesRegex(ValueError, "non-regular"):
                verifier.archive_files(path)

    def test_checksums_and_json_duplicate_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            path = root / "SHA256SUMS"; path.write_text(path.read_text() * 2)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                verifier.verify_bundle(root)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            verifier.read_json(b'{"version":"0.2.0","version":"0.3.0"}')

    def test_a_metadata_only_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            wheel_path = next(root.glob("*.whl"))
            with zipfile.ZipFile(wheel_path) as archive:
                payload = {name: archive.read(name) for name in archive.namelist()}
            prefix = "haltseal_payment_control_lab-0.2.0.dist-info/"
            payload[prefix + "METADATA"] = payload[prefix + "METADATA"].replace(b"Requires-Python:", b"Requires-Dist: unreviewed-package\nRequires-Python:")
            rows=[]
            for name,data in payload.items():
                if name.endswith("/RECORD"):continue
                rows.append([name,"sha256="+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode(),str(len(data))])
            rows.append([prefix+"RECORD","",""]); stream=io.StringIO();csv.writer(stream,lineterminator="\n").writerows(rows)
            payload[prefix+"RECORD"]=stream.getvalue().encode()
            with zipfile.ZipFile(wheel_path,"w") as archive:
                for name,data in payload.items():archive.writestr(name,data)
            self.rebind_fixture(root)
            with self.assertRaisesRegex(ValueError,"dependency"):
                verifier.verify_bundle(root)

if __name__ == "__main__":
    unittest.main()
