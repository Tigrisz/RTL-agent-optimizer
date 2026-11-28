`timescale 1ps/1ps
module tb;
  reg [3:0] dataIn;
  reg RW;
  reg EN;
  reg Rst;
  reg clk;
  wire EMPTY;
  wire FULL;
  wire [3:0] dataOut;
  LIFObuffer dut(
    .dataIn(dataIn),
    .RW(RW),
    .EN(EN),
    .Rst(Rst),
    .clk(clk),
    .EMPTY(EMPTY),
    .FULL(FULL),
    .dataOut(dataOut)
  );
  integer n, k;
  reg [31:0] rnd;
  initial begin
    $dumpfile("__VCD__");
    $dumpvars(1, dut);
    rnd = __SEED__;
    clk = 1'b0;
    EN = 1'b1;
    Rst = 1'b1;
    RW = 1'b0;
    dataIn = 4'd0;
    repeat (2) begin #5; clk = 1'b1; #5; clk = 1'b0; end
    Rst = 1'b0;
    for (n = 0; n < 40; n = n + 1) begin
      for (k = 0; k < 4; k = k + 1) begin
        rnd = (rnd * 1103515245 + 12345) & 32'hFFFFFFFF;
        dataIn = rnd[3:0];
        RW = 1'b0;
        #5; clk = 1'b1; #5; clk = 1'b0;
      end
      for (k = 0; k < 4; k = k + 1) begin
        RW = 1'b1;
        #5; clk = 1'b1; #5; clk = 1'b0;
      end
    end
    $finish;
  end
endmodule
