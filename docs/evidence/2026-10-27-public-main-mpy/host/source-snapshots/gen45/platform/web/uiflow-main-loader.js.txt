// Mirrors uiflow_main_loader.main_loader_verified. This is an observed guest
// capability bound to one process, never a promise derived from a firmware name.
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const positive = value => Number.isSafeInteger(value) && value > 0;
const ID = /^[0-9a-f]{32}$/;
const CANARY_SHA = '0713a25c1bdfb35a2ba0ebf431ec1ccccaa32846eb0dd74f3ebb230ffeac9420';
const SOURCE_SHA = 'e21b73a791266cea38d5c2050e0d4ae48180f4e3908bf748db4b10995908ed78';
const COMPILER_SHA = 'c8646ebb97047c1c56a9d164474729a1bf13508e49d4cd3b1e5c6f00c509911b';

export function mainMpyVerified(record, session) {
  if (!object(record) || record.schema_version !== 1 || record.status !== 'verified'
    || record.mpy_entrypoint !== true || record.loader !== 'micropython-override-main-v1'
    || !Number.isSafeInteger(record.mpy) || record.mpy < 0 || (record.mpy & 255) !== 6
    || record.small_int_bits !== 31) return false;
  const probe = record.probe, identity = record.identity;
  if (!object(probe) || !ID.test(probe.nonce || '') || probe.kind !== 'uiflow-main-mpy-canary-v1'
    || probe.status !== 'PASS' || probe.canary_sha256 !== CANARY_SHA || probe.source_sha256 !== SOURCE_SHA
    || probe.compiler_sha256 !== COMPILER_SHA || probe.file_sha256 !== CANARY_SHA || probe.file_bytes !== 375
    || probe.owner_restored !== true || probe.cleanup_complete !== true || probe.body_entered !== true
    || !positive(probe.owner_before_id) || probe.owner_after_id !== probe.owner_before_id) return false;
  const actual = probe.actual_identity;
  if (!object(actual) || actual.if_main !== true || actual.name !== '__main__' || actual.real_main_name !== 'main'
    || actual.nonce !== probe.nonce || actual.file !== `/flash/.m5-loader-probe-${probe.nonce}/main.mpy`
    || !positive(actual.main_id) || actual.main_id === probe.owner_before_id
    || actual.sys_main_id !== actual.main_id || actual.import_main_id !== actual.main_id) return false;
  return object(identity) && object(session) && positive(session.pid) && session.state === 'running'
    && identity.session_id === session.session_id && identity.pid === session.pid
    && identity.firmware_sha256 === session.firmware_sha256 && identity.runtime === session.runtime
    && identity.device_id === session.device_id && typeof identity.process_start_token === 'string'
    && identity.process_start_token.length > 0 && positive(session.worker?.generation)
    && identity.worker_generation === session.worker.generation;
}
