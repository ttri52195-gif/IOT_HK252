#include "neo_blinky.h"

void neo_blinky(void *pvParameters){

    Adafruit_NeoPixel strip(LED_COUNT, NEO_PIN, NEO_GRB + NEO_KHZ800);
    strip.begin();
    strip.clear();
    strip.show();
    float local_hum = 0;
    uint32_t currentColor = strip.Color(0,0,0);
    while(1) {

        // chỉ update khi có data mới
      if(xSemaphoreTake(xBinarySemaphoreTemp_blinky,0)){

          local_hum = glob_humidity;

      }
            uint32_t newColor;
            if(!isWifiConnected){
                 newColor = strip.Color(128, 0, 128);   

            }
            else if(glob_humidity <= 60){
                newColor = strip.Color(0, 255, 0);   

            }
            else if(glob_humidity <= 80){
                newColor = strip.Color(255, 0, 0);   
            }
            else {
                newColor = strip.Color(0, 0, 255);   

            }

            if(newColor != currentColor){
                currentColor = newColor;
                strip.setPixelColor(0, currentColor);
                strip.show();
            }
        

        // task vẫn chạy đều
        vTaskDelay(pdMS_TO_TICKS(300));  
    }
}