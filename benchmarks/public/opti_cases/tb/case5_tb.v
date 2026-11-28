`timescale 1ps/1ps
module tb;
  reg clk;
  reg rst_n;
  reg [7:0] data_in;
  reg valid_in;
  wire valid_out;
  wire [9:0] data_out;
  verified_accu dut(
    .clk(clk),
    .rst_n(rst_n),
    .data_in(data_in),
    .valid_in(valid_in),
    .valid_out(valid_out),
    .data_out(data_out)
  );
  integer k;
  reg [31:0] rnd;
  initial begin
    $dumpfile("__VCD__");
    $dumpvars(1, dut);
    rnd = __SEED__;
    clk = 1'b0;
    rst_n = 1'b0;
    data_in = 8'd0;
    valid_in = 1'b0;
    #10;
    rst_n = 1'b1;
    for (k = 0; k < 800; k = k + 1) begin
      rnd = (rnd * 1103515245 + 12345) & 32'hFFFFFFFF;
      data_in = rnd[7:0];
      valid_in = rnd[8];
      #5; clk = 1'b1; #5; clk = 1'b0;
    end
    $finish;
  end
endmodule
