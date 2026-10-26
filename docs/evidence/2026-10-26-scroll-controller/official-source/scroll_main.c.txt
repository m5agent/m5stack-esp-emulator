/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2024 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "i2c.h"
#include "tim.h"
#include "gpio.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <string.h>
#include "flash.h"
#include "ws2812.h"
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define I2C_ADDRESS 0x40
#define FIRMWARE_VERSION 1
#define APPLICATION_ADDRESS     ((uint32_t)0x08001000)
#define BOOTLOADER_VER_ADDR ((uint32_t)0x08001000 - 1)
uint32_t bootloader_version;
#define FLASH_DATA_SIZE 32
#define TIM_ENCODE_DEFAULT  0x8000
#define RGB_BUFFER_SIZE 10
/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */
uint8_t i2c_address[1] = {0};
__IO uint8_t fm_version = FIRMWARE_VERSION;
volatile uint32_t i2c_stop_timeout_delay = 0;
volatile uint8_t flag_jump_bootloader = 0;
volatile uint32_t jump_bootloader_timeout = 0;
uint8_t flash_data[FLASH_DATA_SIZE] = {0};
volatile int32_t encoder_change = 0;
volatile uint8_t ab_dir = 0;

volatile uint8_t g_encoder_direct = 0;
uint16_t usNowCnt;
uint16_t usLastCnt = TIM_ENCODE_DEFAULT;
__IO int8_t cDirCnt = 0;
__IO int32_t encoder_countAB = 0;
__IO int32_t increment_countAB = 0;
__IO uint8_t ucPressState = 0;

uint32_t rgb_color_buffer[RGB_BUFFER_SIZE] = {0};
uint32_t rgb_color_buffer_index = 0;
uint32_t lastest_rgb_color = 0;
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
void IAP_Set()
{
	uint8_t i;
 
	uint32_t *pVecTab=(uint32_t *)(0x20000000);
	//????????SRAM???
	for(i = 0; i < 48; i++)
	{
		*(pVecTab++) = *(__IO uint32_t*)(APPLICATION_ADDRESS + (i<<2));
	}
  /* Enable the SYSCFG peripheral clock*/
#if 1 //STM32
  __HAL_RCC_SYSCFG_CLK_ENABLE();
  //??? SRAM ??? 0x00000000
  __HAL_SYSCFG_REMAPMEMORY_SRAM();
#else //AMP32
    RCM_EnableAPB2PeriphClock(RCM_APB2_PERIPH_SYSCFG);
    /* Remap SRAM at 0x00000000 */
    SYSCFG->CFG1_B.MMSEL = SYSCFG_MemoryRemap_SRAM;
#endif
}

void init_flash_data(void) 
{   
  if (!(readPackedMessageFromFlash(flash_data, FLASH_DATA_SIZE))) {
    i2c_address[0] = I2C_ADDRESS;

    flash_data[0] = i2c_address[0];
    flash_data[1] = ab_dir;
    writeMessageToFlash(flash_data , FLASH_DATA_SIZE);
  } else {
    i2c_address[0] = flash_data[0];
    ab_dir = flash_data[1];
  }
}

void flash_data_write_back(void)
{
  if (readPackedMessageFromFlash(flash_data, FLASH_DATA_SIZE)) {
    flash_data[0] = i2c_address[0];
    flash_data[1] = ab_dir;
    writeMessageToFlash(flash_data , FLASH_DATA_SIZE);
  }     
}

void encoder_init(void)
{
  HAL_TIM_Encoder_Start(&htim3, TIM_CHANNEL_1 | TIM_CHANNEL_2);
  __HAL_TIM_ENABLE_IT(&htim3, TIM_IT_UPDATE);
  __HAL_TIM_SET_COUNTER(&htim3, TIM_ENCODE_DEFAULT);
}

void update_encoder(void) {
  g_encoder_direct = !(uint32_t)(__HAL_TIM_IS_TIM_COUNTING_DOWN(&htim3));
  usNowCnt = __HAL_TIM_GET_COUNTER(&htim3);
  if (!ab_dir)
    encoder_change = usNowCnt - usLastCnt;
  else
    encoder_change = usLastCnt - usNowCnt;
  if (cDirCnt < 0) {
    encoder_countAB += 65536 + encoder_change;
    increment_countAB += 65536 + encoder_change;
  } else if(cDirCnt > 0){
    encoder_countAB += -65536 + encoder_change;
    increment_countAB += -65536 + encoder_change;
  } else {
    encoder_countAB += encoder_change;
    increment_countAB += encoder_change;
  }
  usLastCnt = usNowCnt;
  cDirCnt = 0;  
	ucPressState = (!!(BTN1_GPIO_Port->IDR & BTN1_Pin));
}

