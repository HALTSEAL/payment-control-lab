# Copyright 2026 Yong Bok Lee
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location("build_release", Path(__file__).resolve().parents[1] / "tools/build_release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseBundleTests(unittest.TestCase):
    def inventory(self, root, files, repository_only=()):
        path = root / release.INVENTORY
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schema": "payment-control-lab.public-inventory.v2", "files": files, "repository_only": list(repository_only)}))

    def wheel_fixture(self, root, *, extra=False, changed=False, missing=False, bad_record=False):
        prefix = "haltseal_payment_control_lab-0.2.0.dist-info/"
        source = {"payment_control_lab/__init__.py": b'__version__ = "0.2.0"\n', "payment_control_lab/data/scenarios.json": b'[]\n'}
        payload = {**source, prefix + "METADATA": b"Metadata-Version: 2.4\nName: haltseal-payment-control-lab\nVersion: 0.2.0\n", prefix + "WHEEL": b"Wheel-Version: 1.0\n"}
        if changed:
            payload["payment_control_lab/__init__.py"] = b"# Altered runtime\n"
        if extra:
            payload["payment_control_lab/unreviewed.py"] = b"# Not approved\n"
        if missing:
            del payload["payment_control_lab/data/scenarios.json"]
        records = []
        for name, data in payload.items():
            encoded = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            records.append(f"{name},sha256={encoded},{len(data)}\n")
        records.append(prefix + "RECORD,,\n")
        if bad_record:
            records[0] = "payment_control_lab/__init__.py,sha256=wrong,1\n"
        payload[prefix + "RECORD"] = "".join(records).encode()
        wheel = root / "fixture.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            for name, data in payload.items():
                archive.writestr(name, data)
        return wheel, {name: hashlib.sha256(data).hexdigest() for name, data in source.items()}

    def test_wheel_must_match_every_reviewed_runtime_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            wheel, hashes = self.wheel_fixture(Path(tmp))
            self.assertEqual(release.verify_wheel(wheel, hashes, "0.2.0"), hashes)

    def test_wheel_rejects_unreviewed_runtime_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            wheel, hashes = self.wheel_fixture(Path(tmp), extra=True)
            with self.assertRaisesRegex(ValueError, "unreviewed"):
                release.verify_wheel(wheel, hashes, "0.2.0")

    def test_wheel_rejects_altered_source_and_missing_resource(self):
        with tempfile.TemporaryDirectory() as tmp:
            for options, message in (({"changed": True}, "differs"), ({"missing": True}, "omits")):
                with self.subTest(options=options):
                    wheel, hashes = self.wheel_fixture(Path(tmp), **options)
                    with self.assertRaisesRegex(ValueError, message):
                        release.verify_wheel(wheel, hashes, "0.2.0")

    def test_wheel_rejects_corrupt_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            wheel, hashes = self.wheel_fixture(Path(tmp), bad_record=True)
            with self.assertRaisesRegex(ValueError, "RECORD integrity"):
                release.verify_wheel(wheel, hashes, "0.2.0")

    def test_wheel_rejects_duplicate_archive_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            wheel, hashes = self.wheel_fixture(Path(tmp))
            with zipfile.ZipFile(wheel, "a") as archive:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    archive.writestr("payment_control_lab/__init__.py", b"duplicate")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                release.verify_wheel(wheel, hashes, "0.2.0")

    def test_unlicensed_candidate_cannot_be_treated_as_public_distribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "release/candidates").mkdir(parents=True)
            (root / "release/candidates/Apache-2.0.txt").write_text("Candidate only")
            (root / "pyproject.toml").write_text('[project]\nname = "test"\n')
            (root / "LICENSE_STATUS.md").write_text("No open-source `LICENSE` has been granted")
            issues = release.license_issues(root)
            self.assertTrue(any("No applied root LICENSE" in issue for issue in issues))
            self.assertTrue(any("Package metadata" in issue for issue in issues))

    def test_consistent_licensed_fixture_requires_attribution_in_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "release/candidates").mkdir(parents=True)
            (root / "release/candidates/Apache-2.0.txt").write_bytes((release.ROOT / "LICENSE").read_bytes())
            (root / "LICENSE").write_bytes((release.ROOT / "LICENSE").read_bytes())
            (root / "NOTICE").write_text("Copyright 2026 Example Rights Holder\n")
            (root / "LICENSE_STATUS.md").write_text("Applied license in this test fixture")
            metadata = '[project]\nlicense = "Apache-2.0"\n'
            (root / "pyproject.toml").write_text(metadata)
            self.assertTrue(any("built distributions" in issue for issue in release.license_issues(root)))
            (root / "pyproject.toml").write_text(metadata + 'license-files = ["LICENSE", "NOTICE"]\n')
            self.assertEqual(release.license_issues(root), [])
            (root / "NOTICE").write_text("\n")
            self.assertTrue(any("copyright year" in issue for issue in release.license_issues(root)))

    def test_unreviewed_tracked_file_is_rejected(self):
        with patch.object(release.subprocess, "check_output", return_value=b"README.md\0private/kernel.py\0"):
            with self.assertRaisesRegex(ValueError, "private/kernel.py"):
                release.reviewed_paths(release.ROOT)

    def test_inventory_rejects_traversal_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "release").mkdir()
            inventory = root / release.INVENTORY
            self.inventory(root, ["../record.json"])
            with self.assertRaisesRegex(ValueError, "escapes"):
                release.reviewed_paths(root)
            (root / "target.txt").write_text("synthetic")
            try:
                (root / "linked.txt").symlink_to(root / "target.txt")
            except (OSError, NotImplementedError):
                self.skipTest("Symbolic links are unavailable in this environment")
            self.inventory(root, ["linked.txt"])
            with self.assertRaisesRegex(ValueError, "regular file"):
                release.reviewed_paths(root)

    def test_source_zip_is_reproducible_and_excludes_unlisted_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("Reviewed diagnostic source")
            (root / "customer-history.json").write_text("DO NOT DISTRIBUTE")
            first, second = root / "first.zip", root / "second.zip"
            release.source_zip(root, ["README.md"], first, "0.2.0")
            release.source_zip(root, ["README.md"], second, "0.2.0")
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(archive.namelist(), ["payment-control-lab-0.2.0/README.md"])

    def test_diagnostic_zip_excludes_private_review_and_release_records(self):
        record = json.loads((release.ROOT / release.INVENTORY).read_text())
        paths = release.reviewed_paths(release.ROOT)
        excluded = {".github/workflows/quality.yml", ".github/workflows/release-candidate.yml", "tools/build_release.py", "tools/check_report_layout.cjs", "tests/test_release_bundle.py", "release/public-files.json"}
        self.assertTrue(excluded.issubset(record["repository_only"]))
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "diagnostics.zip"
            release.source_zip(release.ROOT, paths, target, "0.2.0")
            with zipfile.ZipFile(target) as archive:
                bundled = {name.removeprefix("payment-control-lab-0.2.0/") for name in archive.namelist()}
                self.assertEqual(bundled, set(paths))
                self.assertFalse(bundled.intersection(record["repository_only"]))
                self.assertIn("payment_control_lab/review.py", bundled)
                self.assertIn("tests/test_review.py", bundled)

    def test_repository_only_file_is_accounted_for_without_being_bundled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("Public usage")
            (root / "review.json").write_text("PRIVATE REVIEW")
            self.inventory(root, ["README.md"], ["review.json"])
            with patch.object(release.subprocess, "check_output", return_value=b"README.md\0review.json\0"):
                self.assertEqual(release.reviewed_paths(root), ["README.md"])
            (root / "unreviewed.txt").write_text("Not reviewed")
            with patch.object(release.subprocess, "check_output", return_value=b"README.md\0review.json\0unreviewed.txt\0"):
                with self.assertRaisesRegex(ValueError, "unreviewed.txt"):
                    release.reviewed_paths(root)

    def test_private_record_cannot_also_be_a_public_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.inventory(root, ["review.json"], ["review.json"])
            with self.assertRaisesRegex(ValueError, "disjoint"):
                release.reviewed_paths(root)

    def test_inventory_requires_explicit_public_and_private_path_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.inventory(root, ["README.md"])
            inventory = root / release.INVENTORY
            for invalid in ({"files": ["README.md"]}, {"schema": "payment-control-lab.public-inventory.v2", "files": ["README.md"]}, [], {"schema": "payment-control-lab.public-inventory.v2", "files": ["README.md"], "repository_only": [1]}):
                with self.subTest(record=invalid):
                    inventory.write_text(json.dumps(invalid))
                    with self.assertRaises(ValueError):
                        release.reviewed_paths(root)

    def test_inventory_rejects_noncanonical_or_unsafe_repository_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("Public usage")
            for relative in ("../review.json", "./README.md", "docs//review.json", "", "review\0.json", "C:\\review.json"):
                with self.subTest(path=relative):
                    self.inventory(root, ["README.md"], [relative])
                    with self.assertRaisesRegex(ValueError, "escapes"):
                        release.reviewed_paths(root)
            self.inventory(root, ["README.md"], ["missing-review.json"])
            with self.assertRaisesRegex(ValueError, "regular file"):
                release.reviewed_paths(root)

    def test_inventory_lists_cannot_be_empty_duplicated_or_unsorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for files, private in (([], []), (["README.md", "README.md"], []), (["README.md"], ["z.md", "a.md"]), (["README.md"], ["a.md", "a.md"])):
                with self.subTest(files=files, private=private):
                    self.inventory(root, files, private)
                    with self.assertRaises(ValueError):
                        release.reviewed_paths(root)


if __name__ == "__main__":
    unittest.main()
