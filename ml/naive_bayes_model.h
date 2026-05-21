#ifndef NAIVE_BAYES_MODEL_H
#define NAIVE_BAYES_MODEL_H

#define NB_NUM_CLASSES 5
#define NB_NUM_FEATURES 2

static const char* kNbLabels[NB_NUM_CLASSES] = {"Không hợp lệ", "Bật điều hòa", "Bật máy hút ẩm", "Bật máy sưởi", "Chế độ bình thường"};
static const float kNbFeatureMean[NB_NUM_FEATURES] = {47.47549438f, 50.59525681f};
static const float kNbFeatureStd[NB_NUM_FEATURES] = {30.24046898f, 63.27154541f};
static const float kNbClassPrior[NB_NUM_CLASSES] = {0.03327561f, 0.51410193f, 0.12110341f, 0.23268184f, 0.09883721f};
static const float kNbEpsilon = 0.0000000010f;

static const float kNbTheta[NB_NUM_CLASSES][NB_NUM_FEATURES] = {
    {-1.89139140f, 0.31594387f},
    {0.61935133f, -0.16294993f},
    {0.65841621f, 0.62023681f},
    {-1.17363048f, -0.00389157f},
    {-0.62857133f, -0.00960235f}
};

static const float kNbVariance[NB_NUM_CLASSES][NB_NUM_FEATURES] = {
    {0.04825145f, 24.00452232f},
    {0.40275467f, 0.13679634f},
    {0.41622442f, 0.00825470f},
    {0.05127535f, 0.20749274f},
    {0.00715865f, 0.18269143f}
};

// Runtime formula on ESP32:
// 1) normalize input: x_norm[j] = (x[j] - kNbFeatureMean[j]) / kNbFeatureStd[j]
// 2) score[class] = log(prior) - 0.5 * sum(log(2*pi*var)) - 0.5 * sum((x_norm-theta)^2 / var)
// 3) choose argmax(score)
#endif
