/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
/*
  UnitTest for UnitAW3641E (Unit FlashLight)
*/
#include <gtest/gtest.h>
#include <M5Unified.h>
#include <M5UnitUnified.hpp>
#include <googletest/test_template.hpp>
#include <googletest/test_helper.hpp>
#include <unit/unit_AW3641E.hpp>

using namespace m5::unit::googletest;
using namespace m5::unit;
using namespace m5::unit::aw3641e;

class TestAW3641E : public GPIOComponentTestBase<UnitAW3641E> {
protected:
    // Override to match UnitAW3641E's TX-only nature (EN pin only, no RX).
    bool begin() override
    {
        return m5::unit::wiring::addGPIO(Units, *unit, m5::unit::wiring::GpioRole::OutOnly) && Units.begin();
    }
    virtual UnitAW3641E* get_instance() override
    {
        return new m5::unit::UnitAW3641E();
    }
};

class TestAW3641EAsTorch : public GPIOComponentTestBase<UnitAW3641E> {
protected:
    bool begin() override
    {
        return m5::unit::wiring::addGPIO(Units, *unit, m5::unit::wiring::GpioRole::OutOnly) && Units.begin();
    }
    virtual UnitAW3641E* get_instance() override
    {
        auto* u             = new m5::unit::UnitAW3641E();
        auto cfg            = u->config();
        cfg.switch_position = SwitchPosition::Torch;
        u->config(cfg);
        return u;
    }
};

// --- pure-API tests (no hardware required) ---

TEST(AW3641E, PulseCountTranslation)
{
    EXPECT_EQ(to_pulse_count(Brightness::Pct100), 1);
    EXPECT_EQ(to_pulse_count(Brightness::Pct90), 2);
    EXPECT_EQ(to_pulse_count(Brightness::Pct80), 3);
    EXPECT_EQ(to_pulse_count(Brightness::Pct70), 4);
    EXPECT_EQ(to_pulse_count(Brightness::Pct60), 5);
    EXPECT_EQ(to_pulse_count(Brightness::Pct50), 6);
    EXPECT_EQ(to_pulse_count(Brightness::Pct40), 7);
    EXPECT_EQ(to_pulse_count(Brightness::Pct30), 8);
}

TEST(AW3641E, SwitchPositionEnumIsDistinct)
{
    EXPECT_NE(SwitchPosition::Flash, SwitchPosition::Torch);
}

TEST(AW3641E, ConfigDefaults)
{
    UnitAW3641E::config_t cfg{};
    EXPECT_EQ(cfg.switch_position, SwitchPosition::Flash);
}

TEST(AW3641E, DurationConstants)
{
    EXPECT_EQ(FLASH_MAX_DURATION_MS, 220u);
    EXPECT_EQ(TORCH_MAX_DURATION_MS, 1300u);
    EXPECT_LT(FLASH_MAX_DURATION_MS, TORCH_MAX_DURATION_MS);
}

TEST(AW3641E, PulseTimingConstants)
{
    // T_HI/T_LO must be within the AW3641E datasheet budget (0.75..10 us).
    // Lower bound relaxed to 1 us because constexpr uint32_t cannot express 0.75.
    EXPECT_GE(PULSE_HIGH_US, 1u);
    EXPECT_LE(PULSE_HIGH_US, 10u);
    EXPECT_GE(PULSE_LOW_US, 1u);
    EXPECT_LE(PULSE_LOW_US, 10u);
    // T_OFF must exceed 500 us per datasheet.
    EXPECT_GT(PULSE_OFF_US, 500u);
}

// --- HW-in-loop tests (require GPIO adapter to be wired to U152) ---

TEST_F(TestAW3641E, Instance)
{
    SCOPED_TRACE(ustr);
    EXPECT_NE(unit, nullptr);
}

TEST_F(TestAW3641E, BeginInitialState)
{
    SCOPED_TRACE(ustr);
    // Default config: switch_position = Flash, no flash/torch active
    EXPECT_FALSE(unit->active());
    EXPECT_EQ(unit->lastDurationMs(), 0u);
    EXPECT_EQ(unit->config().switch_position, SwitchPosition::Flash);
}

TEST_F(TestAW3641E, ConfigRoundTrip)
{
    SCOPED_TRACE(ustr);

    auto cfg            = unit->config();
    cfg.switch_position = SwitchPosition::Torch;
    unit->config(cfg);

    auto out = unit->config();
    EXPECT_EQ(out.switch_position, SwitchPosition::Torch);
}

TEST_F(TestAW3641E, FlashShortPulse)
{
    SCOPED_TRACE(ustr);

    EXPECT_TRUE(unit->flash(Brightness::Pct100, 50));
    EXPECT_TRUE(unit->active());
    EXPECT_EQ(unit->lastDurationMs(), 50u);

    // Let auto-off trigger via update()
    m5::utility::delay(80);
    unit->update();
    EXPECT_FALSE(unit->active());
}

TEST_F(TestAW3641E, FlashWithDefaults)
{
    SCOPED_TRACE(ustr);

    // flash() with no args should default to Brightness::Pct100, duration FLASH_MAX_DURATION_MS
    EXPECT_TRUE(unit->flash());
    EXPECT_TRUE(unit->active());
    EXPECT_EQ(unit->lastDurationMs(), FLASH_MAX_DURATION_MS);

    m5::utility::delay(FLASH_MAX_DURATION_MS + 30);
    unit->update();
    EXPECT_FALSE(unit->active());
}

