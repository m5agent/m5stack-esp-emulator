/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
/*!
  @file unit_AW3641E.cpp
  @brief AW3641E Unit for M5UnitUnified
*/
#include "unit_AW3641E.hpp"
#include <M5Utility.hpp>

#if defined(ARDUINO_ARCH_ESP32) || defined(ESP_PLATFORM)
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#endif

using namespace m5::utility::mmh3;
using namespace m5::unit::types;
using namespace m5::unit::aw3641e;

namespace {

// Scoped critical section guard for the pulse train (ESP32/FreeRTOS only).
// Uses a spinlock so nested critical sections and SMP cores are handled correctly,
// and prior interrupt state is preserved on exit.
// Keeps T_HI/T_LO jitter under the 10 us upper bound even across task switches.
class InterruptGuard {
public:
    InterruptGuard()
    {
#if defined(ARDUINO_ARCH_ESP32) || defined(ESP_PLATFORM)
        portENTER_CRITICAL(&_mux);
#endif
    }
    ~InterruptGuard()
    {
#if defined(ARDUINO_ARCH_ESP32) || defined(ESP_PLATFORM)
        portEXIT_CRITICAL(&_mux);
#endif
    }

    InterruptGuard(const InterruptGuard&) = delete;
    InterruptGuard& operator=(const InterruptGuard&) = delete;

private:
#if defined(ARDUINO_ARCH_ESP32) || defined(ESP_PLATFORM)
    portMUX_TYPE _mux = portMUX_INITIALIZER_UNLOCKED;
#endif
};

}  // namespace

namespace m5 {
namespace unit {

// class UnitAW3641E
const char UnitAW3641E::name[] = "UnitAW3641E";
const types::uid_t UnitAW3641E::uid{"UnitAW3641E"_mmh3};
const types::attr_t UnitAW3641E::attr{attribute::AccessGPIO};

bool UnitAW3641E::begin()
{
    auto ad{adapter()};
    if (!ad || ad->type() != Adapter::Type::GPIO) {
        M5_LIB_LOGE("FlashLight requires GPIO adapter");
        return false;
    }

    // The Grove yellow wire is mapped to the TX pin on M5Stack ports;
    // AW3641E EN pin is driven by TX.
    if (!pinModeTX(gpio::Mode::Output)) {
        M5_LIB_LOGE("Failed to set TX pin mode");
        return false;
    }
    if (!writeDigitalTX(false)) {
        M5_LIB_LOGE("Failed to drive TX low");
        return false;
    }

    _active      = false;
    _start_ms    = 0;
    _duration_ms = 0;
    return true;
}

void UnitAW3641E::update(const bool /*force*/)
{
    if (!_active) {
        return;
    }
    const uint32_t now{m5::utility::millis()};
    if (static_cast<uint32_t>(now - _start_ms) >= _duration_ms) {
        if (writeDigitalTX(false)) {
            _active = false;
        }
    }
}

bool UnitAW3641E::stop()
{
    if (!writeDigitalTX(false)) {
        return false;
    }
    _active = false;
    return true;
}

bool UnitAW3641E::flash(const aw3641e::Brightness brightness, const uint16_t duration_ms)
{
    if (_cfg.switch_position != aw3641e::SwitchPosition::Flash) {
        M5_LIB_LOGE("flash() requires switch_position == Flash, but it is configured as Torch");
        return false;
    }
    if (duration_ms == 0) {
        M5_LIB_LOGW("flash duration_ms == 0; ignored");
        return false;
    }

    // Clamp to Flash-mode safe limit.
    uint16_t effective_ms{duration_ms};
    if (effective_ms > aw3641e::FLASH_MAX_DURATION_MS) {
        M5_LIB_LOGW("flash duration_ms %u exceeds max %u, clamping (use torch() for longer on-time)",
                    static_cast<unsigned>(duration_ms), static_cast<unsigned>(aw3641e::FLASH_MAX_DURATION_MS));
        effective_ms = aw3641e::FLASH_MAX_DURATION_MS;
    }

    // Cancel any in-flight flash/torch before starting a new one.
    // send_pulse_train() also drives EN LOW + waits T_OFF (>500 us) at its start,
    // satisfying the chip's latch-reset requirement automatically.
    _active = false;

    const uint8_t n{to_pulse_count(brightness)};
    if (!send_pulse_train(n)) {
        return false;
    }
    // EN is held HIGH after the pulse train; update() drives EN LOW after duration_ms.
    _duration_ms = effective_ms;
    _start_ms    = m5::utility::millis();
    _active      = true;
    return true;
}

bool UnitAW3641E::torch(const uint16_t duration_ms)
{
    if (_cfg.switch_position != aw3641e::SwitchPosition::Torch) {
        M5_LIB_LOGE("torch() requires switch_position == Torch, but it is configured as Flash");
        return false;
    }
    if (duration_ms == 0) {
        M5_LIB_LOGW("torch duration_ms == 0; ignored");
        return false;
    }

    // Library-side safety cap.
    uint16_t effective_ms{duration_ms};
    if (effective_ms > aw3641e::TORCH_MAX_DURATION_MS) {
        M5_LIB_LOGW("torch duration_ms %u exceeds safety cap %u, clamping", static_cast<unsigned>(duration_ms),
                    static_cast<unsigned>(aw3641e::TORCH_MAX_DURATION_MS));
        effective_ms = aw3641e::TORCH_MAX_DURATION_MS;
    }

    // Cancel any in-flight operation by toggling EN low briefly, then high.
    _active = false;
    if (!writeDigitalTX(false)) {
        return false;
    }
    m5::utility::delayMicroseconds(PULSE_OFF_US);
    if (!writeDigitalTX(true)) {
        return false;
    }

    _duration_ms = effective_ms;
    _start_ms    = m5::utility::millis();
    _active      = true;
    return true;
}

bool UnitAW3641E::send_pulse_train(const uint8_t pulse_count)
{
    // 1. Drive EN low for T_OFF (> 500 us) to reset any pending latch.
    if (!writeDigitalTX(false)) {
        return false;
    }
    m5::utility::delayMicroseconds(PULSE_OFF_US);

    // 2. Send the rising-edge pulse train with interrupts disabled.
    //    Final state is EN = HIGH, which latches the setting and triggers the flash.
    //    Keep writing across a failure so pulse timing stays intact; report at the end.
    bool ok{true};
    {
        // cppcheck-suppress unusedVariable
        InterruptGuard guard;
        for (uint8_t i = 0; i < pulse_count; ++i) {
            ok = writeDigitalTX(false) && ok;
            m5::utility::delayMicroseconds(PULSE_LOW_US);
            ok = writeDigitalTX(true) && ok;
            m5::utility::delayMicroseconds(PULSE_HIGH_US);
        }
    }
    if (!ok) {
        // Drop EN LOW so we do not leave the chip latched HIGH on a partial train.
        writeDigitalTX(false);
        M5_LIB_LOGE("send_pulse_train: writeDigitalTX failed inside pulse loop");
        return false;
    }
    return true;
}

}  // namespace unit
}  // namespace m5
