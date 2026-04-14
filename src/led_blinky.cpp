#include "led_blinky.h"

void led_blinky(void *pvParameters){
    pinMode(LED1_GPIO, OUTPUT);
    digitalWrite(LED1_GPIO, LOW);
   int led_state = 0;  
   float local_temp = 0;
   int delay_time = 0;
  while(1) {              
    
    // Manual mode: control LED1 directly from web
    if (!led_auto_mode) {
      digitalWrite(LED1_GPIO, led_manual_1 ? HIGH : LOW);
      vTaskDelay(pdMS_TO_TICKS(100));
      continue;
    }

    // Auto mode: blink LED based on temperature
    if(xSemaphoreTake(xBinarySemaphoreTemp_blinky,0)){
        local_temp = glob_temperature;
        delay_time = 500;
    }

    if(local_temp >= 21 && local_temp <= 30){
      led_state = 1-led_state;
      digitalWrite(LED1_GPIO,led_state);
      delay_time = 1000;
    }
  
    if(local_temp <= 20){
       led_state = 1-led_state;
       digitalWrite(LED1_GPIO,led_state);
       delay_time = 500;
    }

     if(local_temp > 30){
       led_state = 1-led_state;
       digitalWrite(LED1_GPIO,led_state);
       delay_time = 250;
     }
 
    vTaskDelay(delay_time);
  }
}