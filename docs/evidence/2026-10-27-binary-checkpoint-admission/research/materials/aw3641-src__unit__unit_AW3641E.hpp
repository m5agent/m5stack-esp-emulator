/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
/*!
  @file unit_AW3641E.hpp
  @brief AW3641E Unit for M5UnitUnified

  Driver for UnitFlashLight (SKU:U152).
  AW3641E is an Awinic 1A flash LED driver controlled via a 1-wire EN pulse protocol.
*/
#ifndef M5_UNIT_FLASHLIGHT_UNIT_AW3641E_HPP
#define M5_UNIT_FLASHLIGHT_UNIT_AW3641E_HPP

#include <M5UnitComponent.hpp>

namespace m5 {
namespace unit {

/*!
  @namespace aw3641e
  @brief For AW3641E
 */
namespace aw3641e {

/*!
  @enum SwitchPosition
  @brief Position of the on-board mode selection switch (silkscreen `S1`, SPDT type)
  @note The switch is wired between the AW3641E `FLASH` pin and either +5V (Flash side)
        or GND (Torch side). It is NOT connected to the host MCU and cannot be read
        from software, so this enum is a DECLARATION of the physical switch position
        — the library trusts what the user configured. A mismatch between the declared
        value and the physical switch results in undefined optical behavior.
 */
enum class SwitchPosition : uint8_t {
    Flash,  //!< S1 = Flash side. FLASH pin = +5V. Use flash() to fire pulse-controlled flashes.
    Torch,  //!< S1 = Torch side. FLASH pin = GND. Use torch() to drive continuous illumination.
};

/*!
  @enum Brightness
  @brief Flash brightness level (percentage of I_FLASH; Flash mode only)
  @note On UnitFlashLight (U152) with R_SET = 100 kΩ and R_SENSE = 0.22 Ω,
        I_FLASH(100%) is approximately 584 mA. Torch mode uses a fixed
        ~214 mA regardless of this setting.
 */
enum class Brightness : uint8_t {
    Pct100,  //!< 100% of I_FLASH
    Pct90,   //!< 90%
    Pct80,   //!< 80%
    Pct70,   //!< 70%
    Pct60,   //!< 60%
    Pct50,   //!< 50%
    Pct40,   //!< 40%
    Pct30,   //!< 30% of I_FLASH
};

//! @brief Minimum logic-high pulse width in microseconds (T_HI; datasheet 0.75-10 µs)
constexpr uint32_t PULSE_HIGH_US{4};
//! @brief Minimum logic-low pulse width in microseconds (T_LO; datasheet 0.75-10 µs)
constexpr uint32_t PULSE_LOW_US{4};
//! @brief Minimum EN-low delay required before a pulse sequence (T_OFF; datasheet > 500 µs)
constexpr uint32_t PULSE_OFF_US{600};

//! @brief Maximum duration for a single flash() call in milliseconds
//! @note Matches the AW3641E Flash mode hardware timeout for Pulse 1-8 (220 ms).
//!       For longer continuous on-time use torch() instead.
constexpr uint16_t FLASH_MAX_DURATION_MS{220};

//! @brief Maximum duration for a single torch() call in milliseconds
//! @note Library-side safety cap — but auto-shutdown at this duration still
//!       requires the caller to run Units.update() periodically. Torch mode
//!       itself has no hardware time limit (EN=HIGH continuously drives ~214 mA);
//!       the driver clamps the requested duration but cannot enforce it without
//!       update() calls. Use stop() for guaranteed cutoff.
constexpr uint16_t TORCH_MAX_DURATION_MS{1300};

/*!
  @brief Translate a Brightness level to the AW3641E rising-edge pulse count
  @param b Brightness level
  @return Pulse count in range 1..8 (Pulse 1 = 100% / 220 ms, Pulse 8 = 30% / 220 ms)
  @note Only Pulse 1-8 (Ms220 timeout) is exposed by this library; the chip's
        Pulse 9-16 (1.3 s timeout) range is not used because thermal protection
        causes the LED to dim before the timeout expires at higher currents.
 */
constexpr uint8_t to_pulse_count(const Brightness b)
{
    return static_cast<uint8_t>(static_cast<uint8_t>(b) + 1u);
}

}  // namespace aw3641e

/*!
  @class m5::unit::UnitAW3641E
  @brief 1A flash LED driver controlled via EN-pin pulse protocol
  @warning UnitFlashLight (U152) has an on-board mode selection switch (silkscreen `S1`,
           SPDT type) that selects between Flash and Torch mode by routing the chip's
           FLASH pin to +5V or GND. **The switch state is NOT wired to the host MCU and
           cannot be read from software**; the driver trusts the value declared in
           config_t::switch_position.
  @warning Flash mode (S1 = Flash side): use flash() to fire short metered pulses
           (<= 220 ms). Calling flash() while S1 is on the Torch side does NOT produce a
           metered flash; the LED will simply turn on continuously at the chip's Torch
           current.
  @warning Torch mode (S1 = Torch side): use torch() for steady ~214 mA illumination
           (<= 1.3 s). Calling torch() while S1 is on the Flash side will fire the LED
           briefly (~220 ms) and then dim due to Flash-mode thermal protection.
  @note    If observed behavior does not match the API, power down the unit and toggle
           the physical switch on the PCB before retrying. config_t::switch_position
           must match the physical switch.
 */
class UnitAW3641E : public Component {
    M5_UNIT_COMPONENT_HPP_BUILDER(UnitAW3641E, 0x00);

public:
    /*!
      @struct config_t
      @brief Settings for begin
     */
    struct config_t {
        /*! @brief Declaration of the physical S1 switch position. The driver cannot detect
                  S1 at runtime; it trusts this value. Set this to match the actual switch
                  position on the PCB before calling begin(). */
        aw3641e::SwitchPosition switch_position{aw3641e::SwitchPosition::Flash};
    };

