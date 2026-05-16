"""
国产大模型分析器 —— 调用 DeepSeek / GLM / Qwen 等大模型
实现技能提取、语义匹配、个性化建议等功能

所有大模型使用 OpenAI 兼容接口，通过 httpx 直接调用，无需 openai 包。
"""

import json
import hashlib
import time
from typing import Optional
from functools import lru_cache

import httpx
from loguru import logger


# ============================================================
# 提示词模板
# ============================================================

SKILL_EXTRACT_PROMPT = """你是一个技术招聘专家。请分析以下计算机专业学生的自我描述和项目经历，提取他掌握的技术技能。

要求：
1. 返回严格的 JSON 格式
2. 技能按类别分组：编程语言、框架工具、数据库、领域知识
3. 每项技能给出 1-5 的熟练度评分（5=精通）
4. 同时给出该学生的整体水平评估（初级/中级/高级）
5. 列出该学生最匹配的 3 个岗位方向

返回格式示例：
{
  "skills": {
    "编程语言": {"Python": 4, "Java": 3, "SQL": 3},
    "框架工具": {"Django": 3, "Flask": 2, "Git": 4, "Linux": 3},
    "数据库": {"MySQL": 3, "Redis": 2},
    "领域知识": {"后端开发": 4, "Web开发": 3}
  },
  "level": "中级",
  "directions": ["后端开发", "数据分析", "全栈开发"],
  "summary": "该学生具备扎实的 Python 后端开发能力..."
}

学生信息：
{user_info}

请只返回 JSON，不要有其他文字。"""


SEMANTIC_MATCH_PROMPT = """你是一个招聘匹配专家。请评估以下候选人与岗位的匹配度。

候选人信息：
{user_info}

岗位信息：
{job_info}

请从以下维度评估（返回严格的 JSON）：
1. 技能匹配度（0-100）
2. 经验匹配度（0-100）  
3. 学历匹配度（0-100）
4. 综合匹配度（0-100）
5. 匹配的技能列表
6. 欠缺的技能列表
7. 简短建议（50字以内）

返回格式：
{{
  "skill_match": 80,
  "experience_match": 60,
  "degree_match": 90,
  "overall_match": 75,
  "matched_skills": ["Python", "MySQL"],
  "missing_skills": ["Docker", "K8s"],
  "advice": "建议补充容器化知识，多练习系统设计题"
}}

请只返回 JSON。"""


ADVICE_PROMPT = """你是一个求职顾问。针对以下岗位，给候选人提供具体的面试准备建议。

候选人信息：
{user_info}

目标岗位：
{job_info}

请给出 3-5 条具体可操作的建议（每条30字以内），以及一个总体通过概率评估。

返回 JSON：
{{
  "tips": ["建议1", "建议2", "建议3"],
  "probability": 65,
  "level": "中等"
}}

请只返回 JSON。"""


# ============================================================
# LLM 分析器
# ============================================================

