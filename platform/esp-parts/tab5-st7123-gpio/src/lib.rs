//! Tab5 GPIO31/32 I2C board-detection fixture for M5GFX.
//! Watches the master's SDA/SCL edges and supplies its input line levels.
//! Contacts, reset-pin electrical timing, and additional peripherals are outside this part.

use esp_part::prelude::*;

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

    fn configure(&mut self, config: &PartConfig) {
        self.sda = config.pins["SDA"];
        self.scl = config.pins["SCL"];
        self.desired_level = true;
        self.driven_level = true;
        self.chips = vec![
            Registers::new(0x43, 1, &[(1, 0xa2)]),
            Registers::new(0x44, 1, &[(1, 0xa2)]),
            Registers::new(0x55, 2, &[(0, 3)]),
        ];
    }

    fn claims(&self) -> Vec<Claim> {
        vec![
            drives(1 << self.sda),
            watches((1 << self.sda) | (1 << self.scl)),
        ]
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
        if self.driven_level == self.desired_level {
            return None;
        }
        self.driven_level = self.desired_level;
        Some(drive(self.sda, self.desired_level, now_ns))
    }

    fn state(&self) -> Option<State> {
        Some(
            State::new()
                .set("recognized_addresses", self.addressed)
                .set("write_bytes", self.data_bytes),
        )
    }
}

esp_part::export_part!(Bus, buffer = 1024);
