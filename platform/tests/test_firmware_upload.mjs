import assert from 'node:assert/strict';
import {
  FirmwareUploadClient,
  readUploadCheckpoint,
  writeUploadCheckpoint,
} from '../web/firmware-upload.js';
import { sha256Bytes } from '../web/sha256.js';

function jsonResponse(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ 'Content-Type': 'application/json' }),
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  };
}

const payload = new TextEncoder().encode('web-burner-package');
const payloadSha = sha256Bytes(payload);
const calls = [];
let chunkAttempts = 0;
const fetchImpl = async (path, options = {}) => {
  calls.push({ path, options });
  if (path === '/api/v1/artifact-uploads') {
    const body = JSON.parse(options.body);
    assert.equal(body.expected_size, payload.length);
    assert.equal(body.expected_sha256, payloadSha);
    return jsonResponse({
      upload_id: 'a'.repeat(32),
      status: 'uploading',
      expected_size: payload.length,
      expected_sha256: payloadSha,
      received_bytes: 0,
      chunks: 0,
      name: body.name,
      content_type: body.content_type,
      artifact_id: null,
    }, 202);
  }
  if (path.endsWith('/chunks')) {
    chunkAttempts += 1;
    if (chunkAttempts === 1) throw new Error('transient network failure');
    assert.equal(options.headers.get('X-Chunk-Offset'), '0');
    assert.equal(options.headers.get('X-Chunk-SHA256'), payloadSha);
    return jsonResponse({
      upload_id: 'a'.repeat(32),
      status: 'uploading',
      expected_size: payload.length,
      expected_sha256: payloadSha,
      received_bytes: payload.length,
      chunks: 1,
      name: 'web-probe.zip',
      content_type: 'application/zip',
      artifact_id: null,
      next_offset: payload.length,
    }, 202);
  }
  if (path.endsWith('/complete')) {
    return jsonResponse({
      artifact_id: payloadSha,
      sha256: payloadSha,
      size: payload.length,
      name: 'web-probe.zip',
      content_type: 'application/zip',
      created_at: '2026-10-24T00:00:00+00:00',
    }, 201);
  }
  if (path === '/api/v1/firmware/import') {
    return jsonResponse({
      firmware_id: 'b'.repeat(64),
      sha256: 'b'.repeat(64),
      kind: 'manifest',
      device_id: 'sticks3',
    }, 201);
  }
  throw new Error(`unexpected request ${path}`);
};

const progress = [];
const client = new FirmwareUploadClient({
  fetchImpl,
  chunkBytes: 1024,
  sleep: async () => {},
});
const uploadFile = new Blob([payload], { type: 'application/zip' });
Object.defineProperty(uploadFile, 'name', { value: 'web-probe.zip' });
const result = await client.upload({
  file: uploadFile,
  deviceId: 'sticks3',
  onProgress: event => progress.push(event.phase),
});
assert.equal(result.artifact.artifact_id, payloadSha);
assert.equal(chunkAttempts, 2);
assert.deepEqual(progress, [
  'hashing',
  'hashing',
  'hashing',
  'uploading',
  'uploading',
  'uploaded',
]);
const firmware = await client.importPackage({
  deviceId: 'sticks3',
  artifactId: payloadSha,
});
assert.equal(firmware.kind, 'manifest');

const resumedPayload = new TextEncoder().encode('resume-prefix');
const resumedSha = sha256Bytes(resumedPayload);
const resumedOffsets = [];
const resumedClient = new FirmwareUploadClient({
  chunkBytes: 1024,
  fetchImpl: async (path, options = {}) => {
    if (path.includes('/artifact-uploads/') && !path.endsWith('/chunks') && !path.endsWith('/complete')) {
      return jsonResponse({
        upload_id: 'c'.repeat(32),
        status: 'uploading',
        expected_size: resumedPayload.length,
        expected_sha256: resumedSha,
        received_bytes: 7,
        chunks: 1,
        name: 'resume.zip',
        content_type: 'application/zip',
        artifact_id: null,
      });
    }
    if (path.endsWith('/chunks')) {
      resumedOffsets.push(Number(options.headers.get('X-Chunk-Offset')));
      return jsonResponse({
        upload_id: 'c'.repeat(32),
        status: 'uploading',
        expected_size: resumedPayload.length,
        expected_sha256: resumedSha,
        received_bytes: resumedPayload.length,
        chunks: 2,
        name: 'resume.zip',
        content_type: 'application/zip',
        artifact_id: null,
        next_offset: resumedPayload.length,
      }, 202);
    }
    if (path.endsWith('/complete')) {
      return jsonResponse({
        artifact_id: resumedSha,
        sha256: resumedSha,
        size: resumedPayload.length,
        name: 'resume.zip',
        content_type: 'application/zip',
      }, 201);
    }
    throw new Error(`unexpected resume request ${path}`);
  },
});
const resumeFile = new Blob([resumedPayload], { type: 'application/zip' });
Object.defineProperty(resumeFile, 'name', { value: 'resume.zip' });
await resumedClient.upload({
  file: resumeFile,
  deviceId: 'sticks3',
  checkpoint: { upload_id: 'c'.repeat(32) },
});
assert.deepEqual(resumedOffsets, [7]);

const storageValues = new Map();
const storage = {
  getItem: key => storageValues.get(key) || null,
  setItem: (key, value) => storageValues.set(key, value),
  removeItem: key => storageValues.delete(key),
};
writeUploadCheckpoint({ upload_id: 'a'.repeat(32) }, storage);
assert.equal(
  readUploadCheckpoint(storage).upload_id,
  'a'.repeat(32),
);
writeUploadCheckpoint(null, storage);
assert.equal(readUploadCheckpoint(storage), null);

console.log('FIRMWARE_UPLOAD_OK');
