import {
  FirmwareUploadClient,
  readUploadCheckpoint,
  writeUploadCheckpoint,
} from './firmware-upload.js';
import {
  capabilitySummary,
  manifestNotice,
  validationIssueRows,
} from './firmware-report.js';

const state = {
  devices: [],
  file: null,
  checkpoint: readUploadCheckpoint(),
  firmware: null,
  session: null,
  controller: null,
  busy: false,
  token: sessionStorage.getItem('m5-service-token') || '',
};

const $ = id => document.getElementById(id);
const tokenProvider = () => state.token;
const client = new FirmwareUploadClient({ tokenProvider });

function formatBytes(value) {
  const bytes = Number(value) || 0;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / 1024 ** 2).toFixed(2)} MiB`;
}

function addTimeline(message) {
  const row = document.createElement('span');
  row.textContent = message;
  $('timeline').prepend(row);
}

function setNotice(message, kind = '') {
  $('notice').className = `notice firmware-notice ${kind}`.trim();
  $('notice').textContent = message;
}

function setBusy(busy) {
  state.busy = busy;
  $('startBtn').disabled = busy;
  $('cancelBtn').hidden = !busy;
  $('deviceSelect').disabled = busy;
  $('requiredCapabilitiesInput').disabled = busy;
  $('optionalCapabilitiesInput').disabled = busy;
  $('firmwareFile').disabled = busy;
}

function parseCapabilityList(value) {
  return [...new Set(
    String(value || '')
      .split(/[\s,]+/)
      .map(item => item.trim().toLowerCase())
      .filter(Boolean),
  )].sort();
}

function updateProgress(event) {
  const ratio = Math.max(0, Math.min(1, Number(event.ratio) || 0));
  $('progressBar').style.width = `${ratio * 100}%`;
  $('progressValue').textContent = `${Math.round(ratio * 100)}%`;
  $('progressLabel').textContent = event.message || event.phase || '处理中';
}

function issuesFrom(error) {
  const issues = error?.details?.issues || [];
  if (!Array.isArray(issues) || !issues.length) return '';
  return issues.map(issue => {
    if (typeof issue === 'string') return issue;
    return `[${issue.code || 'issue'}] ${issue.message || ''}`;
  }).join('\n');
}

function showError(error) {
  const details = issuesFrom(error);
  setNotice(`${error.message || error}${details ? `\n${details}` : ''}`, 'danger');
  $('resultChip').textContent = error.code || 'error';
  $('resultChip').className = 'status-chip danger';
  if (details) {
    $('issues').hidden = false;
    $('issueList').textContent = details;
  }
  addTimeline(`${error.code || 'error'}: ${error.message || error}`);
}

function checkpointFromProgress(event, deviceId) {
  if (!event.upload) return state.checkpoint;
  return {
    ...(state.checkpoint || {}),
    upload_id: event.upload.upload_id,
    device_id: deviceId,
    name: event.upload.name,
    expected_size: event.upload.expected_size,
    expected_sha256: event.upload.expected_sha256,
    received_bytes: event.processed,
    chunks: event.upload.chunks,
    content_type: event.upload.content_type,
    created_at: event.upload.created_at,
    status: event.upload.status,
    artifact_id: event.artifact?.artifact_id || event.upload.artifact_id || null,
    updated_at: new Date().toISOString(),
  };
}

function setCheckpoint(checkpoint) {
  state.checkpoint = checkpoint;
  writeUploadCheckpoint(checkpoint);
}

function renderFirmware(firmware) {
  state.firmware = firmware;
  const manifest = firmware.manifest || {};
  const artifact = manifest.artifact || {};
  const target = manifest.target || {};
  const validation = manifest.validation || {};
  const provenance = manifest.provenance || {};
  const capabilities = manifest.capabilities || {};
  const capabilityRows = capabilitySummary(capabilities);
  const warnings = validation.warnings || [];
  const errors = validation.errors || [];
  $('requiredCapabilitiesInput').value = (
    capabilities.required || []
  ).join(', ');
  $('optionalCapabilitiesInput').value = (
    capabilities.optional || []
  ).join(', ');
  const rows = [
    ['Firmware ID', firmware.firmware_id || firmware.sha256, true],
    ['Source format', provenance.source_format || firmware.kind || 'unknown'],
    ['Target', `${firmware.device_id} · ${target.soc || 'unknown SoC'}`],
    ['Normalized', `${formatBytes(firmware.size)} · ${artifact.normalized_from || artifact.kind || 'merged-flash'}`],
    ['Required capabilities', capabilityRows.required],
    ['Optional capabilities', capabilityRows.optional],
    ['SDKConfig capabilities', capabilityRows.detected],
    ['Image observations', capabilityRows.observed],
    ['Image scan', capabilityRows.observation],
    ['Validation', validation.status || 'unknown'],
    ['Security', `secure boot ${manifest.security?.secure_boot || 'unknown'} · encryption ${manifest.security?.flash_encryption || 'unknown'}`],
  ];
  $('summary').replaceChildren(...rows.map(([label, value, code]) => {
    const cell = document.createElement('div');
    const heading = document.createElement('small');
    const content = document.createElement(code ? 'code' : 'strong');
    heading.textContent = label;
    content.textContent = value;
    cell.append(heading, content);
    return cell;
  }));
  $('resultChip').textContent = validation.status || 'imported';
  $('resultChip').className = `status-chip ${validation.status === 'PASS' ? 'ok' : 'danger'}`;
  $('resultSub').textContent =
    `FirmwareManifest ${manifest.manifest_id?.slice(0, 12) || 'created'} · ${formatBytes(firmware.size)} · warnings ${warnings.length}`;
  const issueRows = validationIssueRows(validation);
  $('issues').hidden = issueRows.length === 0;
  $('issueList').textContent = issueRows.join('\n');
  $('createSessionBtn').hidden = false;
  addTimeline(
    `manifest ${validation.status || 'unknown'} · errors ${errors.length} · warnings ${warnings.length} · observed ${(capabilities.observed || []).length}`,
  );
}

function renderCheckpoint() {
  const checkpoint = state.checkpoint;
  if (!checkpoint) return;
  if (checkpoint.firmware_id) {
    $('progressLabel').textContent = '已恢复规范化固件';
    $('progressValue').textContent = '100%';
    $('progressBar').style.width = '100%';
    setNotice(
      `已恢复 firmware ${checkpoint.firmware_id.slice(0, 12)}。可继续创建虚拟设备。`,
      'ok',
    );
    return;
  }
  if (checkpoint.upload_id) {
    const ratio = checkpoint.expected_size
      ? checkpoint.received_bytes / checkpoint.expected_size
      : 0;
    updateProgress({
      ratio,
      message: checkpoint.status === 'completed'
        ? '上传完成，等待 manifest 导入'
        : `已恢复 upload ${checkpoint.upload_id.slice(0, 8)}`,
    });
    setNotice(
      checkpoint.status === 'completed'
        ? '已恢复完整 artifact，刷新后无需重新上传，可直接继续导入。'
        : `已恢复上传进度。重新选择 ${checkpoint.name} 后点击继续。`,
    );
  }
}

async function restoreCheckpoint() {
  if (!state.checkpoint) return;
  try {
    if (state.checkpoint.firmware_id) {
      state.firmware = await client.request(
        `/api/v1/firmware/${encodeURIComponent(state.checkpoint.firmware_id)}`,
      );
      renderFirmware(state.firmware);
      return;
    }
    if (state.checkpoint.upload_id) {
      const upload = await client.request(
        `/api/v1/artifact-uploads/${encodeURIComponent(state.checkpoint.upload_id)}`,
      );
      state.checkpoint = {
        ...state.checkpoint,
        ...upload,
        device_id: state.checkpoint.device_id,
        received_bytes: upload.received_bytes,
        artifact_id: upload.artifact_id,
      };
      setCheckpoint(state.checkpoint);
      renderCheckpoint();
    }
  } catch (error) {
    if (error.status === 404) {
      setCheckpoint(null);
      return;
    }
    showError(error);
  }
}

async function loadDevices() {
  const payload = await client.request('/api/v1/devices');
  state.devices = (payload.devices || []).filter(device => device.creatable);
  $('deviceSelect').replaceChildren(...state.devices.map(device => {
    const option = document.createElement('option');
    option.value = device.device_id;
    option.textContent = `${device.name} (${device.device_id})${
      device.peripheral_status === 'partial' ? ' · partial' : ''
    }`;
    return option;
  }));
  if (
    state.checkpoint?.device_id
    && state.devices.some(device => device.device_id === state.checkpoint.device_id)
  ) {
    $('deviceSelect').value = state.checkpoint.device_id;
  }
}

function chooseFile(file) {
  if (!file) return;
  const checkpoint = state.checkpoint;
  if (
    checkpoint?.upload_id
    && !checkpoint.firmware_id
    && (checkpoint.name !== file.name || checkpoint.expected_size !== file.size)
  ) {
    setCheckpoint(null);
    setNotice('已放弃旧上传会话；新文件会创建新的上传。');
  }
  state.file = file;
  $('fileSummary').textContent = `${file.name} · ${formatBytes(file.size)}`;
  setNotice('文件已选择。点击开始后会先计算完整 SHA256，再按 4 MiB 分块上传。');
}

function resetUploadUi() {
  updateProgress({ ratio: 0, message: '等待上传' });
  $('resultChip').textContent = 'idle';
  $('resultChip').className = 'status-chip';
}

async function startImport() {
  if (state.busy) return;
  const deviceId = $('deviceSelect').value;
  const requiredCapabilities = parseCapabilityList(
    $('requiredCapabilitiesInput').value,
  );
  const optionalCapabilities = parseCapabilityList(
    $('optionalCapabilitiesInput').value,
  );
  if (!deviceId) return;
  let checkpoint = state.checkpoint;
  state.controller = new AbortController();
  setBusy(true);
  setNotice('准备固件包…');
  addTimeline(`target ${deviceId}`);
  try {
    let artifactId = checkpoint?.artifact_id;
    if (!artifactId) {
      if (!state.file) {
        throw new Error(
          checkpoint?.upload_id
            ? `请重新选择 ${checkpoint.name} 以恢复上传`
            : '请选择固件包',
        );
      }
      const uploadResult = await client.upload({
        file: state.file,
        deviceId,
        checkpoint,
        signal: state.controller.signal,
        onProgress: event => {
          updateProgress(event);
          const next = checkpointFromProgress(event, deviceId);
          if (next) {
            checkpoint = next;
            setCheckpoint(next);
          }
          if (event.phase === 'uploaded') {
            addTimeline(`artifact ${event.artifact.artifact_id.slice(0, 12)}`);
          }
        },
      });
      artifactId = uploadResult.artifact.artifact_id;
    }
    setNotice('正在运行 FirmwareManifest、capability 和 security 检查…');
    addTimeline('importing package');
    const firmware = await client.importPackage({
      deviceId,
      artifactId,
      requiredCapabilities,
      optionalCapabilities,
      signal: state.controller.signal,
    });
    setCheckpoint({
      ...(checkpoint || {}),
      device_id: deviceId,
      artifact_id: artifactId,
      firmware_id: firmware.firmware_id,
      required_capabilities: requiredCapabilities,
      optional_capabilities: optionalCapabilities,
      status: 'imported',
      updated_at: new Date().toISOString(),
    });
    updateProgress({ ratio: 1, message: '固件规范化完成' });
    renderFirmware(firmware);
    setNotice(manifestNotice(firmware.manifest?.validation || {}), 'ok');
  } catch (error) {
    if (error.name === 'AbortError') {
      setNotice('操作已取消。已确认的 upload offset 保留，可稍后续传。');
      addTimeline('cancelled by user');
    } else {
      showError(error);
    }
  } finally {
    state.controller = null;
    setBusy(false);
  }
}

async function cancelUpload() {
  const checkpoint = state.checkpoint;
  state.controller?.abort();
  if (!checkpoint?.upload_id || checkpoint.artifact_id || checkpoint.firmware_id) {
    return;
  }
  try {
    await client.abort(checkpoint.upload_id);
  } catch (error) {
    if (error.status !== 409 && error.status !== 404) showError(error);
  }
  setCheckpoint(null);
  resetUploadUi();
  setNotice('上传会话已取消并清理 staging。');
}

async function createSession() {
  if (!state.firmware || state.busy) return;
  const deviceId = $('deviceSelect').value;
  const ttlSeconds = Number($('ttlInput').value || 600);
  setBusy(true);
  try {
    const session = await client.createSession({
      deviceId,
      firmwareId: state.firmware.firmware_id,
      ttlSeconds,
    });
    state.session = session;
    setCheckpoint({
      ...(state.checkpoint || {}),
      session_id: session.session_id,
      status: 'session-created',
    });
    $('sessionResult').hidden = false;
    $('sessionId').textContent = session.session_id;
    setNotice('虚拟设备会话已创建。请到 Live sessions 查看启动、串口和画面。', 'ok');
    addTimeline(`session ${session.session_id} ${session.state}`);
  } catch (error) {
    showError(error);
  } finally {
    setBusy(false);
  }
}

$('firmwareFile').addEventListener('change', event => {
  chooseFile(event.target.files?.[0]);
});
$('startBtn').addEventListener('click', startImport);
$('cancelBtn').addEventListener('click', cancelUpload);
$('createSessionBtn').addEventListener('click', createSession);
$('tokenInput').value = state.token;
$('tokenInput').addEventListener('change', () => {
  state.token = $('tokenInput').value.trim();
  sessionStorage.setItem('m5-service-token', state.token);
  setNotice('API token 已更新。', 'ok');
});

for (const eventName of ['dragenter', 'dragover']) {
  $('dropZone').addEventListener(eventName, event => {
    event.preventDefault();
    $('dropZone').classList.add('is-dragging');
  });
}
for (const eventName of ['dragleave', 'drop']) {
  $('dropZone').addEventListener(eventName, event => {
    event.preventDefault();
    $('dropZone').classList.remove('is-dragging');
  });
}
$('dropZone').addEventListener('drop', event => {
  chooseFile(event.dataTransfer?.files?.[0]);
});

async function init() {
  resetUploadUi();
  try {
    await loadDevices();
    await restoreCheckpoint();
  } catch (error) {
    showError(error);
  }
}

window.m5Firmware = {
  getState: () => ({
    deviceId: $('deviceSelect').value,
    file: state.file?.name || null,
    requiredCapabilities: parseCapabilityList(
      $('requiredCapabilitiesInput').value,
    ),
    optionalCapabilities: parseCapabilityList(
      $('optionalCapabilitiesInput').value,
    ),
    checkpoint: state.checkpoint,
    firmwareId: state.firmware?.firmware_id || null,
    sessionId: state.session?.session_id || null,
    busy: state.busy,
  }),
  start: startImport,
  cancel: cancelUpload,
};

init();
