from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from evidence_store import EvidenceStore, EvidenceStoreError


IDENTITY = {
    "worker_id": "worker-us-east",
    "instance_id": "instance-1",
    "generation": 3,
}


def evidence_zip(label: str = "pass") -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"status": label}) + "\n")
    return output.getvalue()


class EvidenceStoreTests(unittest.TestCase):
    def test_put_is_lease_bound_and_response_loss_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EvidenceStore(Path(directory) / "evidence")
            payload = evidence_zip()
            first = store.put(
                job_id="job-1",
                lease_id="lease-1",
                identity=IDENTITY,
                data=payload,
            )
            replay = store.put(
                job_id="job-1",
                lease_id="lease-1",
                identity=IDENTITY,
                data=payload,
            )
            self.assertFalse(first["idempotent_replay"])
            self.assertTrue(replay["idempotent_replay"])
            self.assertEqual(
                first["evidence_id"],
                replay["evidence_id"],
            )
            self.assertEqual(
                first["content_sha256"],
                hashlib.sha256(payload).hexdigest(),
            )
            self.assertEqual(store.get(first["evidence_id"])["job_id"], "job-1")
            content, record = store.content(first["evidence_id"])
            self.assertEqual(content, payload)
            self.assertEqual(record["lease_id"], "lease-1")
            record_path = (
                Path(directory)
                / "evidence"
                / "records"
                / f"{first['evidence_id']}.json"
            )
            self.assertEqual(record_path.stat().st_mode & 0o777, 0o600)

            with self.assertRaisesRegex(EvidenceStoreError, "different evidence"):
                store.put(
                    job_id="job-1",
                    lease_id="lease-1",
                    identity=IDENTITY,
                    data=evidence_zip("fail"),
                )

    def test_result_requires_exact_job_lease_worker_and_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EvidenceStore(Path(directory) / "evidence")
            payload = evidence_zip()
            record = store.put(
                job_id="job-1",
                lease_id="lease-1",
                identity=IDENTITY,
                data=payload,
            )
            found = store.require_for_result(
                job_id="job-1",
                lease_id="lease-1",
                identity=IDENTITY,
                evidence_sha256=record["content_sha256"],
            )
            self.assertEqual(found["evidence_id"], record["evidence_id"])
            for overrides in (
                {"job_id": "job-2"},
                {"lease_id": "lease-2"},
                {
                    "identity": {
                        **IDENTITY,
                        "generation": IDENTITY["generation"] + 1,
                    }
                },
                {"evidence_sha256": "0" * 64},
            ):
                request = {
                    "job_id": "job-1",
                    "lease_id": "lease-1",
                    "identity": IDENTITY,
                    "evidence_sha256": record["content_sha256"],
                    **overrides,
                }
                with self.subTest(overrides=overrides):
                    with self.assertRaises(EvidenceStoreError):
                        store.require_for_result(**request)

    def test_rejects_non_zip_oversize_and_capacity(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EvidenceStore(
                Path(directory) / "evidence",
                max_records=1,
                max_bytes=len(evidence_zip()) + 8,
            )
            with self.assertRaisesRegex(EvidenceStoreError, "ZIP archive"):
                store.put(
                    job_id="job-1",
                    lease_id="lease-1",
                    identity=IDENTITY,
                    data=b"not-a-zip",
                )
            first = store.put(
                job_id="job-1",
                lease_id="lease-1",
                identity=IDENTITY,
                data=evidence_zip(),
            )
            self.assertEqual(store.stats()["entries"], 1)
            with self.assertRaisesRegex(EvidenceStoreError, "capacity is exhausted"):
                store.put(
                    job_id="job-2",
                    lease_id="lease-2",
                    identity=IDENTITY,
                    data=evidence_zip("second"),
                )
            store.delete(first["evidence_id"])
            self.assertEqual(store.stats()["entries"], 0)

    def test_prune_removes_expired_records_and_orphan_blobs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "evidence"
            store = EvidenceStore(root, retention_seconds=10, clock=lambda: 100)
            record = store.put(
                job_id="job-1",
                lease_id="lease-1",
                identity=IDENTITY,
                data=evidence_zip(),
            )
            orphan = root / "blobs" / f"{'1' * 64}.zip"
            orphan.write_bytes(b"orphan")
            result = store.prune(now=111)
            self.assertEqual(result["records_removed"], 1)
            self.assertEqual(result["blobs_removed"], 2)
            self.assertEqual(store.stats()["entries"], 0)
            with self.assertRaises(EvidenceStoreError):
                store.get(record["evidence_id"])


if __name__ == "__main__":
    unittest.main()
