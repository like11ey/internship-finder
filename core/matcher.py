"""
匹配引擎 —— 综合评估岗位与用户画像的匹配度

打分维度:
  1. 技能匹配 (权重可配)     —— 用户技能 vs JD 要求
  2. 城市匹配                 —— 意向城市 vs 岗位城市
  3. 公司偏好                 —— 关注公司优先加分
  4. 学历匹配                 —— 学历要求 vs 用户学历
"""

import re
from typing import Optional
from loguru import logger


# ============================================================
# 技能关键词库 —— 用于从 JD 文本中提取技能词
# ============================================================

SKILL_KEYWORDS = {
    # 编程语言
    "Python": ["python", "django", "flask", "fastapi", "tornado"],
    "Java": ["java", "spring", "spring boot", "spring cloud", "mybatis", "jvm"],
    "C++": ["c\\+\\+", "cpp", "stl", "qt", "boost"],
    "C": ["\\bc语言\\b", "\\bc\\b", "嵌入式", "单片机"],
    "Go": ["golang", "\\bgo\\b", "gin", "beego"],
    "JavaScript": ["javascript", "js", "node\\.js", "nodejs"],
    "TypeScript": ["typescript", "ts"],
    "Rust": ["rust", "cargo"],
    "Kotlin": ["kotlin"],
    "C#": ["c#", "csharp", "\\.net"],
    "PHP": ["php", "laravel"],
    "Ruby": ["ruby", "rails"],
    "SQL": ["\\bsql\\b", "mysql", "postgresql", "oracle", "数据库", "database"],

    # 框架 / 工具
    "Spring": ["spring", "spring boot"],
    "Django": ["django"],
    "Flask": ["flask"],
    "Vue": ["vue", "vue\\.js"],
    "React": ["react", "react\\.js"],
    "Docker": ["docker", "容器"],
    "Kubernetes": ["kubernetes", "k8s", "容器编排"],
    "Git": ["git", "版本控制"],
    "Linux": ["linux", "shell", "bash", "unix"],
    "MySQL": ["mysql", "sql"],
    "Redis": ["redis", "缓存"],
    "MongoDB": ["mongodb", "mongo"],
    "Kafka": ["kafka", "消息队列"],
    "RabbitMQ": ["rabbitmq", "消息队列"],
    "Nginx": ["nginx"],
    "Jenkins": ["jenkins", "ci/cd", "持续集成"],
    "Spark": ["spark", "大数据"],
    "Hadoop": ["hadoop", "hdfs", "mapreduce"],
    "PyTorch": ["pytorch", "深度学习"],
    "TensorFlow": ["tensorflow", "tf"],
    "OpenCV": ["opencv", "计算机视觉"],
    "Scikit-learn": ["sklearn", "scikit", "机器学习"],
    "Pandas": ["pandas", "数据分析"],

    # 领域知识
    "机器学习": ["机器学习", "machine learning", "ml"],
    "深度学习": ["深度学习", "deep learning", "dl"],
    "NLP": ["nlp", "自然语言处理"],
    "计算机视觉": ["计算机视觉", "cv", "图像", "视觉"],
    "分布式": ["分布式", "分布式系统", "微服务", "microservice"],
    "高并发": ["高并发", "并发", "多线程", "multithread"],
    "网络编程": ["网络编程", "socket", "tcp/ip", "http"],
    "算法": ["算法", "数据结构", "algorithm"],
    "测试": ["测试", "自动化测试", "单元测试", "pytest", "junit"],
    "CI/CD": ["ci/cd", "持续集成", "持续交付"],
    "Android": ["android", "安卓"],
    "iOS": ["ios", "swift"],
    "前端": ["前端", "frontend", "html", "css"],
    "后端": ["后端", "backend", "服务端"],
    "数据分析": ["数据分析", "data analysis", "etl", "数仓"],
}


