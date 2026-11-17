//! Tab5 software-I²C board detection and native ST7123 HP I²C touch reports.

use esp_part::prelude::*;

const TOUCH_ADDRESS: u32 = 0x55;
const WIDTH: u16 = 720;
const HEIGHT: u16 = 1280;
const TOUCH_COUNT: u16 = 0x0009;
const STATUS: u16 = 0x0010;
const FIRST_POINT: u16 = 0x0014;
const POINT_END: u16 = FIRST_POINT + 7;
const TAP_NS: u64 = 180_000_000;
const HOLD_REFRESH_NS: u64 = 16_000_000;
const NS_PER_MS: u64 = 1_000_000;
const DRAG_STEPS: u8 = 5;
const DRAG_STEP_NS: u64 = 60 * NS_PER_MS;
const UNREAD_REPORT_TIMEOUT_NS: u64 = 1_000_000_000;
const MAX_READ: u32 = 512;
const POWER_EXPANDER: u8 = 0x44;
const OUTPUT_DIRECTION: usize = 0x03;
const OUTPUT_STATE: usize = 0x05;
const OUTPUT_HIGH_IMPEDANCE: usize = 0x07;
const POWER_OFF: u8 = 1 << 4;

// The pinned esp-emu routes the entire claimed HP I²C port to the part.
// Keep the same other devices as the service's static Tab5 fixtures.
const HARDWARE_REGISTERS: &[(u8, &[(u8, u8)])] = &[
    (0x32, &[]),
    (
        0x41,
        &[(0xfe, 0x54), (0xff, 0x49), (0x02, 0x19), (0x04, 0xb0)],
    ),
    (0x43, &[(0x01, 0xa2)]),
    (0x44, &[(0x01, 0xa2)]),
    (0x68, &[(0x00, 0x24)]),
];

#[derive(Clone, Copy)]
enum Next {
    Write,
    Read,
    Ignore,
}

#[derive(Clone, Copy, Default)]
enum Phase {
    #[default]
    Idle,
    Receive {
        address: bool,
        data: u8,
        count: u8,
    },
    NeedAck(Next),
    AckLow(Next),
    AckHigh(Next),
    Transmit {
        data: u8,
        next_bit: u8,
    },
    LastDataBit,
    ReadMasterAck,
    ContinueRead,
}

struct Registers {
    address: u8,
    pointer_width: u8,
    pointer: u16,
    registers: [u8; 256],
}

impl Registers {
    fn new(address: u8, pointer_width: u8, seed: &[(u8, u8)]) -> Self {
        let mut registers = [0; 256];
        for (reg, byte) in seed {
            registers[*reg as usize] = *byte;
        }
        Self {
            address,
            pointer_width,
            pointer: 0,
            registers,
        }
    }

    fn power_off_signal(&self) -> bool {
        let output = self.registers[OUTPUT_DIRECTION] & !self.registers[OUTPUT_HIGH_IMPEDANCE];
        output & self.registers[OUTPUT_STATE] & POWER_OFF != 0
    }

    fn read(&mut self) -> u8 {
        let value = self
            .registers
            .get(self.pointer as usize)
            .copied()
            .unwrap_or(0);
        self.pointer = self.pointer.wrapping_add(1);
        value
    }

