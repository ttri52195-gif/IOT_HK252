#include "coreiot.h"

// ----------- CONFIGURE THESE! -----------
const char* coreIOT_Server = "app.coreiot.io";  
const char* coreIOT_Token = "iM6zlejTDaThdGlxgD9t";   // Device Access Token
const int   mqttPort = 1883;
// ----------------------------------------

WiFiClient espClient;
PubSubClient client(espClient);

void reconnect() {
  // Vòng lặp kết nối MQTT
  while (!client.connected()) {
    // Nếu đột ngột mất Wi-Fi do mainserver báo, thoát ngay để không bị treo Task
    if (!isWifiConnected) {
        return; 
    }

    Serial.print("[CoreIoT] Attempting MQTT connection...");
    if (client.connect("ESP32Client", coreIOT_Token, NULL)) {
      Serial.println("connected to CoreIOT Server!");
      client.subscribe("v1/devices/me/rpc/request/+");
      Serial.println("[CoreIoT] Subscribed to v1/devices/me/rpc/request/+");
    } else {
      Serial.print("[CoreIoT] failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      vTaskDelay(pdMS_TO_TICKS(5000));
    }
  }
}

void callback(char* topic, byte* payload, unsigned int length) {
  char message[length + 1];
  memcpy(message, payload, length);
  message[length] = '\0';

  StaticJsonDocument<256> doc;
  DeserializationError error = deserializeJson(doc, message);

  if (error) {
    Serial.println("deserializeJson() failed");
    return;
  }

  const char* method = doc["method"];
  
  if (strcmp(method, "setStateLED") == 0) {
    const char* params = doc["params"];
    if (strcmp(params, "ON") == 0) {
      Serial.println("Device turned ON.");
    } else {   
      Serial.println("Device turned OFF.");
    }
  } 
  // BẮT SỰ KIỆN TỪ SLIDER TRÊN THINGSBOARD
  else if (strcmp(method, "setThre") == 0) {
    float new_threshold = doc["params"];
    glob_temp_threshold = new_threshold;
    Serial.print("[CoreIoT] Da cap nhat nguong nhiet do moi: ");
    Serial.println(glob_temp_threshold);
  } 
  else {
    Serial.print("Unknown method: ");
    Serial.println(method);
  }
}

void setup_coreiot(){
  // KHÔNG GỌI WiFi.begin() Ở ĐÂY NỮA
  client.setServer(coreIOT_Server, mqttPort);
  client.setCallback(callback);
}

void coreiot_task(void *pvParameters){
    setup_coreiot();

    while(1){
        // Chờ mainserver kết nối Wi-Fi xong
        if (!isWifiConnected) {
            vTaskDelay(pdMS_TO_TICKS(2000));
            continue;
        }

        if (!client.connected()) {
            reconnect();
        }
        
        if (client.connected()) {
            client.loop();

            // Gửi cả nhiệt độ, độ ẩm VÀ ngưỡng hiện tại lên web để đồng bộ Slider
            String payload = "{\"temperature\":" + String(glob_temperature, 2) +  
                             ",\"humidity\":" + String(glob_humidity, 2) + 
                             ",\"tempThreshold\":" + String(glob_temp_threshold, 2) + "}";
client.publish("v1/devices/me/telemetry", payload.c_str());
            Serial.println("[CoreIoT] Published: " + payload);
        }

        vTaskDelay(pdMS_TO_TICKS(1000));  
    }
}