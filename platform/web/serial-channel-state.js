const IDS = new Set(['console', 'usb-serial-jtag']);
export function serialChannelLabel(item) {
  return item.channel === 'usb-serial-jtag' ? 'USB Serial/JTAG'
    : item.transport === 'usb-serial-jtag' ? '默认控制台 · USB Serial/JTAG' : '默认控制台';
}

/** Cursors and text belong to one session and one explicitly selected stream. */
export class SerialChannelState {
  constructor(sessionId, limit = 65536) {
    this.sessionId = sessionId; this.limit = limit; this.channel = 'console'; this.epoch = 0;
    this.streams = new Map(); this.channels = [{channel: 'console', transport: 'console', bytes: 0}];
  }
  update(session) {
    if (session.session_id !== this.sessionId) throw new Error('串口会话身份不匹配。');
    this.channels = session.serial_channels === undefined
      ? [{channel: 'console', transport: 'console', bytes: Number(session.serial_bytes || 0)}]
      : session.serial_channels.filter(item => IDS.has(item.channel)
        && Number.isSafeInteger(item.bytes) && item.bytes >= 0).map(item => ({...item}));
    if (!this.channels.some(item => item.channel === this.channel)) {
      this.channel = this.channels[0]?.channel || 'console'; this.epoch++;
    }
    return this.view();
  }
  buffer() {
    if (!this.streams.has(this.channel)) this.streams.set(this.channel, {offset: 0, text: ''});
    return this.streams.get(this.channel);
  }
  select(channel) {
    if (!this.channels.some(item => item.channel === channel)) throw new Error('串口通道不可用。');
    if (channel !== this.channel) {this.channel = channel; this.epoch++;}
    return this.view();
  }
  request(tailBytes = 0) {
    if (!this.channels.some(item => item.channel === this.channel)) return null;
    const size = this.channels.find(item => item.channel === this.channel).bytes;
    return {sessionId: this.sessionId, channel: this.channel, epoch: this.epoch,
      cursor: this.buffer().offset, offset: Math.max(this.buffer().offset, tailBytes ? size - tailBytes : 0)};
  }
  matches(request) { return request && request.sessionId === this.sessionId && request.channel === this.channel && request.epoch === this.epoch && request.cursor === this.buffer().offset; }
  accept(request, payload) {
    if (!this.matches(request)) return null;
    if (payload.session_id !== undefined && payload.session_id !== this.sessionId
      || (payload.channel ?? 'console') !== request.channel
      || !Number.isSafeInteger(payload.next_offset) || payload.next_offset < 0 || typeof payload.data !== 'string') {
      throw new Error('串口通道收据不匹配。');
    }
    const buffer = this.buffer(), reset = payload.next_offset < request.offset;
    if (reset) {
      // The service clamps an old cursor to the truncated file's new EOF.
      // Restart at zero so the already-written prefix is not lost forever.
      buffer.text = ''; buffer.offset = 0;
      return {reset: true, data: '', ...this.view()};
    }
    if (request.offset > buffer.offset) buffer.text = '…较早输出已省略…\n';
    buffer.offset = payload.next_offset;
    buffer.text = (buffer.text + payload.data).slice(-this.limit);
    return {reset, data: payload.data, ...this.view()};
  }
  view() { return {channel: this.channel, channels: this.channels, text: this.buffer().text, bytes: this.buffer().offset}; }
}

export function renderSerialChannelSelect(select, state, disabled = false) {
  const view = state.view(), signature = JSON.stringify(view.channels.map(item => [item.channel, item.transport]));
  if (select.dataset.channels !== signature) {
    select.replaceChildren(...view.channels.map(item => {
      const option = document.createElement('option'); option.value = item.channel;
      option.textContent = serialChannelLabel(item); return option;
    }));
    select.dataset.channels = signature;
  }
  select.value = view.channel; select.disabled = disabled || view.channels.length < 2;
}