class SkillMatcher:
    """
    技能匹配器

    从岗位描述/要求中提取技能关键词，与用户技能栈匹配打分
    """

    def __init__(self, user_skills: dict[str, int]):
        """
        Args:
            user_skills: {技能名: 熟练度 1-5}
        """
        self.user_skills = user_skills
        # 编译正则
        self._compiled: dict[str, list[re.Pattern]] = {}
        for skill, aliases in SKILL_KEYWORDS.items():
            patterns = [re.compile(rf"(?i)\b{a}\b") for a in aliases]
            self._compiled[skill] = patterns

    def extract_requirements(self, text: str) -> dict[str, float]:
        """
        从文本中提取技能要求及权重

        Returns:
            {技能名: 需求量 0-1}
        """
        result: dict[str, float] = {}
        text_lower = text.lower()

        for skill, patterns in self._compiled.items():
            score = 0.0
            for pat in patterns:
                matches = pat.findall(text_lower)
                if matches:
                    score += min(len(matches) * 0.5, 1.0)
            if score > 0:
                result[skill] = min(score, 1.0)

        return result

    def match(self, job_description: str, job_requirements: str = "") -> dict:
        """
        计算技能匹配度

        Args:
            job_description: 岗位描述
            job_requirements: 岗位要求（可选，会合并到描述中）

        Returns:
            {
                "score": 0.0-1.0,       # 总匹配分
                "matched": {skill: match_level},  # 匹配到的技能及程度
                "missing": [skill],     # JD 要求但用户不具备的技能
                "detail": str,          # 可读的描述
            }
        """
        full_text = job_description + " " + job_requirements
        required = self.extract_requirements(full_text)

        if not required:
            return {
                "score": 0.5,  # JD 没提取到技能关键词，给中等分
                "matched": {},
                "missing": [],
                "detail": "未从JD中提取到明确技能要求",
            }

        # 计算匹配度
        total_required = sum(required.values())
        matched_weight = 0.0
        matched_skills: dict[str, float] = {}
        missing: list[str] = []

        for skill, weight in required.items():
            if skill in self.user_skills:
                user_level = self.user_skills[skill]  # 1-5
                match_level = min(user_level / 3.0, 1.0)  # 熟练度 3 及以上视为完全匹配
                matched_weight += weight * match_level
                matched_skills[skill] = match_level
            else:
                missing.append(skill)
                # 未掌握的技能，检测是否有关联技能可以弥补
                related = self._find_related(skill)
                if related:
                    matched_weight += weight * 0.3  # 有关联技能给 30% 分
                    matched_skills[skill] = 0.3

        score = matched_weight / total_required if total_required > 0 else 0.5
        score = min(max(score, 0.0), 1.0)

        # 可读描述
        detail_parts = []
        if matched_skills:
            matched_names = [f"{s}({v:.0%})" for s, v in list(matched_skills.items())[:5]]
            detail_parts.append(f"匹配: {', '.join(matched_names)}")
        if missing:
            detail_parts.append(f"欠缺: {', '.join(missing[:5])}")

        return {
            "score": score,
            "matched": matched_skills,
            "missing": missing,
            "detail": " | ".join(detail_parts) if detail_parts else "匹配度未知",
        }

    def _find_related(self, skill: str) -> Optional[str]:
        """查找用户是否有关联技能"""
        relations = {
            "C++": ["C", "Python"],
            "Go": ["Python", "Java"],
            "Rust": ["C++", "C", "Python"],
            "Kubernetes": ["Docker", "Linux"],
            "Spark": ["Python", "SQL"],
            "PyTorch": ["Python", "机器学习"],
            "TensorFlow": ["Python", "深度学习"],
            "NLP": ["Python", "机器学习"],
            "计算机视觉": ["Python", "OpenCV"],
            "Vue": ["JavaScript", "TypeScript"],
            "React": ["JavaScript", "TypeScript"],
            "Spring": ["Java"],
            "Django": ["Python"],
            "Flask": ["Python"],
            "Kafka": ["分布式"],
            "MongoDB": ["MySQL"],
            "Jenkins": ["CI/CD", "Git"],
        }
        related_list = relations.get(skill, [])
        for r in related_list:
            if r in self.user_skills:
                return r
        return None


