# scratch/run_eval.py
import sys
import os

# 将项目根目录加入 sys.path，以便导入 src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.evaluation import evaluate

if __name__ == "__main__":
    # 1. 准备约束
    my_constraints = {
        "liberty": "/home/jimmy/edatools/NangateOpenCellLibrary_typical.lib",
        "clock_period": 1.0,       # 1.0 ns = 1000 ps
        "top_module": "test_rtl",
        "report_dir": "scratch/reports/test_case"
    }
    
    # 2. RTL 路径
    rtl_file = "scratch/test_rtl.v"
    
    print("🚀 开始调用 Evaluate 接口...")
    res = evaluate(rtl_file, my_constraints)
    
    print("\n📊 评估结果:")
    for k, v in res.items():
        print(f"  - {k}: {v}")
