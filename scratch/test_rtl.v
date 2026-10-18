module test_rtl (
    input clk,
    input [7:0] a, b,
    output reg [7:0] sum
);
    always @(posedge clk) begin
        sum <= a + b;
    end
endmodule
