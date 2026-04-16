#include "tinyml.h"

#include <float.h>
#include <math.h>
#include <string.h>

namespace
{
    constexpr TickType_t kInferencePeriodTicks = pdMS_TO_TICKS(5000);
    constexpr float kPi = 3.14159265358979323846f;

    // Set to 1 to test with fixed values instead of live sensor values.
#ifndef TINYML_USE_FIXED_INPUT
#define TINYML_USE_FIXED_INPUT 0
#endif

#ifndef TINYML_FIXED_TEMP
#define TINYML_FIXED_TEMP 29.5f
#endif

#ifndef TINYML_FIXED_HUMI
#define TINYML_FIXED_HUMI 65.0f
#endif

    bool has_ground_truth = false;
    int ground_truth_label = 0;
    uint32_t eval_total = 0;
    uint32_t eval_correct = 0;
    float class_scores[NB_NUM_CLASSES] = {0.0f};
    float class_probs[NB_NUM_CLASSES] = {0.0f};

    int argmax(const float *values, int count)
    {
        if (values == nullptr || count <= 0)
        {
            return 0;
        }

        int best_idx = 0;
        float best_val = values[0];
        for (int i = 1; i < count; ++i)
        {
            if (values[i] > best_val)
            {
                best_val = values[i];
                best_idx = i;
            }
        }
        return best_idx;
    }

    void normalizeInput(float temperature, float humidity, float normalized[NB_NUM_FEATURES])
    {
        const float raw[NB_NUM_FEATURES] = {temperature, humidity};
        for (int j = 0; j < NB_NUM_FEATURES; ++j)
        {
            const float denom = fabsf(kNbFeatureStd[j]) > 1e-8f ? kNbFeatureStd[j] : 1.0f;
            normalized[j] = (raw[j] - kNbFeatureMean[j]) / denom;
        }
    }

    void runNaiveBayes(float temperature, float humidity)
    {
        float x_norm[NB_NUM_FEATURES] = {0.0f};
        normalizeInput(temperature, humidity, x_norm);

        float max_score = -FLT_MAX;
        for (int c = 0; c < NB_NUM_CLASSES; ++c)
        {
            float score = logf(fmaxf(kNbClassPrior[c], kNbEpsilon));

            for (int j = 0; j < NB_NUM_FEATURES; ++j)
            {
                const float var = fmaxf(kNbVariance[c][j], kNbEpsilon);
                const float diff = x_norm[j] - kNbTheta[c][j];
                score += -0.5f * logf(2.0f * kPi * var);
                score += -0.5f * (diff * diff / var);
            }

            class_scores[c] = score;
            if (score > max_score)
            {
                max_score = score;
            }
        }

        float prob_sum = 0.0f;
        for (int c = 0; c < NB_NUM_CLASSES; ++c)
        {
            class_probs[c] = expf(class_scores[c] - max_score);
            prob_sum += class_probs[c];
        }

        if (prob_sum > 0.0f)
        {
            for (int c = 0; c < NB_NUM_CLASSES; ++c)
            {
                class_probs[c] /= prob_sum;
            }
        }
    }



    void tryUpdateGroundTruthFromSerial()
    {
        if (!Serial.available())
        {
            return;
        }

        char line[32];
        size_t len = Serial.readBytesUntil('\n', line, sizeof(line) - 1);
        line[len] = '\0';

        int gt = -1;
        if (sscanf(line, "gt %d", &gt) == 1)
        {
            if (gt >= 0)
            {
                ground_truth_label = gt;
                has_ground_truth = true;
                Serial.print("[TinyML] Ground truth updated: ");
                Serial.println(ground_truth_label);
                return;
            }
        }

        if (strcmp(line, "gt off") == 0)
        {
            has_ground_truth = false;
            Serial.println("[TinyML] Ground truth disabled");
            return;
        }

        if (strcmp(line, "eval reset") == 0)
        {
            eval_total = 0;
            eval_correct = 0;
            Serial.println("[TinyML] Evaluation counters reset");
            return;
        }
    }

    void printEvalHint()
    {
        Serial.println("[TinyML] Eval commands:");
        Serial.println("[TinyML]   gt <label>    -> set ground-truth label");
        Serial.println("[TinyML]   label range   -> 0..4");
        Serial.println("[TinyML]   gt off        -> disable ground-truth compare");
        Serial.println("[TinyML]   eval reset    -> clear accuracy counters");
    }
} // namespace

void setupTinyML()
{
    Serial.println("[TinyML] Naive Bayes model init...");
    Serial.print("[TinyML] classes=");
    Serial.print(NB_NUM_CLASSES);
    Serial.print(" features=");
    Serial.println(NB_NUM_FEATURES);

    Serial.println("[TinyML] labels:");
    for (int i = 0; i < NB_NUM_CLASSES; ++i)
    {
        Serial.print("[TinyML]   ");
        Serial.print(i);
        Serial.print(" -> ");
        Serial.println(kNbLabels[i]);
    }

    printEvalHint();
    Serial.println("[TinyML] Naive Bayes ready on ESP32.");
}

void tiny_ml_task(void *pvParameters)
{
    setupTinyML();

    while (1)
    {
        tryUpdateGroundTruthFromSerial();

        // Wait for valid sensor data signal from temp_humi_monitor task
        if (xSemaphoreTake(xBinarySemaphoreTinyMLData, pdMS_TO_TICKS(10000)) != pdTRUE)
        {
            continue;
        }

        const float temperature = TINYML_USE_FIXED_INPUT ? TINYML_FIXED_TEMP : glob_temperature;
        const float humidity = TINYML_USE_FIXED_INPUT ? TINYML_FIXED_HUMI : glob_humidity;

        // Skip if values look invalid (safety check)
        if (temperature < -50.0f || temperature > 100.0f ||
            humidity < 0.0f || humidity > 100.0f)
        {
            continue;
        }

        runNaiveBayes(temperature, humidity);
        const int predicted_label = argmax(class_probs, NB_NUM_CLASSES);

        // Output: sensor input and predicted label
        Serial.print("T=");
        Serial.print(temperature, 2);
        Serial.print(" H=");
        Serial.print(humidity, 2);
        Serial.print(" | Label=");
        Serial.println(kNbLabels[predicted_label]);

        if (has_ground_truth)
        {
            ++eval_total;
            if (predicted_label == ground_truth_label)
            {
                ++eval_correct;
            }
        }

        vTaskDelay(kInferencePeriodTicks);
    }
}