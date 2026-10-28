import assert from 'node:assert/strict';
import {PublicDeviceService} from '../web/public-service.js';

// The stable caller key is a session-create JSON field. Replaying the same
// operation preserves its complete body rather than silently changing a key.
{
  const calls = [], units = [{unit_id: 'pir', port: 'A'}];
  const service = new PublicDeviceService('https://service.example/lab', {fetchImpl: async (url, options) => {
    calls.push({url, options});
    return Response.json({session_id: 'same-session', idempotent_replay: calls.length > 1}, {status: 202});
  }});
  const operation = {deviceId: 'cores3', firmwareId: 'firmware-a', units, idempotencyKey: 'public-op-123'};
  await service.create(operation);
  const replay = await service.create(operation);
  assert.equal(calls.length, 2);
  assert.equal(calls[0].url, 'https://service.example/lab/api/v1/sessions');
  assert.equal(calls[0].options.method, 'POST');
  assert.equal(calls[0].options.headers.has('Idempotency-Key'), false);
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    device_id: 'cores3', firmware_id: 'firmware-a', ttl_seconds: 600,
    units, idempotency_key: 'public-op-123',
  });
  assert.equal(calls[1].options.body, calls[0].options.body);
  assert.equal(replay.idempotent_replay, true);
}

// Structured API failures retain the HTTP status and code for the controller.
for (const [status, code, outcomeUnknown] of [[409, 'session_idempotency_conflict', false], [503, 'backend_not_ready', true]]) {
  let calls = 0;
  const service = new PublicDeviceService('https://service.example', {fetchImpl: async () => {
    calls++;
    return Response.json({error: {code, message: 'test failure'}}, {status, headers: {'X-Request-ID': 'request-123'}});
  }});
  await assert.rejects(service.create({deviceId: 'cores3', idempotencyKey: 'unchanged-key'}), error => {
    assert.equal(error.status, status);
    assert.equal(error.code, code);
    assert.equal(error.requestId, 'request-123');
    assert.equal(error.outcomeUnknown, outcomeUnknown);
    return true;
  });
  assert.equal(calls, 1, 'the service client must never retry or mint another key');
}

// A malformed success receipt cannot be treated as proof of no allocation.
for (const status of [200, 202, 503]) {
  const service = new PublicDeviceService('https://service.example', {fetchImpl: async () =>
    new Response('{truncated', {status, headers: {'X-Request-ID': 'truncated-123'}})});
  await assert.rejects(service.create({deviceId: 'cores3', idempotencyKey: 'recover-this-key'}), error => {
    assert.equal(error.status, status);
    assert.equal(error.code, 'invalid_service_response');
    assert.equal(error.outcomeUnknown, true);
    assert.equal(error.requestId, 'truncated-123');
    return true;
  });
}

// Transport rejection and cancellation are observable, with no hidden retry.
for (const failure of [new TypeError('network unavailable'), new DOMException('cancelled', 'AbortError')]) {
  let calls = 0;
  const service = new PublicDeviceService('https://service.example', {fetchImpl: async () => {calls++; throw failure;}});
  await assert.rejects(service.create({deviceId: 'cores3', idempotencyKey: 'stable-operation'}), error => error === failure);
  assert.equal(calls, 1);
}

console.log('PUBLIC_SERVICE_IDEMPOTENCY_OK: stable JSON key, replay body, HTTP errors, ambiguous receipts and no implicit retry');
