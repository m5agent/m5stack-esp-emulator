/* SPDX-License-Identifier: Apache-2.0
 * Copyright 2019-2023 Espressif Systems (Shanghai) CO LTD.
 * Derived host harness: pinned ESP-IDF get_reading_error and S3 coefficients.
 * See docs/unit-research/esp32s3-adc-calibration.md for provenance.
 */
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#define COEFF_GROUP_NUM 4
#define TERM_MAX 5
#define ESP_LOGV(...) ((void)0)
typedef struct {uint8_t term_num;const uint64_t (*coeff)[2];const int32_t *sign;} cali_chars_second_step_t;
const static uint64_t adc1_error_coef_atten[COEFF_GROUP_NUM][TERM_MAX][2] = {
    {{27856531419538344, 1e16}, {50871540569528, 1e16}, {9798249589, 1e15}, {0, 0}, {0, 0}},                       //ADC1 atten0
    {{29831022915028695, 1e16}, {49393185868806, 1e16}, {101379430548, 1e16}, {0, 0}, {0, 0}},                     //ADC1 atten1
    {{23285545746296417, 1e16}, {147640181047414, 1e16}, {208385525314, 1e16}, {0, 0}, {0, 0}},                    //ADC1 atten2
    {{644403418269478, 1e15}, {644334888647536, 1e16}, {1297891447611, 1e16}, {70769718, 1e15}, {13515, 1e15}}     //ADC1 atten3
};
const static uint64_t adc2_error_coef_atten[COEFF_GROUP_NUM][TERM_MAX][2] = {
    {{25668651654328927, 1e16}, {1353548869615, 1e16}, {36615265189, 1e16}, {0, 0}, {0, 0}},                       //ADC2 atten0
    {{23690184690298404, 1e16}, {66319894226185, 1e16}, {118964995959, 1e16}, {0, 0}, {0, 0}},                     //ADC2 atten1
    {{9452499397020617, 1e16}, {200996773954387, 1e16}, {259011467956, 1e16}, {0, 0}, {0, 0}},                     //ADC2 atten2
    {{12247719764336924, 1e16}, {755717904943462, 1e16}, {1478791187119, 1e16}, {79672528, 1e15}, {15038, 1e15}}   //ADC2 atten3
};
/**
 * Term sign
 */
const static int32_t adc1_error_sign[COEFF_GROUP_NUM][TERM_MAX] = {
    {-1, -1, 1, 0,  0},  //ADC1 atten0
    {-1, -1, 1, 0,  0},  //ADC1 atten1
    {-1, -1, 1, 0,  0},  //ADC1 atten2
    {-1, -1, 1, -1, 1}   //ADC1 atten3
};
const static int32_t adc2_error_sign[COEFF_GROUP_NUM][TERM_MAX] = {
    {-1,  1, 1,  0, 0},  //ADC2 atten0
    {-1, -1, 1,  0, 0},  //ADC2 atten1
    {-1, -1, 1,  0, 0},  //ADC2 atten2
    { 1, -1, 1, -1, 1}   //ADC2 atten3
};


static int32_t get_reading_error(uint64_t v_cali_1, const cali_chars_second_step_t *param)
{
    if (v_cali_1 == 0 || param->term_num == 0) {
        return 0;
    }

    uint8_t term_num = param->term_num;
    int32_t error = 0;
    uint64_t coeff = 0;
    uint64_t variable[term_num];
    uint64_t term[term_num];
    memset(variable, 0, term_num * sizeof(uint64_t));
    memset(term, 0, term_num * sizeof(uint64_t));

    /**
     *  The scheme formula is:
     *  error = (K0 * X^0) + (K1 * X^1)  + (K2 * X^2) + (K3 * X^3) + ... +  (Kn * X^n);
     */
    variable[0] = 1;
    coeff = (param->coeff)[0][0];
    term[0] = variable[0] * coeff / (param->coeff)[0][1];
    error = (int32_t)term[0] * (param->sign)[0];

    for (int i = 1; i < term_num; i++) {
        variable[i] = variable[i - 1] * v_cali_1;
        coeff = (param->coeff)[i][0];
        term[i] = variable[i] * coeff;
        ESP_LOGV(TAG, "big coef is %llu, big term%d is %llu, coef_id is %d", coeff, i, term[i], i);

        term[i] = term[i] / (param->coeff)[i][1];
        error += (int32_t)term[i] * (param->sign)[i];
        ESP_LOGV(TAG, "term%d is %llu, error is %"PRId32, i, term[i], error);
    }

    return error;
}
int main(void) {
 const int refs[4]={3664,2785,1989,1123};
 const int raws[]={0,1,330,660,1123,1651,2048,2642,3302,4095};
 for(int u=1;u<=2;u++)for(int a=0;a<4;a++) {
  cali_chars_second_step_t p={a==3?5:3,u==1?adc1_error_coef_atten[a]:adc2_error_coef_atten[a],u==1?adc1_error_sign[a]:adc2_error_sign[a]};
  uint32_t gradient=65536*850/refs[a];
  for(unsigned i=0;i<sizeof(raws)/sizeof(raws[0]);i++) {
   uint64_t first=(uint64_t)raws[i]*gradient/65536;
   int32_t voltage=(int32_t)first-get_reading_error(first,&p);
   printf("%d %d %d %d\n",u,a,raws[i],voltage*1000);
  }
 }
 return 0;
}
