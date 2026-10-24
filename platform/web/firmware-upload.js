import { sha256Blob, sha256Bytes } from './sha256.js';

export const FIRMWARE_UPLOAD_STORAGE_KEY = 'm5-firmware-upload-v1';
export const FIRMWARE_CHUNK_BYTES = 4 * 1024 * 1024;

function abortError() {
  const error = new Error('upload cancelled');
  error.name = 'AbortError';
  return error;
}

function wait(milliseconds, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError());
      return;
    }
    const timer = setTimeout(resolve, milliseconds);
    signal?.addEventListener('abort', () => {
      clearTimeout(timer);
      reject(abortError());
    }, { once: true });
  });
}

export class FirmwareUploadError extends Error {
  constructor(message, { status = 0, code = 'upload_error', details = {} } = {}) {
    super(message);
    this.name = 'FirmwareUploadError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export class FirmwareUploadClient {
  constructor({
    fetchImpl = globalThis.fetch,
    tokenProvider = () => '',
    hashBlob = sha256Blob,
    chunkBytes = FIRMWARE_CHUNK_BYTES,
    sleep = wait,
  } = {}) {
    this.fetchImpl = (...args) => fetchImpl(...args);
    this.tokenProvider = tokenProvider;
    this.hashBlob = hashBlob;
    this.chunkBytes = chunkBytes;
    this.sleep = sleep;
  }

  headers(extra = {}) {
    const headers = new Headers(extra);
    const token = this.tokenProvider();
    if (token) headers.set('Authorization', `Bearer ${token}`);
    return headers;
  }

  async request(path, options = {}, attempts = 3) {
    let lastError;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      if (options.signal?.aborted) throw abortError();
      try {
        const response = await this.fetchImpl(path, {
          ...options,
          headers: this.headers(options.headers),
        });
        const type = response.headers.get('Content-Type') || '';
        const body = type.includes('json')
          ? await response.json()
          : await response.text();
        if (response.ok) return body;
        const error = new FirmwareUploadError(
          body?.error?.message || `request failed with ${response.status}`,
          {
            status: response.status,
            code: body?.error?.code || 'upload_error',
            details: body?.error || {},
          },
        );
        if (response.status < 500 || attempt + 1 >= attempts) throw error;
        lastError = error;
      } catch (error) {
        if (error?.name === 'AbortError') throw error;
        if (error instanceof FirmwareUploadError) {
          if (error.status < 500 || attempt + 1 >= attempts) throw error;
          lastError = error;
        } else {
          lastError = error;
          if (attempt + 1 >= attempts) {
            throw new FirmwareUploadError(
              `network error: ${error.message}`,
              { code: 'network_error' },
            );
          }
        }
      }
      await this.sleep(250 * 2 ** attempt, options.signal);
    }
    throw lastError;
  }

