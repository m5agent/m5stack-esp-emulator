//! Shared Tab5 BMI270 I²C boot model. The guest writes configuration memory
//! through INIT_DATA; the model does not execute the uploaded sensor program.
use esp_part::prelude::*;
use sha2::{Digest, Sha256};

pub(super) const ADDRESS: u32 = 0x68;
const CONFIG_BYTES: usize = 8192;
const CHIP_ID: u8 = 0x00;
const INTERNAL_STATUS: u8 = 0x21;
const FEATURE_PAGE: u8 = 0x2f;
const FIRST_FEATURE: u8 = 0x30;
const LAST_FEATURE: u8 = 0x3f;
const INIT_CTRL: u8 = 0x59;
const INIT_ADDR_0: u8 = 0x5b;
const INIT_ADDR_1: u8 = 0x5c;
const INIT_DATA: u8 = 0x5e;
const POWER_CONF: u8 = 0x7c;
const COMMAND: u8 = 0x7e;
const SOFT_RESET: u8 = 0xb6;
const ADVANCED_POWER_SAVE: u8 = 1;

// BoschSensortec/BMI270_SensorAPI@41129fcfe39c583ee5462d79195741945d51c1fe
// bmi270.c, bmi270_config_file. The model needs only this digest, not the image.
const STANDARD_CONFIG_SHA256: [u8; 32] = [
    0x2d, 0x75, 0xe6, 0x8e, 0x34, 0x3a, 0x13, 0xff, 0x99, 0xbe, 0x98, 0x26, 0x1d, 0xfb, 0xd9, 0x9d,
    0x9e, 0x8c, 0x6f, 0x26, 0x7d, 0xa9, 0xe3, 0xc5, 0xae, 0xb8, 0x83, 0x27, 0x6a, 0xd1, 0x78, 0xdb,
];

#[derive(Clone, Copy, PartialEq, Eq)]
enum InitStatus {
    NotInitialized = 0,
    Initialized = 1,
    Error = 2,
}

pub(super) struct Bmi270 {
    pointer: u8,
    registers: [u8; 256],
    config: [u8; CONFIG_BYTES],
    written_words: [bool; CONFIG_BYTES / 2],
    config_read_offset: usize,
    features: [[u8; 16]; 8],
    status: InitStatus,
    status_reads: u32,
}

impl Default for Bmi270 {
    fn default() -> Self {
        let mut registers = [0; 256];
        registers[CHIP_ID as usize] = 0x24;
        registers[POWER_CONF as usize] = 0x03;
        Self {
            pointer: 0,
            registers,
            config: [0; CONFIG_BYTES],
            written_words: [false; CONFIG_BYTES / 2],
            config_read_offset: 0,
            features: [[0; 16]; 8],
            status: InitStatus::NotInitialized,
            status_reads: 0,
        }
    }
}

impl Bmi270 {
    fn config_offset(&self) -> usize {
        let low = usize::from(self.registers[INIT_ADDR_0 as usize]);
        let high = usize::from(self.registers[INIT_ADDR_1 as usize]);
        ((high << 4) | low) * 2
    }

    fn write_config(&mut self, values: &[u8]) -> bool {
        let offset = self.config_offset();
        let end = offset + values.len();
        if self.status != InitStatus::NotInitialized
            || self.registers[POWER_CONF as usize] & ADVANCED_POWER_SAVE != 0
            || end > CONFIG_BYTES
            || values.len() % 2 != 0
        {
            return false;
        }
        self.config[offset..end].copy_from_slice(values);
        self.written_words[offset / 2..end / 2].fill(true);
        true
    }

    fn valid_config(&self, expected_sha256: &[u8; 32]) -> bool {
        self.written_words.iter().all(|written| *written)
            && Sha256::digest(&self.config[..]).as_slice() == expected_sha256
    }

    fn feature_index(&self, address: u8) -> (usize, usize) {
        let page = usize::from(self.registers[FEATURE_PAGE as usize]);
        (page, usize::from(address - FIRST_FEATURE))
    }

