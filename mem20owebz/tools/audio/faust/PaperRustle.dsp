// PaperRustle.dsp
declare name "PaperRustle";
declare version "1.0";
declare author "Jayson Audio Pipeline";
declare license "MIT";
declare copyright "(c) 2026";

import("stdfaust.lib");

process = paper_rustle;

paper_rustle = noise_signal * envelope_amount * filter_amount * gain
with {
  trigger = button("Trigger");

  noise_signal = trigger
    : en.adsr(0.005, 0.05, 0.3, 0.1)
    * no.noise
    : fi.highpass(1, 2000)
    : fi.lowpass(1, 8000)
    : fi.peak_eq(4000, 2, 6);

  envelope_amount = vslider("Envelope Amount", 1, 0, 1, 0.01);
  filter_amount = vslider("Filter Amount", 1, 0, 1, 0.01);
  gain = vslider("Gain", 0.3, 0, 1, 0.01);
};