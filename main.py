"""
实习生岗位自动筛查工具 —— 主入口

用法:
    python main.py                     # 单次运行
    python main.py --schedule          # 定时运行（每 N 小时一次）
    python main.py --mock              # Mock 模式（不依赖网络）

流程:
    1. 加载配置
    2. 采集岗位（实习僧）+ 面经（牛客网）
    3. 匹配打分
    4. 面试概率评估
    5. 生成 HTML 报告
"""

import sys
import os
import argparse
import time
from datetime import datetime

from loguru import logger

# 确保项目根目录在 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import (
    load_config, get_profile, get_cities, get_skills,
    get_directions, get_preferred_companies,
    get_collector_config, get_matcher_config, get_output_config,
)
from core.shixiseng import ShixisengCollector
from core.nowcoder import NowcoderCollector
from core.matcher import JobMatcher
from analyzer.interview_prob import InterviewProbability, evaluate_all
from output.reporter import generate_report
from storage.db import init_db, JobDAO, InterviewDAO, MatchDAO, RunLogDAO


def setup_logging():
    """配置日志"""
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {message}",
        level="INFO",
    )
    # 同时写入文件
    log_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(log_dir, exist_ok=True)
    logger.add(
        os.path.join(log_dir, "finder.log"),
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {name}:{function}:{line} | {message}",
    )


def run_once(mock: bool = False) -> str:
    """
    执行一次完整的筛查流程

    Returns:
        生成的报告文件路径
    """
    run_id = RunLogDAO.start()
    jobs_count = 0
    interviews_count = 0
    matches_count = 0

    try:
        # ---- 1. 加载配置 ----
        logger.info("=" * 50)
        logger.info("实习生岗位筛查启动")
        logger.info("=" * 50)

        config = load_config()
        profile = get_profile()
        cities = get_cities()
        skills = get_skills()
        directions = get_directions()
        preferred = get_preferred_companies()
        collector_cfg = get_collector_config()
        output_cfg = get_output_config()

        logger.info(f"用户: {profile.get('name')} | {profile.get('school')} | {profile.get('degree')}")
        logger.info(f"意向城市: {cities}")
        logger.info(f"技能栈: {list(skills.keys())}")
        logger.info(f"岗位方向: {directions}")

        # ---- 2. 采集岗位 ----
        logger.info("-" * 40)
        logger.info("阶段 1/4: 采集岗位信息")

        sx_collector = ShixisengCollector(collector_cfg)

        if mock:
            # Mock 模式：直接使用模拟数据
            all_jobs = sx_collector._mock_jobs(cities, directions)
        else:
            all_jobs = sx_collector.collect_jobs(cities, directions)

        logger.info(f"共采集 {len(all_jobs)} 条岗位")

        # 存储到数据库，同时记录内部 id
        for job in all_jobs:
            db_id = JobDAO.upsert(**job)
            job["db_id"] = db_id
        jobs_count = len(all_jobs)

        # ---- 3. 采集面经 ----
        logger.info("-" * 40)
        logger.info("阶段 2/4: 采集面经信息")

        nc_collector = NowcoderCollector(collector_cfg)

        # 从岗位中提取所有公司名
        companies = list(set(j["company"] for j in all_jobs if j.get("company")))
        # 加上偏好公司
        for c in preferred:
            if c not in companies:
                companies.append(c)

        logger.info(f"需要采集面经的公司: {len(companies)} 家")

        if mock:
            all_interviews = nc_collector._mock_interviews(companies)
        else:
            all_interviews = nc_collector.collect_interviews(companies)

        logger.info(f"共采集 {len(all_interviews)} 条面经")

        for iv in all_interviews:
            InterviewDAO.upsert(**iv)
        interviews_count = len(all_interviews)

        # ---- 4. 匹配打分 ----
        logger.info("-" * 40)
        logger.info("阶段 3/4: 匹配打分 + 面试评估")

        matcher_config = {
            "skills": skills,
            "cities": cities,
            "preferred_companies": preferred,
            "profile": profile,
            "matcher_weights": {
                "skill_weight": get_matcher_config().get("skill_weight", 0.5),
                "city_weight": get_matcher_config().get("city_weight", 0.2),
                "company_weight": get_matcher_config().get("company_weight", 0.15),
                "degree_weight": get_matcher_config().get("degree_weight", 0.15),
            },
        }

        matcher = JobMatcher(matcher_config)

        match_results = []
        for job in all_jobs:
            eval_result = matcher.evaluate(job)
            job["total_score"] = eval_result["total_score"]
            job["skill_match"] = eval_result["skill_match"]
            job["city_match"] = eval_result["city_match"]
            job["company_pref"] = eval_result["company_pref"]
            job["degree_match"] = eval_result["degree_match"]
            job["skill_detail"] = eval_result["skill_detail"]
            match_results.append(job)

        # 按总分排序
        match_results.sort(key=lambda x: x["total_score"], reverse=True)

        # 面试概率评估
        enriched = evaluate_all(match_results)

        logger.info(f"匹配完成，共 {len(enriched)} 条有效匹配")

        # 存储匹配结果
        for mr in enriched:
            prob = mr.get("interview_prob", {})
            MatchDAO.save(
                job_id=mr.get("db_id") or 0,
                city_match=mr.get("city_match", 0),
                skill_match=mr.get("skill_match", 0),
                company_pref=mr.get("company_pref", 0),
                degree_match=mr.get("degree_match", 0),
                total_score=mr.get("total_score", 0),
                interview_prob=prob.get("probability", 0.5),
                skill_detail=mr.get("skill_detail", {}),
            )
        matches_count = len(enriched)

        # ---- 5. 生成报告 ----
        logger.info("-" * 40)
        logger.info("阶段 4/4: 生成 HTML 报告")

        top_n = output_cfg.get("top_n", 30)
        report_path = generate_report(
            matched_jobs=enriched,
            profile=profile,
            cities=cities,
            output_dir=output_cfg.get("report_dir", "./outputs"),
            report_name=output_cfg.get("report_name"),
            top_n=top_n,
        )

        # ---- 完成 ----
        logger.info("=" * 50)
        logger.info(f"✅ 筛查完成！报告: {report_path}")
        logger.info(f"   采集岗位: {jobs_count} | 面经: {interviews_count} | 匹配: {matches_count}")
        logger.info("=" * 50)

        RunLogDAO.finish(run_id, jobs_count, interviews_count, matches_count, "success")
        return report_path

    except Exception as e:
        logger.error(f"筛查失败: {e}")
        RunLogDAO.finish(run_id, jobs_count, interviews_count, matches_count,
                         "failed", str(e))
        raise


