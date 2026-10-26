/*
 * M5Stack BCM SPI panel sink
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef HW_MISC_M5_BCM_SPI_PANEL_H
#define HW_MISC_M5_BCM_SPI_PANEL_H

#include "hw/ssi/ssi.h"
#include "qom/object.h"

#define TYPE_M5_BCM_SPI_PANEL "m5-bcm-spi-panel"
OBJECT_DECLARE_SIMPLE_TYPE(M5BcmSpiPanelState, M5_BCM_SPI_PANEL)

#endif
