/*
 * SPDX-FileCopyrightText: 2025 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
/*!
  @file unit_RGB.hpp
  @brief RGB unit for M5UnitUnified
*/
#ifndef M5_UNIT_RGB_UNIT_RGB_HPP
#define M5_UNIT_RGB_UNIT_RGB_HPP

#include "unit_SK6812.hpp"

namespace m5 {
namespace unit {

/*!
  @class m5::unit::UnitRGB
  @brief RGB Unit
*/
class UnitRGB : public UnitSK6812GRB {
    M5_UNIT_COMPONENT_HPP_BUILDER(UnitRGB, 0x00);

public:
    //! @brief Constructor (3 LEDs)
    UnitRGB() : UnitSK6812GRB(3 /* 3pixels */)
    {
        auto ccfg         = component_config();
        ccfg.max_children = 1;  // Can connect 1 Unit
        component_config(ccfg);
    }
};

}  // namespace unit
}  // namespace m5
#endif