  json(path, payload, options = {}) {
    return this.request(path, {
      ...options,
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  }

  async upload({ file, deviceId, checkpoint = null, onProgress = () => {}, signal }) {
    if (!file) throw new FirmwareUploadError('select a firmware package');
    onProgress({
      phase: 'hashing',
      processed: 0,
      total: file.size,
      ratio: 0,
      message: '正在校验文件 SHA256…',
    });
    const expectedSha256 = await this.hashBlob(file, {
      chunkSize: this.chunkBytes,
      onProgress: event => onProgress({
        phase: 'hashing',
        processed: event.processed,
        total: event.total,
        ratio: event.ratio,
        message: '正在校验文件 SHA256…',
      }),
    });
    if (signal?.aborted) throw abortError();

    let upload;
    if (checkpoint?.upload_id) {
      upload = await this.request(
        `/api/v1/artifact-uploads/${encodeURIComponent(checkpoint.upload_id)}`,
        { signal },
      );
      if (
        upload.expected_size !== file.size ||
        upload.expected_sha256 !== expectedSha256 ||
        upload.name !== file.name
      ) {
        throw new FirmwareUploadError(
          '重新选择的文件与待恢复上传不一致',
          { code: 'resume_file_mismatch' },
        );
      }
    } else {
      upload = await this.json(
        '/api/v1/artifact-uploads',
        {
          expected_size: file.size,
          expected_sha256: expectedSha256,
          name: file.name,
          content_type: file.type || 'application/octet-stream',
        },
        { signal },
      );
    }

    let receivedBytes = Number(upload.received_bytes) || 0;
    onProgress({
      phase: 'uploading',
      upload,
      processed: receivedBytes,
      total: file.size,
      ratio: receivedBytes / file.size,
      message: receivedBytes
        ? `从 ${receivedBytes} bytes 继续上传`
        : '开始上传固件包',
    });
    while (receivedBytes < file.size) {
      if (signal?.aborted) throw abortError();
      const end = Math.min(file.size, receivedBytes + this.chunkBytes);
      const chunk = file.slice(receivedBytes, end);
      const chunkSha256 = sha256Bytes(
        new Uint8Array(await chunk.arrayBuffer()),
      );
      try {
        const progress = await this.request(
          `/api/v1/artifact-uploads/${encodeURIComponent(upload.upload_id)}/chunks`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/octet-stream',
              'X-Chunk-Offset': String(receivedBytes),
              'X-Chunk-SHA256': chunkSha256,
            },
            body: chunk,
            signal,
          },
        );
        receivedBytes = progress.next_offset;
        upload = progress;
      } catch (error) {
        if (error?.code !== 'invalid_chunk_offset') throw error;
        upload = await this.request(
          `/api/v1/artifact-uploads/${encodeURIComponent(upload.upload_id)}`,
          { signal },
        );
        receivedBytes = upload.received_bytes;
      }
      onProgress({
        phase: 'uploading',
        upload,
        processed: receivedBytes,
        total: file.size,
        ratio: receivedBytes / file.size,
        message: `已上传 ${receivedBytes} / ${file.size} bytes`,
      });
    }
    const artifact = await this.request(
      `/api/v1/artifact-uploads/${encodeURIComponent(upload.upload_id)}/complete`,
      { method: 'POST', signal },
    );
    onProgress({
      phase: 'uploaded',
      upload: { ...upload, status: 'completed' },
      artifact,
      processed: file.size,
      total: file.size,
      ratio: 1,
      message: '固件包上传完成',
    });
    return { upload: { ...upload, status: 'completed' }, artifact };
  }

  importPackage({
    deviceId,
    artifactId,
    requiredCapabilities = [],
    optionalCapabilities = [],
    signal,
  }) {
    return this.json(
      '/api/v1/firmware/import',
      {
        device_id: deviceId,
        artifact_id: artifactId,
        required_capabilities: requiredCapabilities,
        optional_capabilities: optionalCapabilities,
      },
      { signal },
    );
  }

  createSession({ deviceId, firmwareId, ttlSeconds, signal }) {
    return this.json(
      '/api/v1/sessions',
      {
        device_id: deviceId,
        firmware_id: firmwareId,
        ttl_seconds: ttlSeconds,
      },
      { signal },
    );
  }

  async abort(uploadId, { signal } = {}) {
    if (!uploadId) return null;
    return this.request(
      `/api/v1/artifact-uploads/${encodeURIComponent(uploadId)}`,
      { method: 'DELETE', signal },
      1,
    );
  }
}

export function readUploadCheckpoint(storage = globalThis.localStorage) {
  try {
    const value = JSON.parse(
      storage.getItem(FIRMWARE_UPLOAD_STORAGE_KEY) || 'null',
    );
    return value && typeof value === 'object' ? value : null;
  } catch {
    return null;
  }
}

export function writeUploadCheckpoint(
  checkpoint,
  storage = globalThis.localStorage,
) {
  if (!checkpoint) {
    storage.removeItem(FIRMWARE_UPLOAD_STORAGE_KEY);
    return;
  }
  storage.setItem(
    FIRMWARE_UPLOAD_STORAGE_KEY,
    JSON.stringify(checkpoint),
  );
}
