`timescale 1ps/1ps
module tb;
  reg clk;
  reg rst_n;
  reg i_en;
  reg [63:0] adda;
  reg [63:0] addb;
  wire [64:0] result;
  wire o_en;
  verified_adder_64bit dut(
    .clk(clk),
    .rst_n(rst_n),
    .i_en(i_en),
    .adda(adda),
    .addb(addb),
    .result(result),
    .o_en(o_en)
  );
  integer k;
  reg [31:0] rnd;
  initial begin
    $dumpfile("__VCD__");
    $dumpvars(1, dut);
    rnd = __SEED__;
    clk = 1'b0;
    rst_n = 1'b0;
    i_en = 1'b0;
    adda = 64'd0;
    addb = 64'd0;
    #10;
    rst_n = 1'b1;
    for (k = 0; k < 200; k = k + 1) begin
      rnd = (rnd * 1103515245 + 12345) & 32'hFFFFFFFF;
      adda[31:0] = rnd;
      rnd = (rnd * 1103515245 + 12345) & 32'hFFFFFFFF;
      adda[63:32] = rnd;
      rnd = (rnd * 1103515245 + 12345) & 32'hFFFFFFFF;
      addb[31:0] = rnd;
      rnd = (rnd * 1103515245 + 12345) & 32'hFFFFFFFF;
      addb[63:32] = rnd;
      i_en = (k[1:0] != 2'b11);
      #5; clk = 1'b1; #5; clk = 1'b0;
    end
    $finish;
  end
endmodule
