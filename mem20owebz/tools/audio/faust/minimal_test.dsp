// Minimal test
import("stdfaust.lib");
process = button("Trigger") : en.adsr(0.001, 0.02, 0, 0.01) * no.noise;