class CityMatcher:
    """城市匹配器"""

    def __init__(self, preferred_cities: list[str]):
        self.cities = [c.strip() for c in preferred_cities]

    def match(self, job_city: str) -> float:
        """
        城市匹配度

        Returns:
            1.0 完全匹配, 0.7 同省份/相邻, 0.3 不完全匹配, 0.0 不匹配
        """
        if not self.cities or not job_city:
            return 1.0  # 不限城市

        job_city = job_city.strip()

        # 精确匹配
        for city in self.cities:
            if city in job_city or job_city in city:
                return 1.0

        # 同省匹配（基于城市名简略判断）
        # 西安 → 陕西；如果意向城市中有"西安"，而岗位是"陕西"其他城市
        province_map = {
            "西安": "陕西", "北京": "北京", "上海": "上海",
            "杭州": "浙江", "深圳": "广东", "广州": "广东",
            "成都": "四川", "武汉": "湖北", "南京": "江苏",
        }
        job_province = province_map.get(job_city, "")

        for city in self.cities:
            user_province = province_map.get(city, "")
            if user_province and user_province == job_province:
                return 0.7

        return 0.3


class CompanyMatcher:
    """公司偏好匹配器"""

    def __init__(self, preferred: list[str]):
        self.preferred = [c.strip() for c in (preferred or [])]

    def match(self, company: str) -> float:
        """偏好公司返回 1.0，否则返回 0.5（不扣分）"""
        if not self.preferred:
            return 1.0
        for p in self.preferred:
            if p in company:
                return 1.0
        return 0.5


class DegreeMatcher:
    """学历匹配器"""

    def __init__(self, user_degree: str):
        self.degree = user_degree  # "本科" / "硕士" / "博士"

    def match(self, jd_text: str) -> float:
        """
        根据 JD 判断学历要求

        Returns:
            1.0 满足 / 超出, 0.7 可能满足, 0.3 不太满足
        """
        text = jd_text.lower()

        # 检测 JD 中要求的学历
        requires_phd = any(w in text for w in ["博士", "phd", "博士研究生"])
        requires_master = any(w in text for w in ["硕士", "研究生", "master"])
        requires_bachelor = any(w in text for w in ["本科", "bachelor", "学士"])

        degree_rank = {"本科": 1, "硕士": 2, "博士": 3}
        user_rank = degree_rank.get(self.degree, 1)

        if requires_phd:
            return 1.0 if user_rank >= 3 else 0.3
        elif requires_master:
            return 1.0 if user_rank >= 2 else 0.7
        elif requires_bachelor:
            return 1.0 if user_rank >= 1 else 0.5
        else:
            # 未明确要求
            return 1.0


# ============================================================
# 综合匹配器
# ============================================================

class JobMatcher:
    """整合所有匹配维度"""

    def __init__(self, config: dict):
        self.skill_matcher = SkillMatcher(config["skills"])
        self.city_matcher = CityMatcher(config["cities"])
        self.company_matcher = CompanyMatcher(config.get("preferred_companies", []))
        self.degree_matcher = DegreeMatcher(config.get("profile", {}).get("degree", "硕士"))

        weights = config.get("matcher_weights", {})
        self.w_skill = weights.get("skill_weight", 0.5)
        self.w_city = weights.get("city_weight", 0.2)
        self.w_company = weights.get("company_weight", 0.15)
        self.w_degree = weights.get("degree_weight", 0.15)

    def evaluate(self, job: dict) -> dict:
        """
        评估一个岗位

        Args:
            job: 岗位 dict，需包含 title, company, city, description, requirements

        Returns:
            包含各维度得分和总分
        """
        desc = job.get("description", "")
        reqs = job.get("requirements", "")

        skill_result = self.skill_matcher.match(desc, reqs)
        city_score = self.city_matcher.match(job.get("city", ""))
        company_score = self.company_matcher.match(job.get("company", ""))
        degree_score = self.degree_matcher.match(desc + reqs)

        total = (
            self.w_skill * skill_result["score"]
            + self.w_city * city_score
            + self.w_company * company_score
            + self.w_degree * degree_score
        )

        return {
            "city_match": city_score,
            "skill_match": skill_result["score"],
            "company_pref": company_score,
            "degree_match": degree_score,
            "total_score": round(total, 4),
            "skill_detail": {
                "matched": skill_result["matched"],
                "missing": skill_result["missing"],
                "detail": skill_result["detail"],
            },
        }