class LLMAnalyzer:
    """
    国产大模型分析器

    支持 DeepSeek、智谱 GLM、通义千问等（OpenAI 兼容接口）。
    内置结果缓存，避免重复调用。
    """

    def __init__(self, config: dict):
        self.config = config
        self.enabled = config.get("enabled", False)

        if not self.enabled:
            logger.info("大模型分析已禁用")
            return

        self.api_base = config.get("api_base", "https://api.deepseek.com/v1")
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "deepseek-chat")
        self.temperature = config.get("temperature", 0.3)
        self.max_tokens = config.get("max_tokens", 2000)
        self.provider = config.get("provider", "deepseek")

        # 验证配置
        if not self.api_key or self.api_key == "你的API_KEY":
            logger.warning("未配置大模型 API Key，回退到关键词匹配模式")
            self.enabled = False
            return

        self._http = httpx.Client(timeout=30.0)
        self._call_count = 0
        self._cache: dict[str, str] = {}

        logger.info(f"大模型已启用: {self.provider}/{self.model} @ {self.api_base}")

    # ----------------------------------------------------------
    # 核心 API 调用
    # ----------------------------------------------------------

    def _cache_key(self, prompt: str, user_content: str) -> str:
        """生成缓存键"""
        raw = f"{self.model}:{prompt[:50]}:{user_content}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _call(self, system_prompt: str, user_content: str) -> str:
        """调用大模型 API，带缓存"""
        if not self.enabled:
            return ""

        cache_key = self._cache_key(system_prompt, user_content)
        if cache_key in self._cache:
            logger.debug("LLM 缓存命中")
            return self._cache[cache_key]

        url = f"{self.api_base.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                resp = self._http.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    self._call_count += 1
                    self._cache[cache_key] = content
                    if self._call_count % 5 == 0:
                        logger.info(f"LLM 已调用 {self._call_count} 次")
                    return content
                elif resp.status_code == 429:
                    logger.warning(f"LLM 速率限制 (429)，等待 {5*(attempt+1)}s")
                    time.sleep(5 * (attempt + 1))
                elif resp.status_code == 401:
                    logger.error("LLM API Key 无效 (401)")
                    self.enabled = False
                    return ""
                else:
                    logger.warning(f"LLM 返回 {resp.status_code}: {resp.text[:200]}")
                    if attempt < max_retries:
                        time.sleep(2)
            except httpx.RequestError as e:
                logger.warning(f"LLM 请求失败 (尝试 {attempt+1}): {e}")
                if attempt < max_retries:
                    time.sleep(2)

        return ""

    @staticmethod
    def _parse_json(text: str) -> dict:
        """从 LLM 回复中提取 JSON"""
        if not text:
            return {}
        # 处理 markdown code block
        text = text.strip()
        if text.startswith("```"):
            # 去掉 ```json 和结尾 ```
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试找到 JSON 块
            import re
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            logger.warning(f"LLM 返回非 JSON: {text[:200]}")
            return {}

    # ----------------------------------------------------------
    # 公共方法
    # ----------------------------------------------------------

    def extract_skills(self, self_intro: str, projects: list[dict] = None) -> dict:
        """
        从自然语言描述中提取结构化技能

        Returns:
            {
                "skills": {类别: {技能名: 熟练度}},
                "level": "初级/中级/高级",
                "directions": [...],
                "summary": "..."
            }
            或者空 dict（LLM 不可用时）
        """
        if not self.enabled:
            return {}

        user_info = f"自我描述：{self_intro}\n"
        if projects:
            user_info += "项目经历：\n"
            for p in projects:
                user_info += f"- {p.get('name', '')}: {p.get('desc', '')} (技术栈: {', '.join(p.get('tech', []))})\n"

        content = self._call(SKILL_EXTRACT_PROMPT, user_info)
        return self._parse_json(content)

    def semantic_match(self, user_profile_text: str, job_desc: str) -> dict:
        """
        语义匹配打分

        Returns:
            {"overall_match": 0-100, "skill_match": 0-100, ...}
        """
        if not self.enabled:
            return {}

        user_info = user_profile_text
        job_info = f"岗位描述：{job_desc[:1500]}"

        content = self._call(SEMANTIC_MATCH_PROMPT,
                             f"候选人信息：\n{user_info}\n\n岗位信息：\n{job_info}")
        return self._parse_json(content)

    def generate_advice(self, user_profile_text: str, job_info: str) -> dict:
        """
        生成个性化投递建议

        Returns:
            {"tips": [...], "probability": 0-100, "level": "..."}
        """
        if not self.enabled:
            return {}

        content = self._call(ADVICE_PROMPT,
                             f"候选人信息：\n{user_profile_text}\n\n目标岗位：\n{job_info}")
        return self._parse_json(content)

    def get_stats(self) -> dict:
        """获取调用统计"""
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "model": self.model,
            "call_count": self._call_count,
            "cache_size": len(self._cache),
        }


# ============================================================
# 便捷工厂
# ============================================================

def create_analyzer(config: dict) -> LLMAnalyzer:
    """从配置创建分析器实例"""
    llm_config = config.get("llm", {})
    return LLMAnalyzer(llm_config)


def build_user_profile_text(config: dict) -> str:
    """
    从配置构建用户画像文本（用于 LLM 分析）

    Returns:
        结构化的用户描述文本
    """
    profile = config.get("profile", {})
    skills = config.get("skills", {})
    cities = config.get("cities", [])
    directions = config.get("job_directions", [])

    parts = [
        f"学校：{profile.get('school', '')}",
        f"专业：{profile.get('major', '')}",
        f"学历：{profile.get('degree', '')}",
        f"年级：{profile.get('grade', '')}",
        f"意向城市：{', '.join(cities)}",
        f"岗位方向：{', '.join(directions)}",
    ]

    # 技能
    if skills:
        skill_text = ", ".join(f"{k}({v}分)" for k, v in list(skills.items())[:10])
        parts.append(f"技能：{skill_text}")

    # 自我描述
    intro = profile.get("self_intro", "")
    if intro:
        parts.append(f"\n自我描述：{intro.strip()}")

    # 项目经历
    projects = profile.get("projects", [])
    if projects:
        proj_parts = []
        for p in projects:
            tech_str = ", ".join(p.get("tech", []))
            proj_parts.append(
                f"【{p.get('name', '')}】{p.get('role', '')} | {tech_str} | {p.get('desc', '')}"
            )
        parts.append(f"项目经历：\n" + "\n".join(proj_parts))

    return "\n".join(parts)
