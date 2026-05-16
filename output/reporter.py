"""
报告生成器 —— 使用 Jinja2 渲染 HTML 报告
"""

import os
import json
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape
from loguru import logger


TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")


def _build_job_list(matched_jobs: list[dict]) -> list[dict]:
    """将匹配结果转换为模板渲染所需的数据结构"""
    result = []
    for mj in matched_jobs:
        prob = mj.get("interview_prob", {})
        skill_detail = mj.get("skill_detail", {})

        # 匹配/缺失的技能标签
        matched_tags = []
        missing_tags = []
        if skill_detail:
            # 匹配的技能（只取前3个得分最高的）
            matched = skill_detail.get("matched", {})
            if matched:
                sorted_m = sorted(matched.items(), key=lambda x: x[1], reverse=True)
                matched_tags = [s for s, _ in sorted_m[:5]]
            missing_tags = skill_detail.get("missing", [])[:5]

        result.append({
            "company": mj.get("company", ""),
            "title": mj.get("title", ""),
            "city": mj.get("city", ""),
            "salary": mj.get("salary", ""),
            "job_type": mj.get("job_type", "实习"),
            "url": mj.get("url", ""),
            "description": mj.get("description", ""),
            "total_score": mj.get("total_score", 0),
            "skill_match": mj.get("skill_match", 0),
            "city_match": mj.get("city_match", 0),
            "company_pref": mj.get("company_pref", 0),
            "probability": prob.get("probability", 0.5),
            "difficulty": prob.get("difficulty", 0),
            "level": prob.get("level", "未知"),
            "suggestion": prob.get("suggestion", ""),
            "matched_tags": matched_tags,
            "missing_tags": missing_tags,
        })

    # 按总分降序排列
    result.sort(key=lambda x: x["total_score"], reverse=True)
    return result


def generate_report(
    matched_jobs: list[dict],
    profile: dict,
    cities: list[str],
    output_dir: str = "./outputs",
    report_name: str = None,
    top_n: int = 30,
) -> str:
    """
    生成 HTML 报告

    Args:
        matched_jobs: 匹配后的岗位列表（含 interview_prob）
        profile: 用户信息
        cities: 意向城市列表
        output_dir: 输出目录
        report_name: 报告文件名（支持 strftime 占位符）
        top_n: 展示前 N 条

    Returns:
        报告文件的完整路径
    """
    os.makedirs(output_dir, exist_ok=True)

    now = datetime.now()
    if report_name is None:
        report_name = f"internship_report_{now.strftime('%Y%m%d_%H%M')}.html"
    else:
        report_name = now.strftime(report_name)

    # 准备模板数据
    jobs = _build_job_list(matched_jobs[:top_n])

    # 统计信息
    high_count = sum(1 for j in jobs if j["probability"] >= 0.7)
    companies = list(set(j["company"] for j in jobs))
    avg_score = sum(j["total_score"] for j in jobs) / len(jobs) if jobs else 0

    unique_cities = sorted(set(j["city"] for j in jobs if j.get("city")))

    template_data = {
        "report_time": now.strftime("%Y-%m-%d %H:%M"),
        "profile": profile,
        "cities": cities,
        "jobs": jobs,
        "unique_cities": unique_cities,
        "stats": {
            "total_jobs": len(matched_jobs),
            "matched": len(jobs),
            "avg_score": f"{avg_score:.0%}",
            "high_prob": high_count,
            "companies": len(companies),
        },
    }

    # 渲染
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("report.html")
    html = template.render(**template_data)

    # 写入文件
    filepath = os.path.join(output_dir, report_name)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(f"报告已生成: {filepath}")
    return filepath
