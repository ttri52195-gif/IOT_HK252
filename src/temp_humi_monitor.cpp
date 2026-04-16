#include "temp_humi_monitor.h"
DHT20 dht20;
LiquidCrystal_I2C lcd(0x27,16,2);


void temp_humi_monitor(void *pvParameters){

    Wire.begin(11, 12);
    dht20.begin();
    lcd.begin();
    lcd.backlight();
    while (1){
        /* code */
        
        dht20.read();
        // Reading temperature in Celsius
        float temperature = dht20.getTemperature();
        // Reading humidity
        float humidity = dht20.getHumidity();

        

        // Check if any reads failed and exit early
        if (isnan(temperature) || isnan(humidity)) {
            Serial.println("Failed to read from DHT sensor!");
            // Do NOT update globals on error; keep previous valid values
            vTaskDelay(1000);
            continue;
        }

        //Update global variables for temperature and humidity only if valid
        glob_temperature = temperature;
        glob_humidity = humidity;
        xSemaphoreGive(xBinarySemaphoreTemp_blinky);
        xSemaphoreGive(xBinarySemaphoreTemp_neo);
        xSemaphoreGive(xBinarySemaphoreTinyMLData);
        update_history(glob_temperature, glob_humidity);
        // Print the results
        lcd.setCursor(0,0);
        lcd.print("H: ");
        lcd.print(humidity);
        lcd.print("%");

        lcd.setCursor(0,1);

        lcd.print("T: ");
        lcd.print(temperature);
        lcd.println("C");
        
        vTaskDelay(5000);



    }
    
}