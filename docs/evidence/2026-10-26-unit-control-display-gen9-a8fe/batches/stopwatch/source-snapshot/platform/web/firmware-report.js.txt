function formatBytes(value) {
  const bytes = Math.max(0, Number(value) || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / 1024 ** 2).toFixed(2)} MiB`;
}

function capabilityNames(entries, formatter) {
  if (!Array.isArray(entries) || !entries.length) return 'none';
  return entries.map(entry => {
    if (typeof entry === 'string') return entry;
    return formatter(entry);
  }).join(', ');
}

export function capabilitySummary(capabilities = {}) {
  const observation = capabilities.observation;
  return {
    required: capabilityNames(
      capabilities.required,
      entry => String(entry),
    ),
    optional: capabilityNames(
      capabilities.optional,
      entry => String(entry),
    ),
    detected: capabilityNames(
      capabilities.detected,
      entry => `${entry.capability || 'unknown'} (${entry.flag || entry.source || 'detected'})`,
    ),
    observed: capabilityNames(
      capabilities.observed,
      entry => {
        const signatures = Array.isArray(entry.signatures)
          ? entry.signatures.join('|')
          : 'signature';
        return `${entry.capability || 'unknown'} (${entry.confidence || 'low'}: ${signatures})`;
      },
    ),
    observation: observation && typeof observation === 'object'
      ? [
        observation.status || 'unknown',
        `${formatBytes(observation.bytes_scanned)} / ${formatBytes(observation.bytes_total)}`,
        observation.truncated ? 'truncated' : 'complete',
      ].join(' · ')
      : 'not available',
  };
}

export function validationIssueRows(validation = {}) {
  const errors = Array.isArray(validation.errors) ? validation.errors : [];
  const warnings = Array.isArray(validation.warnings) ? validation.warnings : [];
  return [
    ...errors.map(issue => issueRow('error', issue)),
    ...warnings.map(issue => issueRow('warning', issue)),
  ];
}

function issueRow(severity, issue) {
  if (typeof issue === 'string') return `[${severity}] ${issue}`;
  return `[${issue?.severity || severity}:${issue?.code || 'issue'}] ${issue?.message || ''}`;
}

export function manifestNotice(validation = {}) {
  const errors = Array.isArray(validation.errors) ? validation.errors.length : 0;
  const warnings = Array.isArray(validation.warnings) ? validation.warnings.length : 0;
  if (validation.status === 'PASS') {
    return warnings
      ? `FirmwareManifest 已生成，带 ${warnings} 条审查 warning；请检查 capability 来源后创建虚拟设备。`
      : 'FirmwareManifest 已生成；capability 检查通过，可以创建虚拟设备。';
  }
  return `FirmwareManifest ${validation.status || 'unknown'}：${errors} errors · ${warnings} warnings。`;
}
