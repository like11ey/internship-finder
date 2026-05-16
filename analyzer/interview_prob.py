"""
面试概率评估器 —— 结合面经数据和技能匹配度评估面试通过概率

评估维度:
  1. 技能匹配度 (来自 matcher)   —— 权重 40%
  2. 公司面试难度 (面经数据)     —— 权重 35%
  3. 学历匹配度                     —— 权重 15%
  4. 城市竞争热度                   —— 权重 10%
"""

from typing import Optional
from loguru import logger
from storage.db import InterviewDAO


def get_city_competition_factor(city: str) -> float:
    """
    估算城市竞争热度因子

    一线城市竞争更激烈，通过概率略低
    返回 0.6-1.0，越低表示竞争越激烈
    """
    tier1 = ["北京", "上海", "深圳", "杭州"]
    tier2 = ["广州", "成都", "武汉", "南京", "西安", "苏州", "天津"]
    tier3 = ["长沙", "合肥", "重庆", "济南", "青岛", "郑州", "大连", "厦门"]

    city = city.strip()

    for t in tier1:
        if t in city:
            return 0.7  # 一线竞争激烈
    for t in tier2:
        if t in city:
            return 0.85
    for t in tier3:
        if t in city:
            return 0.95
    return 0.9  # 默认


class InterviewProbability:
    """
    面试通过概率评估器

    根据以下公式计算:
      prob = skill_score * 0.40 + difficulty_factor * 0.35
           + degree_score * 0.15 + city_factor * 0.10
    """

    def __init__(self):
        self.w_skill = 0.40
        self.w_difficulty = 0.35
        self.w_degree = 0.15
        self.w_city = 0.10

    def evaluate(self, job: dict, skill_score: float, degree_score: float) -> dict:
        """
        评估面试通过概率

        Args:
            job: 岗位 dict（需包含 company, city）
            skill_score: 已计算的技能匹配度 (0-1)
            degree_score: 已计算的学历匹配度 (0-1)

        Returns:
            {
                "probability": 0.0-1.0,
                "difficulty": 公司难度评分 (1-5),
                "level": "高/中等/偏低",
                "factors": [...],
                "suggestion": 建议文本
            }
        """
        company = job.get("company", "")

        # 1. 获取该公司面经平均难度
        avg_difficulty = InterviewDAO.get_company_difficulty(company)
        if avg_difficulty is None:
            # 没有面经数据，用默认值
            avg_difficulty = 3.0

        # 难度越高，通过概率越低
        difficulty_factor = max(0.1, 1.0 - (avg_difficulty - 1) * 0.2)

        # 2. 城市竞争因子
        city_factor = get_city_competition_factor(job.get("city", ""))

        # 3. 综合概率
        prob = (
            self.w_skill * skill_score
            + self.w_difficulty * difficulty_factor
            + self.w_degree * degree_score
            + self.w_city * city_factor
        )
        prob = round(min(max(prob, 0.05), 0.95), 3)

        # 4. 等级划分
        if prob >= 0.7:
            level = "较高"
            suggestion = "技能匹配良好，面试难度可控，做好常规准备即可。"
        elif prob >= 0.45:
            level = "中等"
            suggestion = "需要针对薄弱环节加强准备，建议多刷该公司的面经。"
        else:
            level = "偏低"
            suggestion = "技能与岗位要求差距较大，或该公司面试难度很高，建议补充相关技能后再投递。"

        # 5. 影响因素
        factors = [
            f"技能匹配度: {skill_score:.0%}",
            f"公司面试难度: {avg_difficulty:.1f}/5",
            f"城市竞争度: {city_factor:.0%}",
            f"学历匹配度: {degree_score:.0%}",
        ]

        return {
            "probability": prob,
            "difficulty": round(avg_difficulty, 1),
            "level": level,
            "factors": factors,
            "suggestion": suggestion,
            "difficulty_factor": round(difficulty_factor, 2),
            "city_factor": city_factor,
        }


def evaluate_all(match_results: list[dict]) -> list[dict]:
    """
    批量评估面试概率

    对每个匹配结果附加 interview_prob 字段
    """
    evaluator = InterviewProbability()

    enriched = []
    for mr in match_results:
        prob_result = evaluator.evaluate(
            job=mr,
            skill_score=mr.get("skill_match", 0.5),
            degree_score=mr.get("degree_match", 1.0),
        )
        enriched.append({**mr, "interview_prob": prob_result})
    return enriched
