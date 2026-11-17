//! Tab5 software-I²C board detection and native ST7123 HP I²C touch reports.

use esp_part::prelude::*;

const TOUCH_ADDRESS: u32 = 0x55;
const WIDTH: u16 = 720;
const HEIGHT: u16 = 1280;
const TOUCH_COUNT: u16 = 0x0009;
const STATUS: u16 = 0x0010;
const FIRST_POINT: u16 = 0x0014;
const POINT_END: u16 = FIRST_POINT + 7;
const HOLD_NS: u64 = 180_000_000;
const UNREAD_REPORT_TIMEOUT_NS: u64 = 1_000_000_000;
const MAX_READ: u32 = 512;

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

#[derive(Clone, Copy)]
struct Point {
    x: u16,
    y: u16,
}

#[derive(Default)]
struct St7123 {
    pointer: u16,
    point: Option<Point>,
    irq_level: Option<bool>,
    press_at: Option<u64>,
    pending_at: Option<u64>,
    needs_read: bool,
    reports: u32,
    acknowledged: u32,
    rejected: u32,
    status_reads: u32,
    coordinate_reads: u32,
}

impl St7123 {
    fn tap(&mut self, input: &str) -> Option<()> {
        if self.point.is_some() || self.needs_read {
            return None;
        }
        let (x, y) = input.strip_prefix("tap:")?.split_once(',')?;
        let point = Point {
            x: x.parse().ok()?,
            y: y.parse().ok()?,
        };
        if point.x >= WIDTH || point.y >= HEIGHT {
            return None;
        }
        self.point = Some(point);
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
            self.acknowledged = self.acknowledged.saturating_add(1);
        }
        data
    }

    fn poll(&mut self, pin: u32, now_ns: u64) -> Option<EmulatorMessage> {
        // A paused or stopped polling driver must not strand a physical contact.
        // Missing reports stay unacknowledged so the API still fails that input.
        if self.needs_read {
            let pending_at = *self.pending_at.get_or_insert(now_ns);
            if now_ns.saturating_sub(pending_at) >= UNREAD_REPORT_TIMEOUT_NS {
                self.pending_at = None;
                if self.point.is_some() {
                    self.release();
                } else {
                    self.needs_read = false;
                }
            }
        }
        if self.point.is_some() && !self.needs_read {
            let pressed_at = *self.press_at.get_or_insert(now_ns);
            if now_ns.saturating_sub(pressed_at) >= HOLD_NS {
                self.release();
            }
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
        self.press_at = None;
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

    fn configure(&mut self, config: &PartConfig) {
        self.sda = config.pins["SDA"];
        self.scl = config.pins["SCL"];
        self.interrupt = config.pins["INT"];
        self.desired_level = true;
        self.driven_level = true;
        self.chips = vec![
            Registers::new(0x43, 1, &[(1, 0xa2)]),
            Registers::new(0x44, 1, &[(1, 0xa2)]),
            Registers::new(0x55, 2, &[(0, 3)]),
        ];
        self.hardware_chips = HARDWARE_REGISTERS
            .iter()
            .map(|(addr, seed)| Registers::new(*addr, 1, seed))
            .collect();
    }

    fn claims(&self) -> Vec<Claim> {
        let mut claims = vec![
            drives((1 << self.sda) | (1 << self.interrupt)),
            watches((1 << self.sda) | (1 << self.scl)),
        ];
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
            chip.transfer(i2c)
        } else {
            return Some(reply);
        };
        reply.ack = true;
        Some(reply)
    }

    fn on_input(&mut self, input: &str) {
        if self.touch.tap(input).is_none() {
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

    fn poll(&mut self, now_ns: u64) -> Option<EmulatorMessage> {
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
                .set("coordinate_reads", self.touch.coordinate_reads),
        )
    }
}

esp_part::export_part!(Bus, buffer = 1024);
