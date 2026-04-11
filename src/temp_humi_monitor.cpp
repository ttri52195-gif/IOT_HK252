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
            temperature = humidity =  -1;
            //return;
        }

        //Update global variables for temperature and humidity
        glob_temperature = temperature;
        glob_humidity = humidity;
        xSemaphoreGive(xBinarySemaphoreTemp_blinky);
        xSemaphoreGive(xBinarySemaphoreTemp_neo);
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