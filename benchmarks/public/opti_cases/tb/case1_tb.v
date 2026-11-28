`timescale 1ps/1ps
module tb;
  reg [7:0] in;
  reg [2:0] ctrl;
  wire [7:0] out;
  barrel_shifter dut(.in(in), .ctrl(ctrl), .out(out));
  integer k;
  reg [31:0] rnd;
  initial begin
    $dumpfile("__VCD__");
    $dumpvars(1, dut);
    rnd = __SEED__;
    in = 8'd0;
    ctrl = 3'd0;
    for (k = 0; k < 2000; k = k + 1) begin
      rnd = (rnd * 1103515245 + 12345) & 32'hFFFFFFFF;
      in = rnd[7:0];
      ctrl = rnd[10:8];
      #10;
    end
    $finish;
  end
endmodule
