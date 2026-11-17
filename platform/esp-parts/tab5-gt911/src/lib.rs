//! Single-contact, early Tab5 GT911 report path through the real esp-emu I2C
//! controller and GPIO INT line. Coordinates are in the panel's raw orientation.
use esp_part::prelude::*;
use std::collections::VecDeque;

const ADDRESS: u32 = 0x14;
const WIDTH: u16 = 720;
const HEIGHT: u16 = 1280;
const PRODUCT_ID: u16 = 0x8140;
const REPORT_STATUS: u16 = 0x814e;
const FIRST_POINT: u16 = REPORT_STATUS + 1;
const READY: u8 = 0x80;
const SCAN_NS: u64 = 16_000_000;
const TAP_HOLD_NS: u64 = 180_000_000;
const MAX_PENDING: usize = 8;
const MAX_READ: u32 = 512;
// esp-emu v1.1.0 dispatches the entire claimed port to parts. Keep the
// existing Device Service register fixtures on that port while using GT911.
const BOARD_REGISTERS: &[(u32, &[(u8, u8)])] = &[
    (0x32, &[]),
    (
        0x41,
        &[(0xfe, 0x54), (0xff, 0x49), (0x02, 0x19), (0x04, 0xb0)],
    ),
    (0x43, &[(0x01, 0xa2)]),
    (0x44, &[(0x01, 0xa2)]),
    (0x68, &[(0x00, 0x24)]),
];

struct RegisterFile {
    pointer: u8,
    values: [u8; 256],
}

impl RegisterFile {
    fn new(initial_values: &[(u8, u8)]) -> Self {
        let mut values = [0; 256];
        for (address, value) in initial_values {
            values[*address as usize] = *value;
        }
        Self { pointer: 0, values }
    }

