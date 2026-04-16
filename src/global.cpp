#include "global.h"
float glob_temperature = 0;
float glob_humidity = 0;

String ssid = "ESP32-YOUR NETWORK HERE!!!";
String password = "12345678";
String wifi_ssid = "DESKTOP-NAUDP9H 6020";
String wifi_password = "tmt05052005";
// String wifi_ssid = "P409";
// String wifi_password = "phong409@";


volatile boolean  isWifiConnected = false;
volatile bool led_auto_mode = true;
volatile uint8_t led_manual_r = 0;
volatile uint8_t led_manual_g = 0;
volatile uint8_t led_manual_b = 255;
volatile uint8_t led_brightness = 100;
volatile bool led_manual_1 = false;
volatile bool tinyml_has_prediction = false;
volatile int tinyml_predicted_label = -1;
volatile float tinyml_confidence = 0.0f;
volatile float tinyml_last_temp = 0.0f;
volatile float tinyml_last_humi = 0.0f;
volatile unsigned long tinyml_last_update_ms = 0;
SemaphoreHandle_t xBinarySemaphoreInternet = xSemaphoreCreateBinary();
SemaphoreHandle_t xBinarySemaphoreTemp_blinky     = xSemaphoreCreateBinary();
SemaphoreHandle_t xBinarySemaphoreTemp_neo        = xSemaphoreCreateBinary();
SemaphoreHandle_t xBinarySemaphoreTinyMLData      = xSemaphoreCreateBinary();


float temp_history[10] = {0,0,0,0,0,0,0,0,0,0};
float humi_history[10] = {0,0,0,0,0,0,0,0,0,0};
static unsigned long history_update_count = 0;

// Hàm dịch mảng và thêm dữ liệu mới nhất vào cuối (vị trí số 9)
void update_history(float t, float h) {
  for (int i = 0; i < 9; i++) {
    temp_history[i] = temp_history[i + 1];
    humi_history[i] = humi_history[i + 1];
  }
  temp_history[9] = t;
  humi_history[9] = h;

  history_update_count++;
  if (history_update_count % 5 == 0) {
    Serial.print("history updated, latest T=");
    Serial.print(temp_history[9]);
    Serial.print(" H=");
    Serial.println(humi_history[9]);
  }
}