TEST_F(TestAW3641E, FlashRejectsZeroDuration)
{
    SCOPED_TRACE(ustr);

    EXPECT_FALSE(unit->flash(Brightness::Pct100, 0));
    EXPECT_FALSE(unit->active());
}

TEST_F(TestAW3641E, FlashDurationClamp)
{
    SCOPED_TRACE(ustr);

    // duration > FLASH_MAX_DURATION_MS is clamped
    EXPECT_TRUE(unit->flash(Brightness::Pct100, FLASH_MAX_DURATION_MS + 500));
    EXPECT_EQ(unit->lastDurationMs(), FLASH_MAX_DURATION_MS);
    EXPECT_TRUE(unit->stop());
}

TEST_F(TestAW3641E, FlashRejectsWhenSwitchPositionTorch)
{
    SCOPED_TRACE(ustr);

    auto cfg            = unit->config();
    cfg.switch_position = SwitchPosition::Torch;
    unit->config(cfg);

    EXPECT_FALSE(unit->flash(Brightness::Pct100, 50));
    EXPECT_FALSE(unit->active());
}

TEST_F(TestAW3641E, AllBrightnessLevels)
{
    SCOPED_TRACE(ustr);

    const Brightness levels[] = {Brightness::Pct100, Brightness::Pct90, Brightness::Pct80, Brightness::Pct70,
                                 Brightness::Pct60,  Brightness::Pct50, Brightness::Pct40, Brightness::Pct30};
    for (auto b : levels) {
        EXPECT_TRUE(unit->flash(b, 30));
        m5::utility::delay(50);
        unit->update();
    }
    EXPECT_TRUE(unit->stop());
}

TEST_F(TestAW3641E, FlashCancelsInFlightWithStop)
{
    SCOPED_TRACE(ustr);

    EXPECT_TRUE(unit->flash(Brightness::Pct100, 200));
    EXPECT_TRUE(unit->active());

    EXPECT_TRUE(unit->stop());
    EXPECT_FALSE(unit->active());

    // update() should not flip active back on.
    unit->update();
    EXPECT_FALSE(unit->active());
}

TEST_F(TestAW3641E, FlashRetriggerCancelsPrevious)
{
    SCOPED_TRACE(ustr);

    EXPECT_TRUE(unit->flash(Brightness::Pct100, 200));
    EXPECT_TRUE(unit->active());

    // Re-trigger while still active should cancel the previous and start new.
    EXPECT_TRUE(unit->flash(Brightness::Pct50, 50));
    EXPECT_TRUE(unit->active());
    EXPECT_EQ(unit->lastDurationMs(), 50u);

    m5::utility::delay(80);
    unit->update();
    EXPECT_FALSE(unit->active());
}

TEST_F(TestAW3641E, StopWhenIdleIsNoOpSuccess)
{
    SCOPED_TRACE(ustr);

    EXPECT_FALSE(unit->active());
    EXPECT_TRUE(unit->stop());
    EXPECT_FALSE(unit->active());
}

// --- Torch fixture (config: switch_position = Torch) ---

TEST_F(TestAW3641EAsTorch, TorchInitialState)
{
    SCOPED_TRACE(ustr);
    EXPECT_EQ(unit->config().switch_position, SwitchPosition::Torch);
    EXPECT_FALSE(unit->active());
}

TEST_F(TestAW3641EAsTorch, TorchAutoOff)
{
    SCOPED_TRACE(ustr);

    EXPECT_TRUE(unit->torch(50));
    EXPECT_TRUE(unit->active());
    EXPECT_EQ(unit->lastDurationMs(), 50u);

    m5::utility::delay(80);
    unit->update();
    EXPECT_FALSE(unit->active());
}

TEST_F(TestAW3641EAsTorch, TorchWithDefaults)
{
    SCOPED_TRACE(ustr);

    // torch() with no arg defaults to TORCH_MAX_DURATION_MS
    EXPECT_TRUE(unit->torch());
    EXPECT_EQ(unit->lastDurationMs(), TORCH_MAX_DURATION_MS);
    EXPECT_TRUE(unit->stop());
}

TEST_F(TestAW3641EAsTorch, TorchRejectsZeroDuration)
{
    SCOPED_TRACE(ustr);

    EXPECT_FALSE(unit->torch(0));
    EXPECT_FALSE(unit->active());
}

TEST_F(TestAW3641EAsTorch, TorchDurationClamp)
{
    SCOPED_TRACE(ustr);

    EXPECT_TRUE(unit->torch(TORCH_MAX_DURATION_MS + 500));
    EXPECT_EQ(unit->lastDurationMs(), TORCH_MAX_DURATION_MS);
    EXPECT_TRUE(unit->stop());
}

TEST_F(TestAW3641EAsTorch, TorchRejectsWhenSwitchPositionFlash)
{
    SCOPED_TRACE(ustr);

    auto cfg            = unit->config();
    cfg.switch_position = SwitchPosition::Flash;
    unit->config(cfg);

    EXPECT_FALSE(unit->torch(50));
    EXPECT_FALSE(unit->active());
}
