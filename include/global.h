#ifndef __GLOBAL_H__
#define __GLOBAL_H__

#include <Arduino.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"

extern float glob_temperature;
extern float glob_humidity;

extern float temp_history[10];
extern float humi_history[10];
void update_history(float t, float h);

extern String ssid;
extern String password;
extern String wifi_ssid; 
extern String wifi_password;
extern volatile boolean isWifiConnected;

extern volatile bool led_auto_mode;
extern volatile uint8_t led_manual_r;
extern volatile uint8_t led_manual_g;
extern volatile uint8_t led_manual_b;
extern volatile uint8_t led_brightness;
extern volatile bool led_manual_1;


extern SemaphoreHandle_t xBinarySemaphoreInternet;
extern SemaphoreHandle_t xBinarySemaphoreTemp_blinky;
extern SemaphoreHandle_t xBinarySemaphoreTemp_neo;

#endif