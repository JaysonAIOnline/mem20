// BureaucratPop.dsp
declare name "BureaucratPop";
declare version "1.0";
declare author "Jayson Audio Pipeline";

import("stdfaust.lib");

process = bureaucrat_pop;

// Sci-fi "stamp of approval" pop: a short percussive transient filtered at
// 200Hz feeding a low air resonance. Filters are applied sequentially (:).
bureaucrat_pop = (pop_transient * air_resonance) * gain
with {
  trigger = button("Trigger");

  pop_transient = trigger
    : en.adsr(0.001, 0.03, 0, 0.02)
    * (no.noise * 0.3 + os.osc(150) * 0.7)
    : fi.resonbp(200, 1.5, 1.0)
    * vslider("Transient Amount", 0.8, 0, 1, 0.01);

  air_resonance = trigger
    : en.adsr(0.01, 0.15, 0, 0.05)
    * (os.osc(80) * 0.5 + os.osc(160) * 0.3 + os.osc(320) * 0.2)
    * vslider("Air Amount", 0.6, 0, 1, 0.01);

  gain = vslider("Gain", 0.5, 0, 1, 0.01);
};