    fn transfer(&mut self, request: &I2cTransaction) -> Vec<u8> {
        if let Some((address, values)) = request.write.split_first() {
            self.pointer = u16::from(*address);
            for value in values {
                self.registers[self.pointer as usize] = *value;
                self.pointer = (self.pointer + 1) & 0xff;
            }
        }
        (0..request.read_len)
            .map(|_| {
                let value = self.registers[self.pointer as usize];
                self.pointer = (self.pointer + 1) & 0xff;
                value
            })
            .collect()
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
struct Point {
    x: u16,
    y: u16,
}

impl Point {
    fn parse(coordinates: &str) -> Option<Self> {
        let (x, y) = coordinates.split_once(',')?;
        let point = Self {
            x: x.parse().ok()?,
            y: y.parse().ok()?,
        };
        (point.x < WIDTH && point.y < HEIGHT).then_some(point)
    }

    fn interpolate(self, end: Self, step: u8) -> Self {
        let at_step = |start: u16, end: u16| {
            let start = i32::from(start);
            let distance = i32::from(end) - start;
            (start + (distance * i32::from(step)).div_euclid(i32::from(DRAG_STEPS))) as u16
        };
        Self {
            x: at_step(self.x, end.x),
            y: at_step(self.y, end.y),
        }
    }
}

struct Drag {
    start: Point,
    end: Point,
    moves: u8,
    started_at: Option<u64>,
    next_at: Option<u64>,
    last_poll: Option<u64>,
}

#[derive(Default)]
struct St7123 {
    pointer: u16,
    point: Option<Point>,
    irq_level: Option<bool>,
    press_at: Option<u64>,
    length_ns: u64,
    refresh_at: Option<u64>,
    refresh_enabled: bool,
    refresh_pending: bool,
    refresh_acknowledged: u32,
    hold_ms: u32,
    drag: Option<Drag>,
    drag_ms: u32,
    pending_at: Option<u64>,
    needs_read: bool,
    reports: u32,
    acknowledged: u32,
    rejected: u32,
    status_reads: u32,
    coordinate_reads: u32,
}

impl St7123 {
    fn start_contact(&mut self, input: &str) -> Option<()> {
        if self.point.is_some() || self.needs_read {
            return None;
        }
        let (action, parameters) = input.split_once(':')?;
        let (point, length_ns, drag) = match action {
            "tap" => (Point::parse(parameters)?, TAP_NS, None),
            "hold" => {
                let (coordinates, duration) = parameters.rsplit_once(',')?;
                let milliseconds = duration.parse::<u64>().ok()?;
                if !(250..=5000).contains(&milliseconds) {
                    return None;
                }
                (Point::parse(coordinates)?, milliseconds * NS_PER_MS, None)
            }
            "drag" => {
                let (start, end) = parameters.split_once(':')?;
                let (start, end) = (Point::parse(start)?, Point::parse(end)?);
                if start == end {
                    return None;
                }
                (
                    start,
                    0,
                    Some(Drag {
                        start,
                        end,
                        moves: 0,
                        started_at: None,
                        next_at: None,
                        last_poll: None,
                    }),
                )
            }
            _ => return None,
        };
        self.point = Some(point);
        self.drag = drag;
        self.drag_ms = 0;
        self.length_ns = length_ns;
        self.refresh_enabled = action == "hold";
        self.refresh_acknowledged = 0;
        self.hold_ms = 0;
        self.needs_read = true;
        self.reports = self.reports.saturating_add(1);
        Some(())
    }

    fn report(&self) -> [u8; 7] {
        self.point.map_or([0; 7], |point| {
            let [xh, xl] = point.x.to_be_bytes();
            let [yh, yl] = point.y.to_be_bytes();
            [0x80 | xh, xl, yh, yl, 20, 20, 0]
        })
    }

    fn read_register(&self, address: u16) -> u8 {
        match address {
            0x0000 => 3,
            0x0005 => (WIDTH - 1).to_be_bytes()[0],
            0x0006 => (WIDTH - 1).to_be_bytes()[1],
            0x0007 => (HEIGHT - 1).to_be_bytes()[0],
            0x0008 => (HEIGHT - 1).to_be_bytes()[1],
            TOUCH_COUNT => 1,
            STATUS if self.point.is_some() => 0x08,
            FIRST_POINT..POINT_END => self.report()[(address - FIRST_POINT) as usize],
            _ => 0,
        }
    }

    fn transfer(&mut self, request: &I2cTransaction) -> Vec<u8> {
        if let [hi, lo, ..] = request.write.as_slice() {
            self.pointer = u16::from_be_bytes([*hi, *lo]);
        }
        let start = self.pointer;
        let end = u32::from(start) + request.read_len;
        let data = (0..request.read_len)
            .map(|_| {
                let byte = self.read_register(self.pointer);
                self.pointer = self.pointer.wrapping_add(1);
                byte
            })
            .collect();
        let status_read = start <= STATUS && end > u32::from(STATUS);
        let coordinate_read = start <= FIRST_POINT && end >= u32::from(POINT_END);
        self.status_reads = self.status_reads.saturating_add(u32::from(status_read));
        self.coordinate_reads = self
            .coordinate_reads
            .saturating_add(u32::from(coordinate_read));
        if self.needs_read
            && (if self.point.is_some() {
                coordinate_read
            } else {
                status_read || coordinate_read
            })
        {
            self.needs_read = false;
            self.pending_at = None;
            if self.refresh_pending {
                self.refresh_pending = false;
                self.refresh_acknowledged = self.refresh_acknowledged.saturating_add(1);
            } else {
                self.acknowledged = self.acknowledged.saturating_add(1);
            }
        }
        data
    }

    fn advance_drag(&mut self, now_ns: u64) {
        let drag = self.drag.as_mut().unwrap();
        let started_at = *drag.started_at.get_or_insert(now_ns);
        let next_at = drag
            .next_at
            .get_or_insert(now_ns.saturating_add(DRAG_STEP_NS));
        // Keep the prior slot visible until its complete guest read. Give
        // IRQ-driven readers an intervening high level for every move.
        if self.irq_level == Some(false) || now_ns < *next_at {
            return;
        }
        if drag.moves == DRAG_STEPS {
            self.drag_ms = ((now_ns - started_at) / NS_PER_MS).min(u32::MAX as u64) as u32;
            self.release();
        } else {
            drag.moves += 1;
            self.point = Some(drag.start.interpolate(drag.end, drag.moves));
            *next_at = now_ns.saturating_add(DRAG_STEP_NS);
            self.needs_read = true;
            self.reports = self.reports.saturating_add(1);
        }
    }

    fn poll(&mut self, pin: u32, now_ns: u64) -> Option<EmulatorMessage> {
        let contact_was_active = self.point.is_some();
        if let Some(drag) = &mut self.drag {
            if drag
                .last_poll
                .replace(now_ns)
                .is_some_and(|previous| now_ns < previous)
            {
                self.release();
            }
        }
        if let Some(pressed_at) = self.press_at {
            let elapsed = now_ns.saturating_sub(pressed_at);
            if elapsed >= self.length_ns {
                self.hold_ms = (elapsed / NS_PER_MS).min(u32::MAX as u64) as u32;
                self.release();
            }
        }
        // A paused or stopped polling driver must not strand a physical contact.
        // Missing reports stay unacknowledged so the API still fails that input.
        if self.needs_read {
            let pending_at = *self.pending_at.get_or_insert(now_ns);
            if now_ns.saturating_sub(pending_at) >= UNREAD_REPORT_TIMEOUT_NS {
                self.pending_at = None;
                if self.refresh_pending {
                    self.refresh_pending = false;
                    self.needs_read = false;
                } else if self.point.is_some() {
                    self.release();
                } else {
                    self.needs_read = false;
                }
            }
        }
        if self.drag.is_some() && !self.needs_read {
            self.advance_drag(now_ns);
        } else if self.point.is_some() && !self.needs_read {
            self.press_at.get_or_insert(now_ns);
            if self.refresh_enabled {
                let refresh_at = self
                    .refresh_at
                    .get_or_insert(now_ns.saturating_add(HOLD_REFRESH_NS));
                // Give each report a falling edge after the prior read deasserted INT.
                if self.irq_level != Some(false) && now_ns >= *refresh_at {
                    *refresh_at = now_ns.saturating_add(HOLD_REFRESH_NS);
                    self.refresh_pending = true;
                    self.needs_read = true;
                }
            }
        }
        // Delimit the release IRQ even if the last move or refresh was unread.
        if contact_was_active && self.point.is_none() && self.irq_level == Some(false) {
            self.irq_level = Some(true);
            return Some(drive(pin, true, now_ns));
        }
        let level = !self.needs_read;
        if self.irq_level == Some(level) {
            return None;
        }
        self.irq_level = Some(level);
        Some(drive(pin, level, now_ns))
    }

    fn release(&mut self) {
        self.point = None;
        self.drag = None;
        self.press_at = None;
        self.pending_at = None;
        self.refresh_at = None;
        self.refresh_pending = false;
        self.needs_read = true;
        self.reports = self.reports.saturating_add(1);
    }
}

#[derive(Default)]
struct Bus {
    sda: u32,
    scl: u32,
    old: Option<(bool, bool)>,
    phase: Phase,
    selected: Option<usize>,
    pointer_bytes: u8,
    pointer_work: u16,
    desired_level: bool,
    driven_level: bool,
    addressed: u32,
    data_bytes: u32,
    chips: Vec<Registers>,
    interrupt: u32,
    hardware_chips: Vec<Registers>,
    touch: St7123,
    power_latch_wired: bool,
    power_off_requested: bool,
    power_latched_ns: Option<u64>,
    chip_enabled: bool,
}

impl Bus {
    fn received(&mut self, address: bool, byte: u8) -> Next {
        if address {
            let Some(index) = self.chips.iter().position(|chip| chip.address == byte >> 1) else {
                return Next::Ignore;
            };
            self.addressed += 1;
            self.selected = Some(index);
            self.pointer_bytes = 0;
            self.pointer_work = 0;
            return if byte & 1 != 0 {
                Next::Read
            } else {
                Next::Write
            };
        }
        let chip = &mut self.chips[self.selected.unwrap()];
        if self.pointer_bytes < chip.pointer_width {
            self.pointer_work = (self.pointer_work << 8) | u16::from(byte);
            self.pointer_bytes += 1;
            if self.pointer_bytes == chip.pointer_width {
                chip.pointer = self.pointer_work;
            }
        } else {
            if let Some(register) = chip.registers.get_mut(chip.pointer as usize) {
                *register = byte;
            }
            chip.pointer = chip.pointer.wrapping_add(1);
        }
        self.data_bytes += 1;
        Next::Write
    }

    fn transmit_byte(&mut self) {
        let data = self.chips[self.selected.unwrap()].read();
        self.desired_level = data & 0x80 != 0;
        self.phase = Phase::Transmit { data, next_bit: 7 };
    }

    fn rising(&mut self, sda: bool) {
        match self.phase {
            Phase::Receive {
                address,
                data,
                count,
            } => {
                let next = (data << 1) | u8::from(sda);
                self.phase = if count == 7 {
                    Phase::NeedAck(self.received(address, next))
                } else {
                    Phase::Receive {
                        address,
                        data: next,
                        count: count + 1,
                    }
                };
            }
            Phase::AckLow(next) => self.phase = Phase::AckHigh(next),
            Phase::Transmit { data, next_bit } => {
                self.phase = if next_bit == 0 {
                    Phase::LastDataBit
                } else {
                    Phase::Transmit {
                        data,
                        next_bit: next_bit - 1,
                    }
                };
            }
            Phase::ReadMasterAck => {
                self.phase = if sda {
                    Phase::Idle
                } else {
                    Phase::ContinueRead
                };
            }
            _ => (),
        }
    }

    fn falling(&mut self) {
        match self.phase {
            Phase::NeedAck(next) => {
                self.desired_level = matches!(next, Next::Ignore);
                self.phase = Phase::AckLow(next);
            }
            Phase::AckHigh(Next::Read) | Phase::ContinueRead => self.transmit_byte(),
            Phase::AckHigh(next) => {
                self.desired_level = true;
                self.phase = match next {
                    Next::Write => Phase::Receive {
                        address: false,
                        data: 0,
                        count: 0,
                    },
                    _ => Phase::Idle,
                };
            }
            Phase::Transmit { data, next_bit } => self.desired_level = data & (1 << next_bit) != 0,
            Phase::LastDataBit => {
                self.desired_level = true;
                self.phase = Phase::ReadMasterAck;
            }
            _ => (),
        }
    }
}

impl Device for Bus {
    const NAME: &'static str = "software-i2c";
    const ON_BUS: bool = true;
    const ON_MESSAGE: bool = true;

    fn configure(&mut self, config: &PartConfig) {
        self.sda = config.pins["SDA"];
        self.scl = config.pins["SCL"];
        self.interrupt = config.pins["INT"];
        self.power_latch_wired = config.en_pins.iter().any(|pin| pin == "POWER_ENABLE");
        self.chip_enabled = true;
        self.desired_level = true;
        self.driven_level = true;
        self.chips = vec![
            Registers::new(0x43, 1, &[(1, 0xa2)]),
            Registers::new(0x44, 1, &[(1, 0xa2)]),
            Registers::new(0x55, 2, &[(0, 3)]),
        ];
        self.hardware_chips = HARDWARE_REGISTERS
            .iter()
            .map(|(addr, seed)| {
                let mut chip = Registers::new(*addr, 1, seed);
                if self.power_latch_wired && *addr == POWER_EXPANDER {
                    chip.registers[OUTPUT_HIGH_IMPEDANCE] = u8::MAX;
                }
                chip
            })
            .collect();
    }

    fn claims(&self) -> Vec<Claim> {
        let mut claims = vec![
            drives((1 << self.sda) | (1 << self.interrupt)),
            watches((1 << self.sda) | (1 << self.scl)),
        ];
        if self.power_latch_wired {
            claims.push(en());
        }
        claims.extend(
            std::iter::once(TOUCH_ADDRESS)
                .chain(
                    self.hardware_chips
                        .iter()
                        .map(|chip| u32::from(chip.address)),
                )
                .map(|addr| Claim {
                    what: Some(claim::What::I2c(I2cClaim {
                        addr,
                        scl_pin: Some(self.scl),
                        sda_pin: Some(self.sda),
                    })),
                }),
        );
        claims
    }

    fn on_bus(&mut self, request: &BusRequest) -> Option<BusReply> {
        let mut reply = BusReply {
            correlation_id: request.correlation_id,
            op: BusOp::I2c as i32,
            ..Default::default()
        };
        let Some(bus_request::Op::I2c(i2c)) = &request.op else {
            return Some(reply);
        };
        if i2c.read_len > MAX_READ {
            return Some(reply);
        }
        reply.data = if i2c.addr == TOUCH_ADDRESS && i2c.write.len() != 1 {
            self.touch.transfer(i2c)
        } else if let Some(chip) = self
            .hardware_chips
            .iter_mut()
            .find(|chip| u32::from(chip.address) == i2c.addr)
        {
            let was_high = chip.power_off_signal();
            let bytes = chip.transfer(i2c);
            if self.power_latch_wired && chip.address == POWER_EXPANDER
                && !was_high && chip.power_off_signal()
            {
                self.power_off_requested = true;
            }
            bytes
        } else {
            return Some(reply);
        };
        reply.ack = true;
        Some(reply)
    }

    fn on_input(&mut self, input: &str) {
        if self.touch.start_contact(input).is_none() {
            self.touch.rejected = self.touch.rejected.saturating_add(1);
        }
    }

    fn on_pins(&mut self, levels: u64, _now_ns: u64) {
        let scl = levels & (1 << self.scl) != 0;
        let sda = levels & (1 << self.sda) != 0;
        let Some((old_scl, old_sda)) = self.old.replace((scl, sda)) else {
            return;
        };
        if old_scl && scl && old_sda != sda {
            self.desired_level = true;
            self.phase = if sda {
                Phase::Idle
            } else {
                Phase::Receive {
                    address: true,
                    data: 0,
                    count: 0,
                }
            };
        } else if scl && !old_scl {
            self.rising(sda);
        } else if !scl && old_scl {
            self.falling();
        }
    }

    fn on_en(&mut self, level: bool, _at_ns: u64) {
        self.chip_enabled = level;
    }

    fn poll(&mut self, now_ns: u64) -> Option<EmulatorMessage> {
        if self.power_off_requested && self.power_latched_ns.is_none() {
            self.power_latched_ns = Some(now_ns);
            return Some(drive_en(false, now_ns));
        }
        if self.driven_level != self.desired_level {
            self.driven_level = self.desired_level;
            return Some(drive(self.sda, self.desired_level, now_ns));
        }
        self.touch.poll(self.interrupt, now_ns)
    }

    fn state(&self) -> Option<State> {
        Some(
            State::new()
                .set("recognized_addresses", self.addressed)
                .set("write_bytes", self.data_bytes)
                .set("ready", self.touch.needs_read)
                .set("contact", self.touch.point.is_some())
                .set("reports", self.touch.reports)
                .set("acknowledged", self.touch.acknowledged)
                .set("rejected_inputs", self.touch.rejected)
                .set("status_reads", self.touch.status_reads)
                .set("coordinate_reads", self.touch.coordinate_reads)
                .set("hold_ms", self.touch.hold_ms)
                .set("drag_ms", self.touch.drag_ms)
                .set("refresh_acknowledged", self.touch.refresh_acknowledged)
                .set("power_latched", self.power_latched_ns.is_some())
                .set("power_latched_ns", self.power_latched_ns.unwrap_or(0))
                .set("chip_enabled", self.chip_enabled),
        )
    }
}

esp_part::export_part!(Bus, buffer = 1024);

#[cfg(test)]
mod tests {
    use super::*;

    fn write_expander(bus: &mut Bus, addr: u32, register: u8, value: u8) {
        let reply = bus.on_bus(&BusRequest {
            op: Some(bus_request::Op::I2c(I2cTransaction {
                addr,
                write: vec![register, value],
                ..Default::default()
            })),
            ..Default::default()
        }).unwrap();
        assert!(reply.ack);
    }

    #[test]
    fn shutdown_requires_the_power_expander_to_drive_p4_high() {
        let mut config = PartConfig::default();
        config.pins.extend([("SDA".into(), 31), ("SCL".into(), 32), ("INT".into(), 23)]);
        config.en_pins.push("POWER_ENABLE".into());
        let mut bus = Bus::default();
        bus.configure(&config);
        assert_eq!(bus.poll(0), Some(drive(23, true, 0)));

        write_expander(&mut bus, 0x43, OUTPUT_STATE as u8, POWER_OFF);
        write_expander(&mut bus, 0x44, OUTPUT_STATE as u8, POWER_OFF);
        write_expander(&mut bus, 0x44, OUTPUT_DIRECTION as u8, POWER_OFF);
        assert!(bus.poll(1).is_none());
        write_expander(&mut bus, 0x44, OUTPUT_STATE as u8, 0);
        write_expander(&mut bus, 0x44, OUTPUT_HIGH_IMPEDANCE as u8, 0);
        assert!(bus.poll(2).is_none());

        write_expander(&mut bus, 0x44, OUTPUT_STATE as u8, POWER_OFF);
        let message = bus.poll(3).unwrap();
        assert_eq!(message, drive_en(false, 3));
        assert_eq!(bus.state().unwrap().get("chip_enabled"), Some("true"));
        bus.on_en(false, 3);
        assert_eq!(bus.state().unwrap().get("chip_enabled"), Some("false"));
        assert_eq!(bus.state().unwrap().get("power_latched_ns"), Some("3"));
        write_expander(&mut bus, 0x44, OUTPUT_STATE as u8, 0);
        assert!(bus.poll(4).is_none());
    }

    fn read_register(touch: &mut St7123, address: u16, read_len: u32) -> Vec<u8> {
        touch.transfer(&I2cTransaction {
            write: address.to_be_bytes().to_vec(),
            read_len,
            ..Default::default()
        })
    }

    #[test]
    fn unread_drag_move_releases_without_a_completion_receipt() {
        let mut touch = St7123::default();
        assert!(touch.start_contact("drag:0,1279:719,0").is_some());
        touch.poll(23, 0);
        read_register(&mut touch, FIRST_POINT, 7);
        touch.poll(23, 1);

        let move_at = DRAG_STEP_NS + 1;
        touch.poll(23, move_at);
        touch.poll(23, move_at + 1);
        assert!(touch.needs_read);
        assert_eq!(touch.reports, 2);
        assert_eq!(touch.acknowledged, 1);

        let expired = move_at + 1 + UNREAD_REPORT_TIMEOUT_NS;
        touch.poll(23, expired);
        assert_eq!(touch.irq_level, Some(true));
        touch.poll(23, expired + 1);
        assert_eq!(touch.irq_level, Some(false));
        assert_eq!(read_register(&mut touch, STATUS, 1), [0]);
        assert_eq!(touch.reports, 3);
        assert_eq!(touch.acknowledged, 2);
        assert_eq!(touch.drag_ms, 0);
        assert!(touch.start_contact("tap:4,5").is_some());
    }
}