    fn write_register(&mut self, address: u8, value: u8) {
        match address {
            CHIP_ID | INTERNAL_STATUS | INIT_DATA => {}
            INIT_CTRL if self.status == InitStatus::NotInitialized => {
                self.registers[address as usize] = value & 1;
                if value & 1 == 0 {
                    self.written_words.fill(false);
                } else {
                    self.status = if self.valid_config(&STANDARD_CONFIG_SHA256) {
                        InitStatus::Initialized
                    } else {
                        InitStatus::Error
                    };
                }
            }
            // Loading completes once per power-on or soft reset.
            INIT_CTRL => {}
            INIT_ADDR_0 => self.registers[address as usize] = value & 0x0f,
            FEATURE_PAGE => self.registers[address as usize] = value & 0x07,
            FIRST_FEATURE..=LAST_FEATURE => {
                let (page, byte) = self.feature_index(address);
                self.features[page][byte] = value;
            }
            COMMAND => {
                if value == SOFT_RESET {
                    *self = Self::default();
                }
            }
            _ => self.registers[address as usize] = value,
        }
    }

    fn read_register(&mut self, address: u8) -> u8 {
        match address {
            INTERNAL_STATUS => {
                self.status_reads = self.status_reads.saturating_add(1);
                self.status as u8
            }
            FIRST_FEATURE..=LAST_FEATURE => {
                let (page, byte) = self.feature_index(address);
                self.features[page][byte]
            }
            _ => self.registers[address as usize],
        }
    }

    pub(super) fn transfer(&mut self, request: &I2cTransaction) -> Option<Vec<u8>> {
        if let Some((&address, values)) = request.write.split_first() {
            self.pointer = address;
            if address == INIT_DATA {
                if !values.is_empty() && !self.write_config(values) {
                    return None;
                }
            } else {
                if values.len() > self.registers.len() {
                    return None;
                }
                for &value in values {
                    let register = self.pointer;
                    self.write_register(register, value);
                    self.pointer = register.wrapping_add(1);
                }
            }
            if self.pointer == INIT_DATA {
                self.config_read_offset = self.config_offset();
            }
        }
        if self.pointer == INIT_DATA {
            let end = self.config_read_offset + request.read_len as usize;
            let result = self.config.get(self.config_read_offset..end)?.to_vec();
            self.config_read_offset = if request.continues {
                end
            } else {
                self.config_offset()
            };
            return Some(result);
        }
        Some(
            (0..request.read_len)
                .map(|_| {
                    let value = self.read_register(self.pointer);
                    self.pointer = self.pointer.wrapping_add(1);
                    value
                })
                .collect(),
        )
    }

