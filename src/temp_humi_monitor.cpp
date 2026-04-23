#include "temp_humi_monitor.h"
DHT20 dht20;
LiquidCrystal_I2C lcd(0x27, 16, 2);

void temp_humi_monitor(void *pvParameters){

    Wire.begin(11, 12);
    dht20.begin();
    lcd.begin();
    lcd.backlight();
    
    while (1){
        dht20.read();
        float temperature = dht20.getTemperature();
        float humidity = dht20.getHumidity();

        if (isnan(temperature) || isnan(humidity)) {
            Serial.println("Failed to read from DHT sensor!");
            vTaskDelay(pdMS_TO_TICKS(1000));
            continue;
        }

        glob_temperature = temperature;
        glob_humidity = humidity;
        xSemaphoreGive(xBinarySemaphoreTemp_blinky);
        xSemaphoreGive(xBinarySemaphoreTemp_neo);
        xSemaphoreGive(xBinarySemaphoreTinyMLData);
        update_history(glob_temperature,glob_humidity);

        if (glob_temperature > glob_temp_threshold) {
            lcd.clear(); 
            
            lcd.setCursor(0, 1);
            lcd.print("T:");
            lcd.print(temperature, 1);
            lcd.print("C > ");
            lcd.print(glob_temp_threshold, 0);

            for (int i = 0; i < 5; i++) {
                lcd.setCursor(0, 0);
                lcd.print("! WARNING TEMP !");
                vTaskDelay(pdMS_TO_TICKS(500));
                
                lcd.setCursor(0, 0);
                lcd.print("                ");
                vTaskDelay(pdMS_TO_TICKS(500));
            }
        } else {
            lcd.clear(); 
            lcd.setCursor(0, 0);
            lcd.print("H: ");
            lcd.print(humidity, 1);
            lcd.print("%");

            lcd.setCursor(0, 1);
            lcd.print("T: ");
            lcd.print(temperature, 1);
            lcd.print("C");
            
            vTaskDelay(pdMS_TO_TICKS(1000));
        }
    }
}