void Slave_Complete_Callback(uint8_t *rx_data, uint16_t len) 
{
  uint8_t rx_buf[16];
  uint8_t tx_buf[32];
  uint8_t rx_mark[16] = {0}; 

  if (len > 1) {
    if (rx_data[0] == 0xFF)
    {
      if (len == 2) {
        if (rx_data[1] < 128) {
          i2c_address[0] = rx_data[1];
          flash_data_write_back();
          user_i2c_init();
        }
      }
    }
    else if (rx_data[0] == 0xFD)
    {
      if (rx_data[1] == 1) {
        flag_jump_bootloader = 1;
        if (flag_jump_bootloader) {
          LL_I2C_DeInit(I2C1);
          LL_I2C_DisableAutoEndMode(I2C1);
          LL_I2C_Disable(I2C1);
          LL_I2C_DisableIT_ADDR(I2C1);
          HAL_TIM_Encoder_MspDeInit(&htim3);
          __HAL_TIM_DISABLE_IT(&htim3, TIM_IT_UPDATE);
          i2c_port_set_to_input();
          while ((!!(GPIOA->IDR & LL_GPIO_PIN_9)) || (!!(GPIOA->IDR & LL_GPIO_PIN_10)))
          {
            jump_bootloader_timeout++;
            if (jump_bootloader_timeout >= 60000) {
              flag_jump_bootloader = 0;
              break;
            }
          }
          if (jump_bootloader_timeout < 60000) {
            NVIC_SystemReset();
          } else {
            MX_GPIO_Init();
            MX_TIM3_Init();
            encoder_init();
            user_i2c_init();
            i2c1_it_enable();        
            jump_bootloader_timeout = 0;
          }
        }        
      }
    }
    else if (rx_data[0] == 0xFB) {
      if (rx_data[1]) {
        ab_dir = 1;
      }
      else {
        ab_dir = 0;
      }
      flash_data_write_back();
    }
    else if (rx_data[0] >= 0x10 && rx_data[0] <= 0x13) {
      for(int i = 0; i < len - 1; i++) {
        rx_buf[rx_data[0]-0x10+i] = rx_data[1+i];
        rx_mark[rx_data[0]-0x10+i] = 1;     
      }       
      if (rx_mark[0]) {
        encoder_countAB &= ~0x000000ff;
        encoder_countAB |= rx_buf[0];
      }
      if (rx_mark[1]) {
        encoder_countAB &= ~0x0000ff00;
        encoder_countAB |= (rx_buf[1] << 8);
      }
      if (rx_mark[2]) {
        encoder_countAB &= ~0x00ff0000;
        encoder_countAB |= (rx_buf[2] << 16);
      }
      if (rx_mark[3]) {
        encoder_countAB &= ~0xff000000;
        encoder_countAB |= (rx_buf[3] << 24);
      }        
    }      
    else if ((rx_data[0] >= 0x30) && (rx_data[0] <= 0x33))
    {
      for(int i = 0; i < len - 1; i++) {
        rx_buf[rx_data[0]-0x30+i] = rx_data[1+i];
        rx_mark[rx_data[0]-0x30+i] = 1;     
      }      
      if (rx_mark[0]) {
        rgb_color_buffer[rgb_color_buffer_index] &= ~0x000000ff;
        rgb_color_buffer[rgb_color_buffer_index] |= rx_buf[0];
      }
      if (rx_mark[1]) {
        rgb_color_buffer[rgb_color_buffer_index] &= ~0x0000ff00;
        rgb_color_buffer[rgb_color_buffer_index] |= (rx_buf[1] << 8);
      }
      if (rx_mark[2]) {
        rgb_color_buffer[rgb_color_buffer_index] &= ~0x00ff0000;
        rgb_color_buffer[rgb_color_buffer_index] |= (rx_buf[2] << 16);
      }
      if (rx_mark[3]) {
        rgb_color_buffer[rgb_color_buffer_index] &= ~0xff000000;
        rgb_color_buffer[rgb_color_buffer_index] |= (rx_buf[3] << 24);
      }   
      lastest_rgb_color = rgb_color_buffer[rgb_color_buffer_index];
      if (rgb_color_buffer_index < (RGB_BUFFER_SIZE-1))   
        ++rgb_color_buffer_index;
    }
    else if (rx_data[0] == 0x40) {
      if (rx_data[1] == 1) {
        encoder_countAB = 0;
        increment_countAB = 0;
      }
    }      
  }
  else if (len == 1) {
    if (rx_data[0] == 0xFF)
    {
      i2c1_set_send_data(i2c_address, 1); 
    }  
    else if (rx_data[0] == 0xFE)
    {
      i2c1_set_send_data((uint8_t *)&fm_version, 1);
    } 
    else if (rx_data[0] == 0xFC)
    {
      bootloader_version = *(uint8_t*)BOOTLOADER_VER_ADDR;
      i2c1_set_send_data((uint8_t *)&bootloader_version, 1);
    } 
    else if (rx_data[0] == 0xFB)
    {
      i2c1_set_send_data((uint8_t *)&ab_dir, 1);
    } 
    else if (rx_data[0] >= 0x10 && rx_data[0] <= 0x13)
    {
      memcpy(&tx_buf[0], (uint8_t *)&encoder_countAB, 4);
      i2c1_set_send_data((uint8_t *)&tx_buf[rx_data[0]-0x10], 0x13-rx_data[0]+1);
    }
    else if (rx_data[0] == 0x20)
    {
      i2c1_set_send_data((uint8_t *)&ucPressState, 1);
    }   
    else if ((rx_data[0] >= 0x30) && (rx_data[0] <= 0x33))
    {
      memcpy(&tx_buf[0], (uint8_t *)&lastest_rgb_color, 4);
      i2c1_set_send_data((uint8_t *)&tx_buf[rx_data[0]-0x30], 0x33-rx_data[0]+1);
    }                                
    else if ((rx_data[0] >= 0x50) && (rx_data[0] <= 0x53))
    {
      memcpy(&tx_buf[0], (uint8_t *)&increment_countAB, 4);
      i2c1_set_send_data((uint8_t *)&tx_buf[rx_data[0]-0x50], 0x53-rx_data[0]+1);
      increment_countAB = 0;
    }                                
    else if (rx_data[0] == 0x60)
    {
      i2c1_set_send_data((uint8_t *)&g_encoder_direct, 1);
    }                                
  }
}
/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{
  /* USER CODE BEGIN 1 */
  IAP_Set();
  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  // MX_I2C1_Init();
  MX_TIM3_Init();
  /* USER CODE BEGIN 2 */
  encoder_init();
  init_flash_data();
  sk6812_init(TOTAL_RGB);
  user_i2c_init();
  i2c1_it_enable();
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
		update_encoder();
    i2c_timeout_counter = 0;
    if (i2c_stop_timeout_flag) {
      if (i2c_stop_timeout_delay < HAL_GetTick()) {
        i2c_stop_timeout_counter++;
        i2c_stop_timeout_delay = HAL_GetTick() + 10;
      }
    }
    if (i2c_stop_timeout_counter > 50) {
      LL_I2C_DeInit(I2C1);
      LL_I2C_DisableAutoEndMode(I2C1);
      LL_I2C_Disable(I2C1);
      LL_I2C_DisableIT_ADDR(I2C1);     
      user_i2c_init();    
      i2c1_it_enable();
      LL_mDelay(500);
    } 
    if (rgb_color_buffer_index) {
      uint32_t rgb_show_index = rgb_color_buffer_index;
      for (uint32_t i = 0; i < rgb_show_index; i++) {
        neopixel_set_color(0, rgb_color_buffer[i]);
        neopixel_show();
      }
      rgb_color_buffer_index = 0;
    }        
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  LL_FLASH_SetLatency(LL_FLASH_LATENCY_1);
  while(LL_FLASH_GetLatency() != LL_FLASH_LATENCY_1)
  {
  }
  LL_RCC_HSI_Enable();

   /* Wait till HSI is ready */
  while(LL_RCC_HSI_IsReady() != 1)
  {

  }
  LL_RCC_HSI_SetCalibTrimming(16);
  LL_RCC_PLL_ConfigDomain_SYS(LL_RCC_PLLSOURCE_HSI_DIV_2, LL_RCC_PLL_MUL_12);
  LL_RCC_PLL_Enable();

   /* Wait till PLL is ready */
  while(LL_RCC_PLL_IsReady() != 1)
  {

  }
  LL_RCC_SetAHBPrescaler(LL_RCC_SYSCLK_DIV_1);
  LL_RCC_SetAPB1Prescaler(LL_RCC_APB1_DIV_1);
  LL_RCC_SetSysClkSource(LL_RCC_SYS_CLKSOURCE_PLL);

   /* Wait till System clock is ready */
  while(LL_RCC_GetSysClkSource() != LL_RCC_SYS_CLKSOURCE_STATUS_PLL)
  {

  }
  LL_SetSystemCoreClock(48000000);

   /* Update the time base */
  if (HAL_InitTick (TICK_INT_PRIORITY) != HAL_OK)
  {
    Error_Handler();
  }
  LL_RCC_SetI2CClockSource(LL_RCC_I2C1_CLKSOURCE_HSI);
}

/* USER CODE BEGIN 4 */

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
    HAL_NVIC_SystemReset();
  }
  /* USER CODE END Error_Handler_Debug */
}

#ifdef  USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
