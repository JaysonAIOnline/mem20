// StampImpact.dsp - Simplified working version
declare name "StampImpact";
declare version "1.0";
declare author "Jayson Audio Pipeline";

import("stdfaust.lib");

process = stamp_impact;

stamp_impact = noise_burst * gain
with {
  trigger = button("Trigger");
  
  noise_burst = trigger
    : en.adsr(0.001, 0.02, 0, 0.01)
    * no.noise
    * vslider("Noise Amount", 0.5, 0, 1, 0.01);
  
  gain = vslider("Gain", 0.6, 0, 1, 0.01);
};