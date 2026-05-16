"""
牛客网采集器 —— 采集面经 / 讨论贴信息

真实模式: 通过 HTTP 请求 + HTML 解析获取面经数据
Mock 模式: 使用预置示例数据
"""

import time
import re
from datetime import datetime
from bs4 import BeautifulSoup
from loguru import logger

from core.collector import BaseCollector


class NowcoderCollector(BaseCollector):
    """牛客网面经采集器"""

    BASE_URL = "https://www.nowcoder.com"

    # 面经频道
    DISCUSS_URL = "https://www.nowcoder.com/discuss"

    # 搜索接口
    SEARCH_URL = "https://www.nowcoder.com/search"

    # 公司面经标签页
    COMPANY_TAG_URL = "https://www.nowcoder.com/discuss/tag"

    def collect_jobs(self, cities: list[str], keywords: list[str]) -> list[dict]:
        """牛客网本身岗位较少，主要用实习僧"""
        logger.info("牛客网岗位采集暂不实现，主要使用实习僧获取岗位")
        return []

    def collect_interviews(self, companies: list[str]) -> list[dict]:
        """
        采集指定公司的面经信息

        策略：
        1. 逐个公司搜索面经
        2. 解析面经列表
        3. 提取难度、内容等
        """
        all_interviews = []
        seen = set()

        for company in companies:
            logger.info(f"采集面经: 公司={company}")
            try:
                items = self._search_company(company)
                for item in items:
                    key = item.get("interview_id", "")
                    if key and key not in seen:
                        seen.add(key)
                        all_interviews.append(item)
                logger.info(f"  获取 {len(items)} 条面经")
            except Exception as e:
                logger.error(f"面经采集失败 [{company}]: {e}")
                continue

            time.sleep(self.request_delay * 1.5)

        if not all_interviews:
            logger.warning("牛客网面经采集结果为空，切换到 Mock 模式")
            return self._mock_interviews(companies)

        return all_interviews

    def _search_company(self, company: str) -> list[dict]:
        """
        搜索公司面经

        NOTE: 选择器需根据牛客网实际页面结构调整。
              牛客网可能使用 API 异步加载数据，
              如果 requests 拿不到内容需切换到 Playwright。
        """
        # 尝试通过标签页获取
        url = f"{self.COMPANY_TAG_URL}/{company}"
        resp = self.get(url)
        if resp is None:
            # 回退到搜索
            resp = self.get(self.SEARCH_URL, params={
                "type": "post",
                "query": f"{company} 面经",
            })

        if resp is None:
            return []

        soup = BeautifulSoup(resp.text, "lxml")

        interviews = []

        # ---- 通用帖子列表解析 ----
        cards = soup.select(
            '[class*="discuss"], [class*="post"], [class*="feed-item"], '
            '[class*="topic"], li[class*="list"]'
        )

        if not cards:
            logger.debug("未找到面经卡片，页面可能是 SPA")
            return []

        for card in cards[:15]:
            try:
                title_el = card.select_one(
                    '[class*="title"], h3, h4, [class*="subject"], a[href]'
                )
                content_el = card.select_one(
                    '[class*="content"], [class*="desc"], [class*="text"], p'
                )
                time_el = card.select_one('[class*="time"], [class*="date"], span')
                difficulty_el = card.select_one(
                    '[class*="diff"], [class*="level"], [class*="hard"]'
                )

                title = title_el.get_text(strip=True) if title_el else ""
                content = content_el.get_text(strip=True) if content_el else ""
                post_time = time_el.get_text(strip=True) if time_el else ""
                diff_text = difficulty_el.get_text(strip=True) if difficulty_el else ""

                if not title:
                    continue

                # 难度量化
                diff_score = self._quantify_difficulty(diff_text, content)

                interview_id = f"nc_{hash(f'{company}_{title}') & 0x7FFFFFFF:x}"

                interviews.append({
                    "source": "nowcoder",
                    "interview_id": interview_id,
                    "company": company,
                    "position": self._extract_position(title),
                    "title": title,
                    "content": content[:1000],
                    "difficulty": diff_text or "未知",
                    "difficulty_score": diff_score,
                    "likes": 0,
                    "post_date": post_time or datetime.now().strftime("%Y-%m-%d"),
                })
            except Exception as e:
                logger.debug(f"解析面经卡片失败: {e}")
                continue

        return interviews

    @staticmethod
    def _extract_position(title: str) -> str:
        """从标题中提取岗位"""
        positions = ["后端", "前端", "算法", "测试", "数据", "运维", "产品", "客户端"]
        for p in positions:
            if p in title:
                return p
        return ""

    @staticmethod
    def _quantify_difficulty(diff_text: str, content: str) -> float:
        """
        将难度描述量化为 1-5 分

        综合以下因素：
        - 直接标注的难度标签
        - 内容中的难度关键词
        """
        score = 3.0  # 默认中等

        text = diff_text + content

        if any(w in text for w in ["困难", "很难", "非常难", "地狱", "hard"]):
            score = 4.5
        elif any(w in text for w in ["较难", "偏难", "有点难", "不容易"]):
            score = 3.8
        elif any(w in text for w in ["中等", "一般", "还行", "正常"]):
            score = 3.0
        elif any(w in text for w in ["简单", "容易", "简单", "基础"]):
            score = 2.0
        elif any(w in text for w in ["很容易", "非常容易", "easy"]):
            score = 1.5

        # 因子：如果提到"手撕"（手写代码）加一点分
        if "手撕" in text or "算法题" in text:
            score = min(5.0, score + 0.5)

        return score

    # ============================================================
    # Mock 数据
    # ============================================================

    @staticmethod
    def _mock_interviews(companies: list[str]) -> list[dict]:
        """生成模拟面经数据"""
        logger.info("使用 Mock 数据生成面经...")

        mock_data = [
            {
                "company": "字节跳动", "position": "后端",
                "title": "字节跳动后端开发实习生面经",
                "content": "一面：项目深挖 + 算法题（LRU Cache）+ 操作系统。"
                           "二面：系统设计 + MySQL 索引 + Redis 数据结构。"
                           "三面：HR 面。整体难度中等偏上，面试官很专业。",
                "difficulty": "中等",
                "difficulty_score": 3.5,
                "likes": 128,
            },
            {
                "company": "字节跳动", "position": "测试开发",
                "title": "字节测开实习面试",
                "content": "一面：测试用例设计 + Python 编程 + 自动化框架理解。"
                           "问得很细，需要真正做过项目。",
                "difficulty": "中等",
                "difficulty_score": 3.0,
                "likes": 56,
            },
            {
                "company": "阿里巴巴", "position": "Java",
                "title": "阿里Java实习面经（已拿offer）",
                "content": "简历面 + 技术面 + 交叉面 + HR面。问了很多JVM和并发编程，"
                           "算法题难度 LeetCode Medium。准备充分的话不难。",
                "difficulty": "较难",
                "difficulty_score": 4.0,
                "likes": 256,
            },
            {
                "company": "腾讯", "position": "数据分析",
                "title": "腾讯数据分析实习面经",
                "content": "SQL 手写 + Python 数据分析 + 业务场景题。"
                           "考察统计学基础和AB测试。难度中等。",
                "difficulty": "中等",
                "difficulty_score": 3.0,
                "likes": 89,
            },
            {
                "company": "华为", "position": "后端",
                "title": "华为云计算实习面试",
                "content": "一面：基础八股 + 项目 + 手撕代码。"
                           "二面：主管面，主要聊项目和对云计算的看法。"
                           "华子面试比较友好，难度中等。",
                "difficulty": "中等",
                "difficulty_score": 2.8,
                "likes": 167,
            },
            {
                "company": "华为", "position": "嵌入式",
                "title": "华为嵌入式开发实习面经",
                "content": "手撕代码 + C语言基础 + Linux内核。"
                           "面试官很nice，会给提示。难度中等偏下。",
                "difficulty": "中等",
                "difficulty_score": 2.5,
                "likes": 45,
            },
            {
                "company": "美团", "position": "算法",
                "title": "美团算法实习面经",
                "content": "LeetCode Hard 手撕 + 机器学习基础 + 项目。"
                           "美团的算法要求很高，难度较大。",
                "difficulty": "较难",
                "difficulty_score": 4.2,
                "likes": 134,
            },
            {
                "company": "百度", "position": "NLP",
                "title": "百度NLP算法实习面经",
                "content": "论文讲解 + Transformer深入原理 + 代码实现 Attention。"
                           "实验室方向对口的话难度中等，否则偏难。",
                "difficulty": "较难",
                "difficulty_score": 3.8,
                "likes": 92,
            },
            {
                "company": "荣耀", "position": "软件开发",
                "title": "荣耀软件开发实习面经",
                "content": "Java基础 + Android + 项目经历。"
                           "难度中等偏下，对基础知识要求扎实。",
                "difficulty": "中等",
                "difficulty_score": 2.5,
                "likes": 34,
            },
            {
                "company": "中兴通讯", "position": "通信",
                "title": "中兴通信软件开发实习",
                "content": "C语言 + 计算机网络 + 通信协议基础。"
                           "面试流程比较标准，难度不大。",
                "difficulty": "简单",
                "difficulty_score": 2.0,
                "likes": 67,
            },
            {
                "company": "ThoughtWorks", "position": "软件开发",
                "title": "ThoughtWorks 实习面试",
                "content": "结对编程 + 项目讨论 + 文化面。"
                           "更看重沟通和思维，技术难度中等。",
                "difficulty": "中等",
                "difficulty_score": 2.8,
                "likes": 78,
            },
            {
                "company": "海康威视", "position": "AI算法",
                "title": "海康威视视觉算法实习面经",
                "content": "图像处理基础 + PyTorch + 项目。"
                           "问得很深入，需要真正理解算法原理。难度中等偏上。",
                "difficulty": "中等",
                "difficulty_score": 3.5,
                "likes": 56,
            },
            {
                "company": "京东", "position": "Java",
                "title": "京东Java开发实习",
                "content": "Java基础 + Spring + 数据库 + 手撕代码。"
                           "整体难度中等，八股文准备充分即可。",
                "difficulty": "中等",
                "difficulty_score": 3.0,
                "likes": 112,
            },
            {
                "company": "滴滴", "position": "后端",
                "title": "滴滴后端实习面经",
                "content": "MySQL + Redis + 分布式 + 算法。"
                           "面试官很喜欢问场景设计题，难度中等偏上。",
                "difficulty": "中等",
                "difficulty_score": 3.5,
                "likes": 73,
            },
            {
                "company": "小米", "position": "嵌入式",
                "title": "小米IoT嵌入式实习",
                "content": "C语言 + RTOS + 硬件基础。"
                           "对底层理解要求较高，难度中等。",
                "difficulty": "中等",
                "difficulty_score": 3.0,
                "likes": 41,
            },
            {
                "company": "网易", "position": "后端",
                "title": "网易游戏后端实习",
                "content": "C++ / Python 编程 + 网络编程 + 算法。"
                           "游戏公司技术要求全面，难度中等偏上。",
                "difficulty": "中等",
                "difficulty_score": 3.5,
                "likes": 88,
            },
            {
                "company": "拼多多", "position": "后端",
                "title": "拼多多后端开发实习",
                "content": "算法题难度较高 + 系统设计 + 数据库。"
                           "整体偏难，对算法和系统设计都有要求。",
                "difficulty": "较难",
                "difficulty_score": 4.0,
                "likes": 145,
            },
            {
                "company": "小红书", "position": "数据开发",
                "title": "小红书数据开发实习面经",
                "content": "SQL + Spark + 数据仓库理论。"
                           "面试比较友好，难度中等偏下。",
                "difficulty": "中等",
                "difficulty_score": 2.5,
                "likes": 52,
            },
            {
                "company": "中国电子科技集团", "position": "软件开发",
                "title": "中电科软件开发实习面试",
                "content": "基础知识 + 项目 + 综合素质。"
                           "国企风格，技术深度要求不高，难度偏简单。",
                "difficulty": "简单",
                "difficulty_score": 1.8,
                "likes": 23,
            },
        ]

        # 筛选匹配的公司
        company_set = set(companies)
        filtered = [
            m for m in mock_data
            if not company_set or m["company"] in company_set
        ]
        if not filtered:
            filtered = mock_data

        interviews = []
        for md in filtered:
            interview_id = f"nc_mock_{hash(md['company'] + md['title']) & 0x7FFFFFFF:x}"
            interviews.append({
                "source": "nowcoder",
                "interview_id": interview_id,
                "company": md["company"],
                "position": md["position"],
                "title": md["title"],
                "content": md["content"],
                "difficulty": md["difficulty"],
                "difficulty_score": md["difficulty_score"],
                "likes": md["likes"],
                "post_date": datetime.now().strftime("%Y-%m-%d"),
            })

        logger.info(f"Mock 面经生成: {len(interviews)} 条")
        return interviews
