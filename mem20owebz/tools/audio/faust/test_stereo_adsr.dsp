// Test with explicit stereo output
import("stdfaust.lib");
process = button("Trigger") <: _,_ : en.adsr(0.001, 0.02, 0, 0.01) * no.noise;