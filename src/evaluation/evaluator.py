import subprocess
import tempfile
import os
import re
import time
import logging
from pathlib import Path
from dotenv import load_dotenv

# --- 环境配置加载 ---
_project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(_project_root / ".env")
load_dotenv(_project_root / "tools.env", override=True)

YOSYS_BIN = os.getenv("YOSYS_BIN")
LIBERTY_FILE = os.getenv("LIB_FILE")

if not YOSYS_BIN or not Path(YOSYS_BIN).exists():
    raise RuntimeError(f"Yosys 路径未正确配置 (tools.env -> YOSYS_BIN): {YOSYS_BIN}")
if not LIBERTY_FILE or not Path(LIBERTY_FILE).exists():
    raise RuntimeError(f"Liberty 文件路径未正确配置 (tools.env -> LIBERTY_FILE): {LIBERTY_FILE}")

logger = logging.getLogger(__name__)

def evaluate(rtl_path: str, constraints: dict) -> dict:
    """
    模块 C：调用 Yosys 评估 RTL 的面积和逻辑深度。
    """
    start_time = time.time()
    
    delay_limit = constraints.get("delay_limit") if constraints else None
    
    top_module = None
    try:
        rtl_content = Path(rtl_path).read_text()
        # 匹配 module 后面的第一个单词作为模块名
        match = re.search(r"module\s+(\w+)", rtl_content)
        if match:
            top_module = match.group(1)
        else:
            # 如果正则没匹配到，说明代码可能被改坏了，或者不是合法的 Verilog
            logger.error(f"无法从 RTL 文件中解析出模块名: {rtl_path}")
            return {"status": "error", "area": None, "delay": None, "timing_met": None}
    except Exception as e:
        logger.error(f"读取 RTL 文件失败: {e}")
        return {"status": "error", "area": None, "delay": None, "timing_met": None}

    with tempfile.TemporaryDirectory() as tmpdir:
        ys_script = Path(tmpdir) / "run.ys"
        
        # 使用从环境变量读取的 LIBERTY_FILE
        yosys_script_content = f"""
        read_liberty -ignore_miss_func {LIBERTY_FILE}
        read_verilog -sv {rtl_path}
        
        synth -top {top_module} -flatten
        
        ltp -noff
        
        dfflibmap -liberty {LIBERTY_FILE}
        abc -liberty {LIBERTY_FILE}
        
        stat -liberty {LIBERTY_FILE}
        """
        ys_script.write_text(yosys_script_content)

        try:
            # 使用从环境变量读取的 YOSYS_BIN
            result = subprocess.run(
                [YOSYS_BIN, "-s", str(ys_script)],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            save_dir = Path("experiments/reports")
            save_dir.mkdir(parents=True, exist_ok=True)
            file_stem = Path(rtl_path).stem
            # 使用毫秒级时间戳（乘以1000），解决同一秒内覆盖的问题
            timestamp = int(time.time() * 1000)
            final_report_path = save_dir / f"{file_stem}_{timestamp}.log"
            final_report_path.write_text(result.stdout + "\n" + result.stderr)
            
            if result.returncode != 0:
                logger.warning(f"Yosys 综合失败: {result.stderr}")
                return {"status": "error", "area": None, "delay": None, "timing_met": None, "report_path": str(final_report_path)}
            
            output = result.stdout
            
            area = None
            area_match = re.search(r"Chip area for module.*?:\s*([\d\.]+)", output)
            if area_match:
                area = float(area_match.group(1))
            
            delay = None
            ltp_match = re.search(r"Longest topological path.*?length=(\d+)", output)
            if ltp_match:
                delay = int(ltp_match.group(1))

            timing_met = None
            if delay_limit is not None and delay is not None:
                timing_met = bool(delay <= delay_limit)
            00
            return {
                "status": "success",
                "area": area,
                "delay": delay,
                "timing_met": timing_met,
                "report_path": str(final_report_path),
                "runtime": round(time.time() - start_time, 2)
            }

        except subprocess.TimeoutExpired:
            logger.warning("Yosys 执行超时 (30s)")
            return {"status": "timeout", "area": None, "delay": None, "timing_met": None, "report_path": None}
        except Exception as e:
            logger.error(f"评估过程发生异常: {str(e)}")
            return {"status": "error", "area": None, "delay": None, "timing_met": None, "report_path": None}
