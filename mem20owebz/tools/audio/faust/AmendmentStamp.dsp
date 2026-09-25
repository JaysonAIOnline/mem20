// AmendmentStamp.dsp
declare name "AmendmentStamp";
declare version "1.0";
declare author "Jayson Audio Pipeline";

import("stdfaust.lib");

process = amendment_stamp;

// Official document stamp: low 60Hz thud, paper crinkle highpass, small
// reverb tail. mono_freeverb(fb1, fb2, damp, spread) is a 1in/1out mono verb.
amendment_stamp = (thud_crinkle : reverbed) * gain
with {
  trigger = button("Trigger");

  thud = trigger
    : en.adsr(0.001, 0.15, 0, 0.05)
    * (os.osc(60) * 0.6 + os.osc(120) * 0.4)
    : fi.lowpass(1, 200)
    * vslider("Thud Amount", 0.9, 0, 1, 0.01);

  crinkle = trigger
    : en.adsr(0.005, 0.05, 0, 0.02)
    * no.noise
    : fi.highpass(1, 3000)
    : fi.peak_eq(5000, 2, 8)
    * vslider("Crinkle Amount", 0.7, 0, 1, 0.01);

  thud_crinkle = thud + crinkle;

  reverbed = _ : re.mono_freeverb(0.3, 0.7, 0.25, 30)
    * vslider("Reverb Mix", 0.2, 0, 1, 0.01);

  gain = vslider("Gain", 0.7, 0, 1, 0.01);
};