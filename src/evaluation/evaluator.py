# src/evaluation/evaluator.py
import os
import re
import signal
from pyosys import libyosys as ys

# 简单的超时控制类（防止大模型写了死循环卡死）
class TimeoutError(Exception): pass
def timeout_handler(signum, frame):
    raise TimeoutError("Yosys 运行超时")

def evaluate(rtl: str, constraints: dict) -> dict:
    """
    综合评估接口
    """
    # 1. 初始化兜底返回值
    result = {
        "status": "error",
        "area": None,
        "delay": None,
        "timing_met": None,
        "report_path": None
    }

    # 2. 解析参数
    lib = constraints.get("liberty")
    clock_ns = constraints.get("clock_period")
    top_module = constraints.get("top_module")
    report_dir = constraints.get("report_dir", "reports")
    
    if not lib or not os.path.exists(lib):
        print(f"[Evaluate] Error: Liberty file not found at {lib}")
        return result
    
    # 单位统一转为 ps
    period_ps = int(clock_ns * 1000) if clock_ns else None

    # 3. 准备报告目录
    os.makedirs(report_dir, exist_ok=True)
    stat_log = os.path.join(report_dir, "stat.log")
    ltp_log = os.path.join(report_dir, "ltp.log")

    # 设置 60 秒超时
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(60)

    try:
        design = ys.Design()
        
        # --- 综合流程 ---
        ys.run_pass(f"read_verilog {rtl}", design)
        if top_module:
            ys.run_pass(f"hierarchy -check -top {top_module}", design)
        else:
            ys.run_pass("hierarchy -check -auto-top", design)
            
        ys.run_pass("proc; opt; memory; opt", design)
        
        ys.run_pass("techmap; opt", design) 
        
        # 工艺映射
        ys.run_pass(f"read_liberty -lib {lib}", design)
        ys.run_pass(f"dfflibmap -liberty {lib}", design)
        ys.run_pass("opt", design)
        
        if period_ps:
            ys.run_pass(f"abc -liberty {lib} -D {period_ps}", design)
        else:
            ys.run_pass(f"abc -liberty {lib}", design)
        ys.run_pass("clean", design)

        # --- 提取面积 ---
        ys.run_pass(f"tee -o {stat_log} stat -liberty {lib}", design)
        with open(stat_log) as f:
            m_area = re.search(r"Chip area for module\s+'.*?':\s*([\d.]+)", f.read())
            if m_area:
                result["area"] = float(m_area.group(1))

        # --- 提取延时 ---
        ys.run_pass("flatten", design)
        ys.run_pass(f"tee -o {ltp_log} ltp -noff", design)
        with open(ltp_log) as f:
            m_delay = re.search(r"Longest topological path.*?length\s*=\s*([\d.]+)", f.read())
            if m_delay:
                result["delay"] = float(m_delay.group(1))

        # --- 判断逻辑 ---
        if result["area"] is not None:
            result["status"] = "success"
            result["report_path"] = stat_log  # 这里先用 stat_log 作为报告

            if result["delay"] is not None and period_ps:
                result["timing_met"] = (result["delay"] <= period_ps)

    except TimeoutError:
        result["status"] = "timeout"
        print("[Evaluate] Timeout!")
    except Exception as e:
        print(f"[Evaluate] Yosys Error: {str(e)}")
        result["status"] = "error"
    finally:
        signal.alarm(0) # 取消定时器

    return result
