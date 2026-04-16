#ifndef NAIVE_BAYES_MODEL_H
#define NAIVE_BAYES_MODEL_H

#define NB_NUM_CLASSES 5
#define NB_NUM_FEATURES 2

static const char* kNbLabels[NB_NUM_CLASSES] = {"Không hợp lệ", "Bật điều hòa", "Bật máy hút ẩm", "Bật máy sưởi", "Chế độ bình thường"};
static const float kNbFeatureMean[NB_NUM_FEATURES] = {39.75828171f, 49.13862228f};
static const float kNbFeatureStd[NB_NUM_FEATURES] = {34.49666595f, 28.52767754f};
static const float kNbClassPrior[NB_NUM_CLASSES] = {0.16728856f, 0.17226368f, 0.09266169f, 0.19527363f, 0.37251244f};
static const float kNbEpsilon = 0.0000000010f;

static const float kNbTheta[NB_NUM_CLASSES][NB_NUM_FEATURES] = {
    {-1.44440043f, -0.00301485f},
    {0.75999415f, 0.58084267f},
    {0.73739284f, 1.44497454f},
    {-0.81158721f, 0.02227719f},
    {0.53921878f, -0.63835961f}
};

static const float kNbVariance[NB_NUM_CLASSES][NB_NUM_FEATURES] = {
    {0.02935677f, 0.96854228f},
    {0.32150364f, 0.08705299f},
    {0.30282542f, 0.03948113f},
    {0.03841082f, 1.05831516f},
    {0.45184255f, 0.56150800f}
};

// Runtime formula on ESP32:
// 1) normalize input: x_norm[j] = (x[j] - kNbFeatureMean[j]) / kNbFeatureStd[j]
// 2) score[class] = log(prior) - 0.5 * sum(log(2*pi*var)) - 0.5 * sum((x_norm-theta)^2 / var)
// 3) choose argmax(score)
#endif
