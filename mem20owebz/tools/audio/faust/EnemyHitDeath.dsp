// EnemyHitDeath.dsp
declare name "EnemyHitDeath";
declare version "1.0";
declare author "Jayson Audio Pipeline";

import("stdfaust.lib");

process = enemy_hit_death;

// Crunchy impact transient followed by a longer dissipating low rumble.
enemy_hit_death = (crunch * dissipation) * gain
with {
  trigger = button("Trigger");

  crunch = trigger
    : en.adsr(0.001, 0.08, 0, 0.02)
    * (no.noise * 0.7 + os.osc(200) * 0.3)
    : fi.highpass(1, 500)
    : fi.lowpass(1, 6000)
    * vslider("Crunch Amount", 0.8, 0, 1, 0.01);

  dissipation = trigger
    : en.adsr(0.01, 0.3, 0, 0.1)
    * (no.noise * 0.4 + os.osc(100) * 0.6)
    : fi.lowpass(1, 2000)
    * vslider("Dissipation Amount", 0.5, 0, 1, 0.01);

  gain = vslider("Gain", 0.6, 0, 1, 0.01);
};