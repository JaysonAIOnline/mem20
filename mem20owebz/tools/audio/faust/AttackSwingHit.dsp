// AttackSwingHit.dsp
declare name "AttackSwingHit";
declare version "1.0";
declare author "Jayson Audio Pipeline";

import("stdfaust.lib");

process = attack_swing_hit;

// Melee swing (noise whoosh resonating at 2kHz) plus a lower impact thud.
attack_swing_hit = (swing_whoosh + impact_hit) * gain
with {
  trigger = button("Trigger");

  swing_whoosh = trigger
    : en.adsr(0, 0.4, 0, 0.02)
    * (no.noise * 0.6 + os.osc(300) * 0.4)
    : fi.resonbp(2000, 0.7, 1.0)
    * vslider("Swing Amount", 0.7, 0, 1, 0.01);

  impact_hit = trigger
    : en.adsr(0.001, 0.05, 0, 0.02)
    * (no.noise * 0.5 + os.osc(300) * 0.5)
    : fi.resonbp(500, 2, 1.0)
    * vslider("Impact Amount", 0.9, 0, 1, 0.01);

  gain = vslider("Gain", 0.7, 0, 1, 0.01);
};