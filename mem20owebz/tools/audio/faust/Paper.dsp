// Paper.dsp
declare name "Paper";
declare version "1.0";
declare author "Jayson Audio Pipeline";

import("stdfaust.lib");

process = paper_rustle;

paper_rustle = no.noise
  * envelope
  * filter_bank
  * gain
with {
  trigger = button("Trigger");
  
  envelope = trigger
    : en.adsr(0.005, 0.05, 0.3, 0.1)
    * vslider("Envelope Amount", 1, 0, 1, 0.01);
  
  filter_bank = fi.highpass(1, 2000)
    * fi.lowpass(2, 8000)
    * fi.peak_eq(4000, 2, 6)
    * vslider("Filter Amount", 1, 0, 1, 0.01);
  
  gain = vslider("Gain", 0.3, 0, 1, 0.01);
};