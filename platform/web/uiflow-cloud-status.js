// These are independent guest observations, not a cloud application readiness verdict.
const WEBREPL_STATES = {
  identity_rejected: '云端拒绝设备身份',
  server_error: '云端返回业务错误',
  heartbeat_observed: '已观测到心跳往返（尚未验证远程代码执行）',
  handshake_observed: '已观测到握手（尚未观测到心跳往返）',
  disconnected: '已观测到连接断开',
  not_observed: '尚未观测到连接',
};
const REASONS = {
  mac_not_bound: '设备尚未绑定，请使用屏幕上的配对码在 UIFlow 完成绑定。',
  mac_not_found: '云端未找到该设备，请检查 UIFlow 中的设备绑定。',
  server_error: '具体原因尚未确认，请稍后重试。',
};
const count = value => Number.isSafeInteger(value) && value >= 0 ? value : null;
const known = (values, key) => Object.hasOwn(values, key) ? values[key] : null;

export function uiflowCloudStatusView(session, {cloudExpected = false} = {}) {
  const cloud = session?.uiflow_cloud_status;
  if (!cloudExpected && session?.uiflow_startup?.mode !== 'cloud' && !cloud) return null;
  const historical = ['stopped', 'failed'].includes(session?.state);
  const heading = historical ? 'UIFlow 云端状态 · 末次观测' : 'UIFlow 云端状态';
  if (!cloud || cloud.source !== 'guest-pcap') return {
    heading, tone: 'unknown', lines: ['配对服务：服务未提供诊断状态', '云端 WebREPL：服务未提供诊断状态'],
  };
  if (cloud.state === 'unavailable' || !['observed', 'not_observed'].includes(cloud.state)) return {
    heading, tone: 'unknown', lines: ['配对服务：暂无法判断', '云端 WebREPL：暂无法判断'],
  };
  const pairing = cloud.pairing?.state === 'code_received'
    ? '已收到配对码（不代表已完成绑定）'
    : cloud.pairing?.state === 'not_observed' ? '尚未观测到配对码' : '状态未知';
  const webrepl = cloud.webrepl || {};
  const lines = [`配对服务：${pairing}`, `云端 WebREPL：${known(WEBREPL_STATES, webrepl.state) || '状态未知'}`];
  if (known(REASONS, webrepl.reason)) lines.push(known(REASONS, webrepl.reason));
  if (webrepl.device_registered === true) lines.push('曾观测到云端设备登记回执。');
  const handshakes = count(webrepl.handshakes), disconnects = count(webrepl.disconnects);
  if (handshakes !== null && disconnects !== null) lines.push(`累计观测：握手 ${handshakes} 次 · 断开 ${disconnects} 次`);
  const heartbeats = count(webrepl.heartbeat_roundtrips);
  if (heartbeats !== null && heartbeats > 0) lines.push(`曾观测到心跳往返 ${heartbeats} 次；尚未验证远程代码执行。`);
  if (cloud.observation?.status === 'partial') lines.push('观测尚不完整，仅显示已确认的事件。');
  return {heading, lines, tone: ['identity_rejected', 'server_error', 'disconnected'].includes(webrepl.state) ? 'warning' : 'neutral'};
}

export function renderUIFlowCloudStatus(element, session, options) {
  const view = uiflowCloudStatusView(session, options);
  element.hidden = !view;
  element.dataset.cloudState = view?.tone || '';
  const text = view ? [view.heading, ...view.lines].join('\n') : '';
  // Avoid repeated aria-live announcements when an unchanged snapshot is polled.
  if (element.textContent !== text) element.textContent = text;
}
