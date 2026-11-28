`timescale 1ps/1ps
module tb;
  reg clk;
  reg rst;
  reg [7:0] dividend;
  reg [7:0] divisor;
  reg sign;
  reg opn_valid;
  wire res_valid;
  reg res_ready;
  wire [15:0] result;
  verified_radix2_div dut(
    .clk(clk),
    .rst(rst),
    .dividend(dividend),
    .divisor(divisor),
    .sign(sign),
    .opn_valid(opn_valid),
    .res_valid(res_valid),
    .res_ready(res_ready),
    .result(result)
  );
  integer k, cyc;
  reg [31:0] rnd;
  initial begin
    $dumpfile("__VCD__");
    $dumpvars(1, dut);
    rnd = __SEED__;
    clk = 1'b0;
    rst = 1'b1;
    dividend = 8'd0;
    divisor = 8'd1;
    sign = 1'b0;
    opn_valid = 1'b0;
    res_ready = 1'b0;
    repeat (2) begin #5; clk = 1'b1; #5; clk = 1'b0; end
    rst = 1'b0;
    for (k = 0; k < 40; k = k + 1) begin
      rnd = (rnd * 1103515245 + 12345) & 32'hFFFFFFFF;
      dividend = rnd[7:0];
      divisor = rnd[15:8] | 8'h1;
      sign = rnd[16];
      opn_valid = 1'b1;
      res_ready = 1'b0;
      #5; clk = 1'b1; #5; clk = 1'b0;
      opn_valid = 1'b0;
      for (cyc = 0; cyc < 16 && !res_valid; cyc = cyc + 1) begin
        #5; clk = 1'b1; #5; clk = 1'b0;
      end
      res_ready = 1'b1;
      #5; clk = 1'b1; #5; clk = 1'b0;
      res_ready = 1'b0;
      #5; clk = 1'b1; #5; clk = 1'b0;
    end
    $finish;
  end
endmodule
