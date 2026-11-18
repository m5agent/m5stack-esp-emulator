//! Bounded I²C control-port state. I²S signal and analog paths belong to
//! separate hardware/backend models.
use super::Gt911;
use esp_part::prelude::*;

const SPEAKER: u32 = 0x10;
const MICROPHONE: u32 = 0x40;

// Everest ES8388 rev 1.0 §6 and ES7210 rev 21.0 §7 reset values,
// limited to the control registers used by ESP Codec Dev v1.3.4.
// The three DLL controls are written by the vendor driver and have no
// documented reset value in the ES8388 register table.
const SPEAKER_RESET: &[(u8, u8)] = &[
    (0x00, 0x06),
    (0x01, 0x1c),
    (0x02, 0xc3),
    (0x03, 0xfc),
    (0x04, 0xc0),
    (0x05, 0x00),
    (0x06, 0x00),
    (0x07, 0x7c),
    (0x08, 0x80),
    (0x09, 0x00),
    (0x0a, 0x00),
    (0x0b, 0x06),
    (0x0c, 0x00),
    (0x0d, 0x06),
    (0x0e, 0x30),
    (0x0f, 0x30),
    (0x10, 0xc0),
    (0x11, 0xc0),
    (0x12, 0x38),
    (0x13, 0xb0),
    (0x14, 0x32),
    (0x15, 0x06),
    (0x16, 0x00),
    (0x17, 0x00),
    (0x18, 0x06),
    (0x19, 0x32),
    (0x1a, 0xc0),
    (0x1b, 0xc0),
    (0x1c, 0x08),
    (0x1d, 0x06),
    (0x1e, 0x1f),
    (0x1f, 0xf7),
    (0x20, 0xfd),
    (0x21, 0xff),
    (0x22, 0x1f),
    (0x23, 0xf7),
    (0x24, 0xfd),
    (0x25, 0xff),
    (0x26, 0x00),
    (0x27, 0x38),
    (0x28, 0x38),
    (0x29, 0x38),
    (0x2a, 0x38),
    (0x2b, 0x38),
    (0x2c, 0x38),
    (0x2d, 0x00),
    (0x2e, 0x00),
    (0x2f, 0x00),
    (0x30, 0x00),
    (0x31, 0x00),
    (0x32, 0x00),
    (0x33, 0x00),
    (0x34, 0x00),
];
const MICROPHONE_RESET: &[(u8, u8)] = &[
    (0x00, 0x32),
    (0x01, 0x20),
    (0x02, 0x02),
    (0x03, 0x04),
    (0x04, 0x01),
    (0x05, 0x00),
    (0x06, 0x00),
    (0x07, 0x20),
    (0x08, 0x10),
    (0x09, 0x40),
    (0x0a, 0x40),
    (0x11, 0x00),
    (0x12, 0x00),
    (0x13, 0x00),
    (0x14, 0x00),
    (0x20, 0x26),
    (0x21, 0x26),
    (0x22, 0x06),
    (0x23, 0x26),
    (0x3d, 0x72),
    (0x3e, 0x10),
    (0x3f, 0x00),
    (0x40, 0x80),
    (0x41, 0x71),
    (0x42, 0x71),
    (0x43, 0x00),
    (0x44, 0x00),
    (0x45, 0x00),
    (0x46, 0x00),
    (0x47, 0x00),
    (0x48, 0x00),
    (0x49, 0x00),
    (0x4a, 0x00),
    (0x4b, 0xff),
    (0x4c, 0xff),
];

struct Codec {
    pointer: u8,
    values: [Option<u8>; 0x4d],
    defaults: &'static [(u8, u8)],
    reset_bit: u8,
    private_registers: &'static [u8],
    readonly: &'static [u8],
    writes: u32,
    reads: u32,
}

impl Codec {
    fn new(
        defaults: &'static [(u8, u8)],
        reset_bit: u8,
        private_registers: &'static [u8],
        readonly: &'static [u8],
    ) -> Self {
        let mut model = Self {
            pointer: 0,
            values: [None; 0x4d],
            defaults,
            reset_bit,
            private_registers,
            readonly,
            writes: 0,
            reads: 0,
        };
        model.reset();
        model
    }

    fn reset(&mut self) {
        self.values.fill(None);
        for &(reg, value) in self.defaults {
            self.values[usize::from(reg)] = Some(value);
        }
    }

    fn supports_write(&self, reg: u8) -> bool {
        !self.readonly.contains(&reg)
            && (self.defaults.iter().any(|&(address, _)| address == reg)
                || self.private_registers.contains(&reg))
    }

