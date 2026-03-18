#include "global.h"
float glob_temperature = 0;
float glob_humidity = 0;

String ssid = "ESP32-YOUR NETWORK HERE!!!";
String password = "12345678";
String wifi_ssid = "DESKTOP-NAUDP9H 6020";
String wifi_password = "tmt05052005";
volatile boolean  isWifiConnected = false;
SemaphoreHandle_t xBinarySemaphoreInternet = xSemaphoreCreateBinary();
SemaphoreHandle_t xBinarySemaphoreTemp_blinky     = xSemaphoreCreateBinary();
SemaphoreHandle_t xBinarySemaphoreTemp_neo        = xSemaphoreCreateBinary();