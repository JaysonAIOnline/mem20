// Test with si.smoo converted to mono
import("stdfaust.lib");
process = button("Trigger") : si.smoo : *(no.noise) : fi.highpass(1, 2000) * fi.lowpass(2, 12000);