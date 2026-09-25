// Test with si.smoo for stereo conversion
import("stdfaust.lib");
process = button("Trigger") : si.smoo : en.adsr(0.001, 0.02, 0, 0.01) * no.noise;