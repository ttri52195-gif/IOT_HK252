#include "temp_humi_monitor.h"

DHT20 dht20;
LiquidCrystal_I2C lcd(0x27, 16, 2);

void temp_humi_monitor(void *pvParameters)
{
    Wire.begin(11, 12);
    Wire.setClock(100000);

    dht20.begin();

    lcd.begin();
    lcd.backlight();

    TickType_t lastSensorRead = 0;
    TickType_t lastBlink = 0;

    bool warningBlinkState = false;
    bool wasWarning = false;

    while (1)
    {
        TickType_t now = xTaskGetTickCount();

        if (now - lastSensorRead >= pdMS_TO_TICKS(1000))
        {
            lastSensorRead = now;

            bool valid = false;

            for (int i = 0; i < 3; i++)
            {
                dht20.read();
                float t = dht20.getTemperature();
                float h = dht20.getHumidity();

                if (!isnan(t) && !isnan(h))
                {
                    glob_temperature = t;
                    glob_humidity = h;
                    valid = true;
                    break;
                }
                vTaskDelay(pdMS_TO_TICKS(50));
            }

            if (valid)
            {
                xSemaphoreGive(xBinarySemaphoreTemp_blinky);
                xSemaphoreGive(xBinarySemaphoreTemp_neo);
                xSemaphoreGive(xBinarySemaphoreTinyMLData);

                update_history(glob_temperature, glob_humidity);
            }
            else
            {
                Serial.println("DHT20 read failed!");
            }
        }

        // ================== 2. DISPLAY ==================
        if (glob_temperature > glob_temp_threshold)
        {
            // Vừa chuyển sang WARNING
            if (!wasWarning)
            {
                lcd.clear();
                wasWarning = true;
                warningBlinkState = true;
                lastBlink = now;
            }

            // Blink không block
            if (now - lastBlink >= pdMS_TO_TICKS(500))
            {
                lastBlink = now;
                warningBlinkState = !warningBlinkState;

                lcd.setCursor(0, 0);
                if (warningBlinkState)
                    lcd.print("! WARNING TEMP !");
                else
                    lcd.print("                "); // clear dòng
            }

            // Dòng dưới luôn hiển thị nhiệt độ
            lcd.setCursor(0, 1);
            lcd.print("T:");
            lcd.print(glob_temperature, 1);
            lcd.print("C   ");
        }
        else
        {
            // Thoát WARNING → clear 1 lần
            if (wasWarning)
            {
                lcd.clear();
                wasWarning = false;
            }

            lcd.setCursor(0, 0);
            lcd.print("H:");
            lcd.print(glob_humidity, 1);
            lcd.print("%   ");

            lcd.setCursor(0, 1);
            lcd.print("T:");
            lcd.print(glob_temperature, 1);
            lcd.print("C   ");
        }

        vTaskDelay(pdMS_TO_TICKS(100)); 
    }
}