    fn transfer(&mut self, request: &I2cTransaction) -> Vec<u8> {
        if let Some((address, data)) = request.write.split_first() {
            self.pointer = *address;
            for value in data {
                self.values[self.pointer as usize] = *value;
                self.pointer = self.pointer.wrapping_add(1);
            }
        }
        (0..request.read_len)
            .map(|_| {
                let value = self.values[self.pointer as usize];
                self.pointer = self.pointer.wrapping_add(1);
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

enum Tap {
    AwaitingReport,
    ReleaseAt(u64),
}

#[derive(Default)]
struct Gt911 {
    scl: Option<u32>,
    sda: Option<u32>,
    interrupt: Option<u32>,
    irq_level: Option<bool>,
    pointer: u16,
    contact: Option<Point>,
    pending: VecDeque<Option<Point>>,
    latched_point: Option<Point>,
    ready: bool,
    next_scan: u64,
    produced: u32,
    acknowledged: u32,
    rejected_inputs: u32,
    board: Vec<(u32, RegisterFile)>,
    tap: Option<Tap>,
}

impl Gt911 {
    fn acknowledge(&mut self) {
        if self.ready {
            self.acknowledged = self.acknowledged.saturating_add(1);
        }
        self.ready = false;
        self.latched_point = None;
    }

    fn read_register(&self, address: u16) -> u8 {
        let width = WIDTH.to_le_bytes();
        let height = HEIGHT.to_le_bytes();
        match address {
            0x8048 => width[0],
            0x8049 => width[1],
            0x804a => height[0],
            0x804b => height[1],
            0x804c => 1, // Maximum modeled contacts.
            0x804d => 1, // Falling-edge interrupt mode.
            PRODUCT_ID..=0x8143 => b"911\0"[(address - PRODUCT_ID) as usize],
            REPORT_STATUS if self.ready => READY | u8::from(self.latched_point.is_some()),
            FIRST_POINT..=0x8156 if self.ready => {
                let Some(point) = self.latched_point else {
                    return 0;
                };
                let x = point.x.to_le_bytes();
                let y = point.y.to_le_bytes();
                let report = [0, x[0], x[1], y[0], y[1], 20, 0, 0];
                report[(address - FIRST_POINT) as usize]
            }
            _ => 0,
        }
    }

    fn parse_point(input: &str) -> Option<Point> {
        let (x, y) = input.split_once(',')?;
        let point = Point {
            x: x.parse().ok()?,
            y: y.parse().ok()?,
        };
        (point.x < WIDTH && point.y < HEIGHT).then_some(point)
    }

    fn next_contact(&self, input: &str) -> Option<Option<Point>> {
        if input == "up" {
            return self.contact.map(|_| None);
        }
        let (action, coordinates) = input.split_once(':')?;
        match (action, self.contact.is_some()) {
            ("down", false) | ("move", true) => Self::parse_point(coordinates).map(Some),
            _ => None,
        }
    }
}

impl Device for Gt911 {
    const NAME: &'static str = "gt911";
    const ON_BUS: bool = true;

    fn configure(&mut self, config: &PartConfig) {
        self.scl = config.pins.get("SCL").copied();
        self.sda = config.pins.get("SDA").copied();
        self.interrupt = config.pins.get("INT").copied().filter(|pin| *pin < 64);
        self.board = BOARD_REGISTERS
            .iter()
            .map(|(address, values)| (*address, RegisterFile::new(values)))
            .collect();
    }

    fn claims(&self) -> Vec<Claim> {
        let mut claims: Vec<_> = std::iter::once(ADDRESS)
            .chain(self.board.iter().map(|(addr, _)| *addr))
            .map(|addr| Claim {
                what: Some(claim::What::I2c(I2cClaim {
                    addr,
                    scl_pin: self.scl,
                    sda_pin: self.sda,
                })),
            })
            .collect();
        if let Some(pin) = self.interrupt {
            claims.push(drives(1_u64 << pin));
        }
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
        if let Some((_, registers)) = self.board.iter_mut().find(|(addr, _)| *addr == i2c.addr) {
            reply.data = registers.transfer(i2c);
            reply.ack = true;
            return Some(reply);
        }
        if i2c.addr != ADDRESS || i2c.write.len() == 1 {
            return Some(reply);
        }
        if let [hi, lo, rest @ ..] = i2c.write.as_slice() {
            self.pointer = u16::from_be_bytes([*hi, *lo]);
            for value in rest {
                if self.pointer == REPORT_STATUS && *value == 0 {
                    self.acknowledge();
                }
                self.pointer = self.pointer.wrapping_add(1);
            }
        }
        reply.data = (0..i2c.read_len)
            .map(|_| {
                let value = self.read_register(self.pointer);
                self.pointer = self.pointer.wrapping_add(1);
                value
            })
            .collect();
        reply.ack = true;
        Some(reply)
    }

    fn on_input(&mut self, input: &str) {
        if let Some(point) = input.strip_prefix("tap:").and_then(Self::parse_point) {
            if !self.ready && self.contact.is_none() && self.pending.is_empty() {
                self.contact = Some(point);
                self.pending.push_back(Some(point));
                self.tap = Some(Tap::AwaitingReport);
                return;
            }
        }
        if let Some(contact) = self
            .next_contact(input)
            .filter(|_| self.tap.is_none() && self.pending.len() < MAX_PENDING)
        {
            self.contact = contact;
            self.pending.push_back(contact);
        } else {
            self.rejected_inputs = self.rejected_inputs.saturating_add(1);
        }
    }

    fn poll(&mut self, now_ns: u64) -> Option<EmulatorMessage> {
        let pin = self.interrupt?;
        if matches!(self.tap, Some(Tap::ReleaseAt(deadline)) if now_ns >= deadline) {
            self.tap = None;
            self.contact = None;
            self.pending.push_back(None);
        }
        // Acknowledge releases the previous INT before another report may latch.
        if !self.ready && self.irq_level == Some(false) {
            self.irq_level = Some(true);
            return Some(drive(pin, true, now_ns));
        }
        if !self.ready && now_ns >= self.next_scan {
            if let Some(contact) = self.pending.pop_front().or_else(|| self.contact.map(Some)) {
                self.latched_point = contact;
                self.ready = true;
                self.produced = self.produced.saturating_add(1);
                self.next_scan = now_ns.saturating_add(SCAN_NS);
                if matches!(self.tap, Some(Tap::AwaitingReport)) {
                    self.tap = Some(Tap::ReleaseAt(now_ns.saturating_add(TAP_HOLD_NS)));
                }
            }
        }
        let level = !self.ready;
        if self.irq_level != Some(level) {
            self.irq_level = Some(level);
            return Some(drive(pin, level, now_ns));
        }
        None
    }

    fn state(&self) -> Option<State> {
        Some(
            State::new()
                .set("ready", self.ready)
                .set("contact", self.contact.is_some())
                .set("reports", self.produced)
                .set("acknowledged", self.acknowledged)
                .set("rejected_inputs", self.rejected_inputs),
        )
    }
}

esp_part::export_part!(Gt911, buffer = 1024);
