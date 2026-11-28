module fp_rounding #(
    parameter DAT_WIDTH = 24
) (
    input wire [DAT_WIDTH-1:0]  abs_value_i,
    input wire                  sign_i,
    input wire [1:0]            round_sticky_bits_i,
    input wire [2:0]            rnd_mode_i,
    input wire                  effective_subtraction_i,
    output wire [DAT_WIDTH-1:0] abs_rounded_o,
    output wire                 sign_o,
    output wire                 exact_zero_o
);

    localparam FRM_RNE = 3'b000;
    localparam FRM_RTZ = 3'b001;
    localparam FRM_RDN = 3'b010;
    localparam FRM_RUP = 3'b011;
    localparam FRM_RMM = 3'b100;

    reg round_up;

    always @(*) begin
        case (rnd_mode_i)
            FRM_RNE:
                case (round_sticky_bits_i)
                    2'b00,
                    2'b01: round_up = 1'b0;
                    2'b10: round_up = abs_value_i[0];
                    2'b11: round_up = 1'b1;
                endcase
            FRM_RTZ: round_up = 1'b0;
            FRM_RDN: round_up = (| round_sticky_bits_i) & sign_i;
            FRM_RUP: round_up = (| round_sticky_bits_i) & ~sign_i;
            FRM_RMM: round_up = round_sticky_bits_i[1];
            default:  round_up = 1'bx;
        endcase
    end

    assign abs_rounded_o = abs_value_i + round_up;

    assign exact_zero_o = (abs_value_i == 0) && (round_sticky_bits_i == 0);

    assign sign_o = (exact_zero_o && effective_subtraction_i) ? (rnd_mode_i == FRM_RDN)
                                                              : sign_i;

endmodule
