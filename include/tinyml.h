#ifndef __TINY_ML__
#define __TINY_ML__

#include <Arduino.h>

#include "global.h"
#include "naive_bayes_model.h"

void setupTinyML();
void tiny_ml_task(void *pvParameters);

#endif