    /*! @brief Constructor
        @param addr Placeholder (GPIO unit; address is ignored) */
    explicit UnitAW3641E(const uint8_t addr = DEFAULT_ADDRESS) : Component(addr)
    {
    }
    /*! @brief Destructor */
    virtual ~UnitAW3641E()
    {
    }

    //! @brief Begin the unit (configures EN as OUTPUT and drives EN LOW)
    //! @return True if successful
    virtual bool begin() override;
    //! @brief Drive EN LOW automatically when the flash/torch duration has elapsed
    //! @param force Currently ignored (kept for API symmetry)
    virtual void update(const bool force = false) override;

    ///@name Settings for begin
    ///@{
    //! @brief Gets the configuration
    //! @return Current configuration
    inline config_t config()
    {
        return _cfg;
    }
    //! @brief Set the configuration
    //! @param cfg Configuration to apply
    inline void config(const config_t& cfg)
    {
        _cfg = cfg;
    }
    ///@}

    ///@name Operation control
    ///@{
    /*!
      @brief Stop any in-flight flash or torch (drives EN LOW immediately)
      @return True if the GPIO write succeeded; safe to call when idle (no-op success)
     */
    bool stop();

    /*!
      @brief Fire a flash with the given brightness for up to FLASH_MAX_DURATION_MS
      @param brightness Brightness level (Pct100..Pct30; default Pct100)
      @param duration_ms Flash duration in milliseconds (default 220).
             Clamped to FLASH_MAX_DURATION_MS (220 ms) with a warning if exceeded.
             A value of 0 returns false without driving the pin.
      @return True on success.
              False if config_t::switch_position is not Flash (logs error),
              if duration_ms is 0, or if the GPIO write fails.
      @note Auto-off depends on periodic Units.update() calls — update() drives EN LOW
            after duration_ms elapses. The AW3641E also enforces a 220 ms hardware
            timeout in Flash mode, so the LED turns off even if update() is missed;
            however, active() remains true until update() runs.
            If a previous flash/torch is still active(), it is cancelled and
            the new flash starts after T_OFF (>500 µs).
      @warning Requires config_t::switch_position == SwitchPosition::Flash to match
               the physical S1 switch.
     */
    bool flash(const aw3641e::Brightness brightness = aw3641e::Brightness::Pct100,
               const uint16_t duration_ms           = aw3641e::FLASH_MAX_DURATION_MS);

    /*!
      @brief Drive the LED continuously in Torch mode for up to TORCH_MAX_DURATION_MS
      @param duration_ms Torch duration in milliseconds (default 1300).
             Clamped to TORCH_MAX_DURATION_MS (1300 ms) with a warning if exceeded.
             A value of 0 returns false without driving the pin.
      @return True on success.
              False if config_t::switch_position is not Torch (logs error),
              if duration_ms is 0, or if the GPIO write fails.
      @note Auto-off is COOPERATIVE — update() drives EN LOW after duration_ms only
            when the caller runs Units.update() (typically once per loop()). Torch mode
            has NO hardware timeout: if update() stops being called (blocked task,
            long delay(), etc.), the LED stays on continuously at ~214 mA until stop()
            is called or power is removed. Call stop() explicitly for hard cutoff.
            If a previous flash/torch is still active(), it is cancelled and
            the new torch starts.
            Torch current is fixed at approximately 214 mA; brightness is not
            adjustable.
      @warning Requires config_t::switch_position == SwitchPosition::Torch to match
               the physical S1 switch.
     */
    bool torch(const uint16_t duration_ms = aw3641e::TORCH_MAX_DURATION_MS);
    ///@}

    ///@name Status accessors
    ///@{
    //! @brief Last applied on-duration in milliseconds (clamped value used for flash() or torch())
    //! @return Duration in milliseconds (after clamping); 0 if no operation has been issued yet
    inline uint16_t lastDurationMs() const
    {
        return _duration_ms;
    }
    //! @brief Is a flash or torch currently in progress?
    //! @return True while update() is still waiting to drive EN LOW
    inline bool active() const
    {
        return _active;
    }
    ///@}

protected:
    //! @brief Send a 1-wire EN pulse train of the given count (1..8 for Brightness Pct100..Pct30)
    //! @param pulse_count Number of rising edges (1..8). Final state is EN = HIGH.
    //! @return True if the GPIO writes succeeded.
    bool send_pulse_train(const uint8_t pulse_count);

protected:
    config_t _cfg{};
    // Flash/torch timing tracker for non-blocking auto-shutdown in update().
    bool _active{false};
    uint32_t _start_ms{0};
    uint16_t _duration_ms{0};
};

}  // namespace unit
}  // namespace m5

#endif
