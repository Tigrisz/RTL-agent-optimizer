import sys
import os
from pathlib import Path

# 确保能导入 evaluator
sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))
from evaluation.evaluator import evaluate

def run_all_cases():
    # 指向复制过来的 opti_cases 目录
    cases_root = Path(__file__).resolve().parent.parent / "benchmarks" / "public" / "opti_cases"
    
    # 收集所有 case 目录（按名称排序 case1 ~ case8）
    case_dirs = sorted([d for d in cases_root.iterdir() if d.is_dir() and d.name.startswith("case")])
    
    if not case_dirs:
        print("❌ 未找到任何 case 目录，请确认 benchmarks/public/opti_cases/ 是否存在。")
        return

    print(f"🔍 共发现 {len(case_dirs)} 个 case，开始批量评估...\n")
    print(f"{'Case':<10} {'状态':<10} {'面积(µm²)':<15} {'延时(ltp)':<12} {'报告路径'}")
    print("-" * 80)

    summary = []
    for case_dir in case_dirs:
        rtl_path = case_dir / "rtl.v"
        if not rtl_path.exists():
            print(f"{case_dir.name:<10} {'❌ 缺少rtl.v':<10}")
            continue

        # 约束：这里不传 top，让 evaluator 自动从文件内容解析；
        # 也不传 delay_limit，因为各 case 的合理上限不同，先看原始数据
        constraints = {"delay_limit": None, "delay_unit": None}

        try:
            result = evaluate(str(rtl_path), constraints)
        except Exception as e:
            print(f"{case_dir.name:<10} {'❌ 异常':<10} {str(e)}")
            continue

        status = result.get("status", "unknown")
        area = result.get("area")
        delay = result.get("delay")
        report_path = result.get("report_path", "")

        # 格式化输出
        area_str = f"{area:.2f}" if area is not None else "N/A"
        delay_str = str(delay) if delay is not None else "N/A"
        print(f"{case_dir.name:<10} {status:<10} {area_str:<15} {delay_str:<12} {report_path}")

        # 记录用于后续汇总
        summary.append({
            "case": case_dir.name,
            "status": status,
            "area": area,
            "delay": delay,
        })

    # 打印汇总
    print("\n" + "=" * 80)
    success_count = sum(1 for s in summary if s["status"] == "success")
    print(f"📊 汇总: 共 {len(summary)} 个 case，成功 {success_count} 个，失败 {len(summary) - success_count} 个")

    if success_count > 0:
        areas = [s["area"] for s in summary if s["area"] is not None]
        delays = [s["delay"] for s in summary if s["delay"] is not None]
        if areas:
            print(f"   面积范围: {min(areas):.2f} ~ {max(areas):.2f} µm²")
        if delays:
            print(f"   延时范围: {min(delays)} ~ {max(delays)} ltp 级数")

if __name__ == "__main__":
    run_all_cases()