    pub(super) fn observe(&self, state: State) -> State {
        state
            .set("bmi270_init_status", self.status as u8)
            .set("bmi270_status_reads", self.status_reads)
            .set(
                "bmi270_config_bytes",
                self.written_words
                    .iter()
                    .filter(|&&written| written)
                    .count()
                    * 2,
            )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn bus(imu: &mut Bmi270, write: &[u8], read_len: u32, continues: bool) -> Option<Vec<u8>> {
        imu.transfer(&I2cTransaction {
            addr: ADDRESS,
            write: write.to_vec(),
            read_len,
            continues,
            ..Default::default()
        })
    }

    fn write(imu: &mut Bmi270, values: &[u8]) {
        assert_eq!(bus(imu, values, 0, false), Some(vec![]));
    }

    fn read(imu: &mut Bmi270, register: u8) -> u8 {
        bus(imu, &[register], 1, false).unwrap()[0]
    }

    #[test]
    fn long_writes_target_word_addressed_memory_and_keep_normal_registers() {
        let mut imu = Bmi270::default();
        assert_eq!(super::super::part_buffer_len(), 16384);
        assert_eq!(read(&mut imu, POWER_CONF), 0x03);
        assert_eq!(bus(&mut imu, &[INIT_DATA, 1, 2], 0, false), None);
        write(&mut imu, &[POWER_CONF, 0]);
        write(&mut imu, &[0x40, 0xa8]);
        write(&mut imu, &[INIT_ADDR_0, 0xf1, 0x01]); // 0x011 words = 34 bytes.
        assert_eq!(read(&mut imu, INIT_ADDR_0), 1);
        write(&mut imu, &[INIT_DATA, 1, 2, 3, 4]);
        assert_eq!(bus(&mut imu, &[INIT_DATA], 3, true), Some(vec![1, 2, 3]));
        assert_eq!(bus(&mut imu, &[], 2, false), Some(vec![4, 0]));
        assert_eq!(
            bus(&mut imu, &[INIT_DATA], 4, false),
            Some(vec![1, 2, 3, 4])
        );
        assert_eq!(&imu.config[34..38], &[1, 2, 3, 4]);
        assert_eq!(bus(&mut imu, &[INIT_DATA, 1], 0, false), None);
        write(&mut imu, &[INIT_ADDR_0, 0x0f, 0xff]);
        assert_eq!(bus(&mut imu, &[INIT_DATA, 1, 2, 3, 4], 0, false), None);
        assert_eq!(read(&mut imu, 0x40), 0xa8);
        assert_eq!(read(&mut imu, CHIP_ID), 0x24);
    }

    #[test]
    fn full_config_requires_coverage_and_content_then_protects_read_only_status() {
        let mut imu = Bmi270::default();
        write(&mut imu, &[POWER_CONF, 0]);
        let synthetic = [0x46; CONFIG_BYTES];
        let synthetic_sha: [u8; 32] = Sha256::digest(synthetic).into();
        write(&mut imu, &[INIT_ADDR_0, 0, 0x80]);
        write(
            &mut imu,
            &[&[INIT_DATA], &synthetic[CONFIG_BYTES / 2..]].concat(),
        );
        assert!(!imu.valid_config(&synthetic_sha));
        write(&mut imu, &[INIT_ADDR_0, 0, 0]);
        write(
            &mut imu,
            &[&[INIT_DATA], &synthetic[..CONFIG_BYTES / 2]].concat(),
        );
        assert!(imu.valid_config(&synthetic_sha));
        assert!(!imu.valid_config(&STANDARD_CONFIG_SHA256));
        assert_eq!(
            read(&mut imu, INTERNAL_STATUS),
            InitStatus::NotInitialized as u8
        );
        write(&mut imu, &[INTERNAL_STATUS, 1]);
        assert_eq!(
            read(&mut imu, INTERNAL_STATUS),
            InitStatus::NotInitialized as u8
        );
        write(&mut imu, &[INIT_CTRL, 1]);
        assert_eq!(read(&mut imu, INTERNAL_STATUS), InitStatus::Error as u8);
        write(&mut imu, &[INIT_CTRL, 0]);
        assert_eq!(read(&mut imu, INTERNAL_STATUS), InitStatus::Error as u8);
        assert_eq!(bus(&mut imu, &[INIT_DATA, 1, 2], 0, false), None);
        write(&mut imu, &[COMMAND, SOFT_RESET]);
        assert_eq!(
            read(&mut imu, INTERNAL_STATUS),
            InitStatus::NotInitialized as u8
        );
        assert_eq!(read(&mut imu, POWER_CONF), 0x03);
    }

    #[test]
    fn incomplete_load_errors_and_feature_pages_keep_independent_register_values() {
        let mut imu = Bmi270::default();
        write(&mut imu, &[POWER_CONF, 0]);
        write(&mut imu, &[INIT_DATA, 1, 2]);
        write(&mut imu, &[INIT_CTRL, 0]);
        assert!(!imu.written_words[0]);
        write(&mut imu, &[INIT_CTRL, 1]);
        assert_eq!(read(&mut imu, INTERNAL_STATUS), InitStatus::Error as u8);
        write(&mut imu, &[FEATURE_PAGE, 0x85]);
        assert_eq!(read(&mut imu, FEATURE_PAGE), 5);
        write(&mut imu, &[FIRST_FEATURE, 0xcd, 0xef]);
        write(&mut imu, &[FEATURE_PAGE, 0]);
        assert_eq!(read(&mut imu, FIRST_FEATURE), 0);
        write(&mut imu, &[FEATURE_PAGE, 5]);
        assert_eq!(
            bus(&mut imu, &[FIRST_FEATURE], 2, false),
            Some(vec![0xcd, 0xef])
        );
        write(&mut imu, &[COMMAND, SOFT_RESET]);
        write(&mut imu, &[FEATURE_PAGE, 5]);
        assert_eq!(read(&mut imu, FIRST_FEATURE), 0);
    }
}