def run_schedule(interval_hours: int = 12):
    """定时运行模式"""
    import schedule as sched

    logger.info(f"定时模式启动，每 {interval_hours} 小时执行一次")
    sched.every(interval_hours).hours.do(run_once)

    # 立即执行一次
    run_once()

    while True:
        sched.run_pending()
        time.sleep(60)


def main():
    parser = argparse.ArgumentParser(
        description="实习生岗位自动筛查工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py                  # 单次筛查
  python main.py --mock           # 使用模拟数据（测试用）
  python main.py --schedule       # 定时运行（每12小时）
  python main.py --schedule -i 6  # 每6小时运行一次
        """,
    )
    parser.add_argument("--mock", action="store_true",
                        help="Mock 模式，使用内置模拟数据")
    parser.add_argument("--schedule", action="store_true",
                        help="定时运行模式")
    parser.add_argument("--web", action="store_true",
                        help="启动 Web 服务")
    parser.add_argument("-i", "--interval", type=int, default=12,
                        help="定时间隔（小时），默认 12")
    parser.add_argument("-p", "--port", type=int, default=0,
                        help="Web 服务端口（默认使用 config.yaml 配置）")

    args = parser.parse_args()

    setup_logging()

    # 初始化数据库
    init_db()

    if args.web:
        from web.app import start_web
        from core.config import load_config
        config = load_config()
        web_cfg = config.get("web", {})
        start_web(
            host=web_cfg.get("host", "127.0.0.1"),
            port=args.port or web_cfg.get("port", 5000),
        )
    elif args.schedule:
        run_schedule(args.interval)
    else:
        report_path = run_once(mock=args.mock)
        # 尝试自动打开报告
        try:
            import webbrowser
            webbrowser.open(f"file:///{report_path.replace(os.sep, '/')}")
        except Exception:
            pass


if __name__ == "__main__":
    main()
