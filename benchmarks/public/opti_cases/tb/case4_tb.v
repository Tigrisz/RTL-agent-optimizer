`timescale 1ps/1ps
module tb;
  reg [15:0] A;
  reg [7:0] B;
  wire [15:0] result;
  wire [15:0] odd;
  div_16bit dut(.A(A), .B(B), .result(result), .odd(odd));
  integer k;
  reg [31:0] rnd;
  initial begin
    $dumpfile("__VCD__");
    $dumpvars(1, dut);
    rnd = __SEED__;
    A = 16'd0;
    B = 8'd1;
    for (k = 0; k < 2000; k = k + 1) begin
      rnd = (rnd * 1103515245 + 12345) & 32'hFFFFFFFF;
      A = rnd[15:0];
      B = rnd[23:16];
      if (rnd[27:24] == 4'd0)
        B = 8'd0;
      #10;
    end
    $finish;
  end
endmodule
