// Test with si.smoo and explicit stereo handling
import("stdfaust.lib");
process = button("Trigger") : si.smoo <: _,_ : en.adsr(0.001, 0.02, 0, 0.01) * no.noise;