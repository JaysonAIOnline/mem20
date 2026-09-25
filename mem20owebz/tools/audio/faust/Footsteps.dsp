// Footsteps.dsp - Bipedal footstep SFX for The Unreliable Prophecy
declare name "Footsteps";
declare version "1.0";
declare author "Jayson Audio Pipeline";

import("stdfaust.lib");

process = footstep_loop;

footstep_loop = (left_heel + right_heel) * gain
with {
  trigger = button("Trigger");

  // Each footfall: a low-frequency thud (hard attack, ~150ms decay) with a
  // touch of noise floor. Left and right alternate via a stepped delay.
  left_heel = trigger
    : en.adsr(0.002, 0.06, 0.0, 0.15)
    * (os.osc(95) * 0.6 + no.noise * 0.05)
    : fi.lowpass(1, 260)
    * vslider("Left Thud", 0.8, 0, 1, 0.01);

  // Right foot fires 0.42s later (stride length at walking pace).
  right_heel = trigger
    : de.delay(48000, 20160)
    : en.adsr(0.002, 0.06, 0.0, 0.15)
    * (os.osc(85) * 0.6 + no.noise * 0.05)
    : fi.lowpass(1, 240)
    * vslider("Right Thud", 0.8, 0, 1, 0.01);

  gain = vslider("Gain", 0.5, 0, 1, 0.01);
};