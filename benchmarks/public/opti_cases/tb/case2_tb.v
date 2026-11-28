`timescale 1ps/1ps
module tb;
  reg [23:0] abs_value_i;
  reg sign_i;
  reg [1:0] round_sticky_bits_i;
  reg [2:0] rnd_mode_i;
  reg effective_subtraction_i;
  wire [23:0] abs_rounded_o;
  wire sign_o;
  wire exact_zero_o;
  fp_rounding dut(
    .abs_value_i(abs_value_i),
    .sign_i(sign_i),
    .round_sticky_bits_i(round_sticky_bits_i),
    .rnd_mode_i(rnd_mode_i),
    .effective_subtraction_i(effective_subtraction_i),
    .abs_rounded_o(abs_rounded_o),
    .sign_o(sign_o),
    .exact_zero_o(exact_zero_o)
  );
  integer k;
  reg [31:0] rnd;
  initial begin
    $dumpfile("__VCD__");
    $dumpvars(1, dut);
    rnd = __SEED__;
    abs_value_i = 24'd0;
    sign_i = 1'b0;
    round_sticky_bits_i = 2'd0;
    rnd_mode_i = 3'd0;
    effective_subtraction_i = 1'b0;
    for (k = 0; k < 2000; k = k + 1) begin
      rnd = (rnd * 1103515245 + 12345) & 32'hFFFFFFFF;
      abs_value_i = rnd[23:0];
      sign_i = rnd[24];
      round_sticky_bits_i = rnd[26:25];
      // modes 3'b000..3'b100 are defined; 101/110/111 assign X
      rnd_mode_i = rnd[29:27];
      if (rnd_mode_i > 3'd4)
        rnd_mode_i = rnd_mode_i - 3'd3;
      effective_subtraction_i = rnd[30];
      #10;
    end
    $finish;
  end
endmodule