    fn transfer(&mut self, request: &I2cTransaction) -> Option<Vec<u8>> {
        let (address, writes) = request
            .write
            .split_first()
            .map_or((self.pointer, &[][..]), |(address, data)| (*address, data));
        let start = usize::from(address);
        let next = start.checked_add(writes.len())?;
        let end = next.checked_add(request.read_len as usize)?;
        if end > self.values.len() || !(start..next).all(|reg| self.supports_write(reg as u8)) {
            return None;
        }
        // Validate and commit after all addressed registers have been checked.
        let mut result = self.values;
        for (reg, &value) in (start..next).zip(writes) {
            if reg == 0 && value & self.reset_bit != 0 {
                result.fill(None);
                for &(reset_register, reset_value) in self.defaults {
                    result[usize::from(reset_register)] = Some(reset_value);
                }
            }
            result[reg] = Some(value);
        }
        let readback: Option<Vec<u8>> = result[next..end].iter().copied().collect();
        let readback = readback?;
        self.pointer = end as u8;
        self.values = result;
        self.writes = self.writes.saturating_add(writes.len() as u32);
        self.reads = self.reads.saturating_add(request.read_len);
        Some(readback)
    }
}

struct Codecs {
    speaker: Codec,
    microphone: Codec,
}

impl Default for Codecs {
    fn default() -> Self {
        Self {
            speaker: Codec::new(SPEAKER_RESET, 0x80, &[0x35, 0x37, 0x39], &[]),
            microphone: Codec::new(MICROPHONE_RESET, 0x04, &[], &[0x3d, 0x3e, 0x3f]),
        }
    }
}

impl Codecs {
    fn transfer(&mut self, request: &I2cTransaction) -> Option<Vec<u8>> {
        match request.addr {
            SPEAKER => self.speaker.transfer(request),
            MICROPHONE => self.microphone.transfer(request),
            _ => None,
        }
    }

    fn counts(&self) -> (u32, u32, u32, u32) {
        (
            self.speaker.writes,
            self.speaker.reads,
            self.microphone.writes,
            self.microphone.reads,
        )
    }
}

/// The same GT911 board and two codec control ports on its native I²C wires.
#[derive(Default)]
pub struct Gt911WithCodecs {
    board: Gt911,
    codecs: Codecs,
}

impl Device for Gt911WithCodecs {
    const NAME: &'static str = Gt911::NAME;
    const ON_BUS: bool = true;

    fn configure(&mut self, config: &PartConfig) {
        self.board.configure(config);
    }

    fn claims(&self) -> Vec<Claim> {
        let mut claims = self.board.claims();
        claims.extend([SPEAKER, MICROPHONE].into_iter().map(|addr| Claim {
            what: Some(claim::What::I2c(I2cClaim {
                addr,
                scl_pin: self.board.scl,
                sda_pin: self.board.sda,
            })),
        }));
        claims
    }

    fn on_bus(&mut self, request: &BusRequest) -> Option<BusReply> {
        if let Some(bus_request::Op::I2c(i2c)) = &request.op {
            if matches!(i2c.addr, SPEAKER | MICROPHONE) {
                let data = self.codecs.transfer(i2c);
                return Some(BusReply {
                    correlation_id: request.correlation_id,
                    op: BusOp::I2c as i32,
                    ack: data.is_some(),
                    data: data.unwrap_or_default(),
                    ..Default::default()
                });
            }
        }
        self.board.on_bus(request)
    }

    fn on_input(&mut self, input: &str) {
        self.board.on_input(input);
    }

    fn poll(&mut self, now_ns: u64) -> Option<EmulatorMessage> {
        self.board.poll(now_ns)
    }

