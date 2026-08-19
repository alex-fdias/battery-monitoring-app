/*!
 * @file INA3221_read_send_UART.ino
 */
#include "Adafruit_INA3221.h"
#include <Wire.h>

#define DEBUG_TIMINGS // enable measuring I2C and UART timings and sending them
                      // through the UART

#define INA3221_ADDRESS 0x40

#define ENABLE_LED_OUTPUT // enable an LED turning on and off every
                          // LED_TOGGLE_TIME milliseconds
#ifdef ENABLE_LED_OUTPUT
#define LED_PIN 3
#define LED_TOGGLE_TIME 1000 // milliseconds
#endif

#define ITERATION_TIME 5000 // microseconds

// INA3221 object
Adafruit_INA3221 ina3221;

// channels 1 to 3 (equalizer, discharge, charge) resistance values
const float shunt_resistances[] = {0.005, 0.001, 0.010};

#ifdef DEBUG_TIMINGS
unsigned long t0, tmeas, tserial; // to time I2C and UART communication
#endif

#ifdef ENABLE_LED_OUTPUT
bool led_state = HIGH;
unsigned long t_led_activity;
#endif

unsigned long t_iter_start; // to time iteration time (loop)

void setup() {
  Serial.begin(115200);
  while (!Serial)
    delay(10); // Wait for serial port to connect on some boards

  // initialize the INA3221
  if (!ina3221.begin(INA3221_ADDRESS, &Wire)) {
    Serial.println("Failed to find INA3221 chip");
    while (1)
      delay(10);
  }
  Wire.setClock(1000000);

  Serial.println("INA3221 found!");

  // configure the INA3221
  ina3221.setBusVoltageConvTime(INA3221_CONVTIME_140US);
  ina3221.setShuntVoltageConvTime(INA3221_CONVTIME_140US);

  Serial.print(
      "Setting bus voltage and shunt voltage conversion times to 140us... ");
  if (ina3221.getBusVoltageConvTime() == INA3221_CONVTIME_140US &&
      ina3221.getShuntVoltageConvTime() == INA3221_CONVTIME_140US) {
    Serial.println("OK");
  }

  Serial.print("Disabling averaging mode... ");
  ina3221.setAveragingMode(INA3221_AVG_1_SAMPLE);
  if (ina3221.getAveragingMode() == INA3221_AVG_1_SAMPLE) {
    Serial.println("OK");
  }

  // Set shunt resistances for each channel
  for (uint8_t i = 0; i < 3; i++) {
    ina3221.setShuntResistance(i, shunt_resistances[i]);
  }

#ifdef ENABLE_LED_OUTPUT
  // initialize LED pin as a digital output and set the pin high
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, led_state);

  // variable to measure LED on and off times
  t_led_activity = millis();
#endif

  // variable to measure iteration time (loop)
  t_iter_start = micros();
}

void loop() {
  // wait until enough time has elapsed to begin the next iteration
  while (micros() - t_iter_start < ITERATION_TIME) {
  }

#ifdef DEBUG_TIMINGS
  tmeas = 0, tserial = 0;
#endif

  // read voltage (mV) and current (mA) for channels 1 to 3
  for (uint8_t i = 0; i < 3; i++) {
#ifdef DEBUG_TIMINGS
    t0 = micros();
#endif
    unsigned int voltage = ina3221.getBusVoltageMilliVolt(i);
    long current = ina3221.getCurrentMilliAmp(i);
#ifdef DEBUG_TIMINGS
    tmeas += micros() - t0;
#endif

#ifdef DEBUG_TIMINGS
    t0 = micros();
#endif
    Serial.print(i + 1);
    Serial.print(":");
    Serial.print(voltage);
    Serial.print(",");
    Serial.print(current);
    Serial.print(";");
#ifdef DEBUG_TIMINGS
    Serial.flush();
    tserial += micros() - t0;
#endif
  }
#ifdef DEBUG_TIMINGS
  t0 = micros();
#endif
  Serial.println();
#ifdef DEBUG_TIMINGS
  Serial.flush();
  tserial += micros() - t0;
#endif

#ifdef DEBUG_TIMINGS
  Serial.print("T:");
  Serial.print(tmeas);
  Serial.print(",");
  Serial.println(tserial);
  Serial.flush();
#endif

#ifdef ENABLE_LED_OUTPUT
  // toggle LED state if enough time (LED_TOGGLE_TIME milliseconds) has elapsed
  if (millis() - t_led_activity > LED_TOGGLE_TIME) {
    led_state = !led_state; // HIGH to LOW, LOW to HIGH
    digitalWrite(LED_PIN, led_state);

    t_led_activity += LED_TOGGLE_TIME;
  }
#endif

  t_iter_start += ITERATION_TIME;
}
