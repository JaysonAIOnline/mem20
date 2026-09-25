// test_adsr_filter.dsp
import("stdfaust.lib");
process = button("Trigger") : en.adsr(0.001, 0.02, 0, 0.01) * no.noise * fi.highpass(1, 2000) * fi.lowpass(2, 12000);