    fn state(&self) -> Option<State> {
        let (speaker_writes, speaker_reads, microphone_writes, microphone_reads) =
            self.codecs.counts();
        Some(
            self.board
                .state()
                .unwrap_or_default()
                .set("speaker_control_writes", speaker_writes)
                .set("speaker_control_reads", speaker_reads)
                .set("microphone_control_writes", microphone_writes)
                .set("microphone_control_reads", microphone_reads),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn transaction(addr: u32, write: &[u8], read_len: u32) -> I2cTransaction {
        I2cTransaction {
            addr,
            write: write.to_vec(),
            read_len,
            ..Default::default()
        }
    }

    #[test]
    fn control_port_writes_and_readback_are_independent() {
        let mut model = Codecs::default();
        assert_eq!(
            model.transfer(&transaction(SPEAKER, &[0x19, 0x04], 0)),
            Some(vec![])
        );
        assert_eq!(
            model.transfer(&transaction(SPEAKER, &[0x19], 1)),
            Some(vec![0x04])
        );
        assert_eq!(
            model.transfer(&transaction(MICROPHONE, &[0x3d], 2)),
            Some(vec![0x72, 0x10])
        );
        assert_eq!(
            model.transfer(&transaction(MICROPHONE, &[0x3d, 0x00], 0)),
            None
        );
        assert_eq!(
            model.transfer(&transaction(SPEAKER, &[0x00, 0x80], 0)),
            Some(vec![])
        );
        assert_eq!(
            model.transfer(&transaction(SPEAKER, &[0x19], 1)),
            Some(vec![0x32])
        );
        assert_eq!(
            model.transfer(&transaction(SPEAKER, &[0xff, 0x11], 0)),
            None
        );
    }

    #[test]
    fn tab5_idf_speaker_initialization_uses_only_supported_registers() {
        // Ordered bytes from the SDK rebuild's successful HP-I2C0 A/B lane.
        let writes = [
            (0x19, 0x04),
            (0x01, 0x50),
            (0x02, 0x00),
            (0x35, 0xa0),
            (0x37, 0xd0),
            (0x39, 0xd0),
            (0x08, 0x00),
            (0x04, 0xc0),
            (0x00, 0x12),
            (0x17, 0x18),
            (0x18, 0x02),
            (0x26, 0x00),
            (0x27, 0x90),
            (0x2a, 0x90),
            (0x2b, 0x80),
            (0x2d, 0x00),
            (0x1b, 0x00),
            (0x1a, 0x00),
            (0x2e, 0x1e),
            (0x2f, 0x1e),
            (0x30, 0x00),
            (0x31, 0x00),
            (0x04, 0x3c),
            (0x03, 0xff),
            (0x09, 0xbb),
            (0x0a, 0x00),
            (0x0b, 0x02),
            (0x0c, 0x0c),
            (0x0d, 0x02),
            (0x10, 0x00),
            (0x11, 0x00),
            (0x03, 0x09),
        ];
        let mut model = Codecs::default();
        assert_eq!(model.transfer(&transaction(SPEAKER, &[0x35], 1)), None);
        for (register, value) in writes {
            assert_eq!(
                model.transfer(&transaction(SPEAKER, &[register, value], 0)),
                Some(vec![])
            );
        }
        assert_eq!(model.counts(), (32, 0, 0, 0));
        assert_eq!(
            model.transfer(&transaction(SPEAKER, &[0x03], 2)),
            Some(vec![0x09, 0x3c])
        );
        assert_eq!(
            model.transfer(&transaction(SPEAKER, &[0x35], 1)),
            Some(vec![0xa0])
        );
    }

    #[test]
    fn unknown_or_readonly_registers_reject_without_changing_either_codec() {
        let mut model = Codecs::default();
        assert_eq!(
            model.transfer(&transaction(MICROPHONE, &[0x3c, 0xab, 0xcd], 0)),
            None
        );
        assert_eq!(
            model.transfer(&transaction(SPEAKER, &[0x34, 0x77, 0x88, 0x99], 0)),
            None
        );
        assert_eq!(
            model.transfer(&transaction(SPEAKER, &[0x34], 1)),
            Some(vec![0x00])
        );
        assert_eq!(
            model.transfer(&transaction(MICROPHONE, &[0x43, 0x6a], 0)),
            Some(vec![])
        );
        assert_eq!(
            model.transfer(&transaction(MICROPHONE, &[0x00, 0x04], 0)),
            Some(vec![])
        );
        assert_eq!(
            model.transfer(&transaction(MICROPHONE, &[0x43], 1)),
            Some(vec![0x00])
        );
        assert_eq!(model.counts(), (0, 1, 2, 1));
    }

    #[test]
    fn feature_composes_the_two_codec_addresses_on_existing_gt911_pins() {
        let mut board = Gt911::default();
        let mut with_codecs = Gt911WithCodecs::default();
        let mut config = PartConfig::default();
        config.pins.insert("SDA".into(), 31);
        config.pins.insert("SCL".into(), 32);
        config.pins.insert("INT".into(), 23);
        board.configure(&config);
        with_codecs.configure(&config);
        let claims = with_codecs.claims();
        let old_claims = board.claims();
        assert_eq!(claims[..old_claims.len()], old_claims);
        for (claim, address) in claims[old_claims.len()..].iter().zip([SPEAKER, MICROPHONE]) {
            let Some(claim::What::I2c(i2c)) = &claim.what else {
                panic!("codec must have an I2C claim");
            };
            assert_eq!(
                (i2c.addr, i2c.scl_pin, i2c.sda_pin),
                (address, Some(32), Some(31))
            );
        }
        for (address, transfer, length) in [
            (0x14, &[0x81, 0x40][..], 4),
            (SPEAKER, &[0x19, 0x04][..], 0),
            (0x77, &[][..], 0),
        ] {
            let request = BusRequest {
                correlation_id: 42,
                op: Some(bus_request::Op::I2c(transaction(address, transfer, length))),
                ..Default::default()
            };
            let reply = with_codecs.on_bus(&request).unwrap();
            if address == SPEAKER {
                assert!(reply.ack);
                assert_eq!(reply.correlation_id, 42);
            } else {
                assert_eq!(reply, board.on_bus(&request).unwrap());
            }
        }
        assert_eq!(
            with_codecs.state().unwrap().get("speaker_control_writes"),
            Some("1")
        );
    }
}
