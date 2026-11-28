`timescale 1ps/1ps
module tb;
  reg [31:0] a;
  reg [31:0] b;
  wire [31:0] c;
  fixed_point_subtractor dut(.a(a), .b(b), .c(c));
  integer k;
  reg [31:0] rnd;
  initial begin
    $dumpfile("__VCD__");
    $dumpvars(1, dut);
    rnd = __SEED__;
    a = 32'd0;
    b = 32'd0;
    for (k = 0; k < 2000; k = k + 1) begin
      rnd = (rnd * 1103515245 + 12345) & 32'hFFFFFFFF;
      a = rnd;
      rnd = (rnd * 1103515245 + 12345) & 32'hFFFFFFFF;
      b = rnd;
      #10;
    end
    $finish;
  end
endmodule
