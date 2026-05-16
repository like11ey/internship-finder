"""
实习僧采集器 —— 采集实习僧网站上的实习岗位信息

真实模式: 通过 HTTP 请求 + HTML 解析获取数据
Mock 模式: 使用预置示例数据，用于不依赖网络的演示和测试
"""

import time
import re
from datetime import datetime
from bs4 import BeautifulSoup
from loguru import logger

from core.collector import BaseCollector


class ShixisengCollector(BaseCollector):
    """实习僧岗位采集器"""

    BASE_URL = "https://www.shixiseng.com"

    # 实习僧搜索 API 端点（推测，实际可能不同）
    SEARCH_URL = "https://www.shixiseng.com/interns"

    def collect_jobs(self, cities: list[str], keywords: list[str]) -> list[dict]:
        """
        采集实习岗位信息

        策略：
        1. 逐个城市 + 关键词组合搜索
        2. 解析搜索结果列表
        3. 去重后返回
        """
        all_jobs = []
        seen = set()

        for city in cities:
            for kw in keywords:
                logger.info(f"采集实习僧: 城市={city}, 关键词={kw}")
                try:
                    jobs = self._search(city, kw)
                    for job in jobs:
                        key = (job.get("job_id", ""), job.get("company", ""))
                        if key not in seen:
                            seen.add(key)
                            all_jobs.append(job)
                    logger.info(f"  获取 {len(jobs)} 条结果")
                except Exception as e:
                    logger.error(f"采集失败 [{city}/{kw}]: {e}")
                    continue

                # 搜索间隔
                time.sleep(self.request_delay * 1.5)

        if not all_jobs:
            logger.warning("实习僧采集结果为空，切换到 Mock 模式")
            return self._mock_jobs(cities, keywords)

        return all_jobs

    def _search(self, city: str, keyword: str) -> list[dict]:
        """
        搜索实习岗位

        NOTE: 以下为通用解析逻辑。实习僧实际页面可能是 SPA，
              如果 requests 获取不到内容，需要切换到 Playwright/Selenium。
              选择器需要根据实际 DOM 结构调整。
        """
        params = {
            "k": keyword,
            "c": city,
        }
        resp = self.get(self.SEARCH_URL, params=params)
        if resp is None:
            logger.warning(f"请求失败: {self.SEARCH_URL}?k={keyword}&c={city}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")

        jobs = []

        # ---- 通用岗位卡片解析 ----
        # 尝试多种常见选择器模式
        # 模式 A: class 包含 "intern" 或 "job" 的卡片
        cards = soup.select('[class*="intern"], [class*="job-item"], [class*="position"]')
        if not cards:
            # 模式 B: 列表项
            cards = soup.select('li[class*="list"], .list-item, .item')

        if not cards:
            # 可能是 SPA 页面，返回空让上层切换 mock
            logger.debug("未找到岗位卡片，页面可能是 SPA 动态渲染")
            return []

        for card in cards[:20]:  # 每页最多取 20 个
            try:
                # ---- 提取字段（选择器需根据实际页面调整） ----
                title_el = (
                    card.select_one('[class*="title"], h3, h4, [class*="name"]')
                )
                company_el = (
                    card.select_one('[class*="company"], [class*="corp"], [class*="org"]')
                )
                city_el = (
                    card.select_one('[class*="city"], [class*="location"], [class*="addr"]')
                )
                salary_el = (
                    card.select_one('[class*="salary"], [class*="pay"], [class*="money"]')
                )
                link_el = card.select_one("a[href]")
                desc_el = (
                    card.select_one('[class*="desc"], [class*="detail"], [class*="info"], p')
                )

                title = title_el.get_text(strip=True) if title_el else ""
                company = company_el.get_text(strip=True) if company_el else ""
                city_text = city_el.get_text(strip=True) if city_el else city
                salary = salary_el.get_text(strip=True) if salary_el else ""
                desc = desc_el.get_text(strip=True) if desc_el else ""

                url = ""
                if link_el and link_el.get("href"):
                    href = link_el["href"]
                    url = href if href.startswith("http") else self.BASE_URL + href

                if not title or not company:
                    continue

                # 生成唯一 ID
                job_id = f"sxs_{hash(f'{company}_{title}_{city_text}') & 0x7FFFFFFF:x}"

                jobs.append({
                    "source": "shixiseng",
                    "job_id": job_id,
                    "title": title,
                    "company": company,
                    "city": city_text,
                    "district": "",
                    "description": desc[:500] if desc else "",
                    "requirements": "",
                    "url": url,
                    "salary": salary,
                    "job_type": "实习",
                    "post_date": datetime.now().strftime("%Y-%m-%d"),
                })
            except Exception as e:
                logger.debug(f"解析卡片失败: {e}")
                continue

        return jobs

    def collect_interviews(self, companies: list[str]) -> list[dict]:
        """实习僧本身面经较少，此方法主要靠牛客网"""
        logger.info("实习僧不支持面经采集，请使用牛客网")
        return []

    # ============================================================
    # Mock 数据 —— 用于演示和测试
    # ============================================================

    @staticmethod
    def _mock_jobs(cities: list[str], keywords: list[str]) -> list[dict]:
        """生成模拟实习岗位数据"""
        logger.info("使用 Mock 数据生成实习岗位...")

        mock_companies = [
            {
                "company": "字节跳动", "title": "后端开发实习生",
                "desc": "负责抖音后端服务开发，参与高并发系统设计与优化。"
                        "要求：掌握 Python/Go，熟悉 MySQL、Redis，了解分布式系统原理。",
                "requirements": "Python/Go, MySQL, Redis, 分布式",
                "city": "北京", "salary": "400-500/天",
            },
            {
                "company": "阿里巴巴", "title": "Java开发实习生",
                "desc": "参与淘宝核心交易链路开发，负责订单系统模块。"
                        "要求：扎实的 Java 基础，熟悉 Spring 框架，了解微服务架构。",
                "requirements": "Java, Spring, 微服务, MySQL",
                "city": "杭州", "salary": "350-450/天",
            },
            {
                "company": "腾讯", "title": "数据分析实习生",
                "desc": "负责微信支付数据分析和用户行为建模。"
                        "要求：Python/SQL，熟悉机器学习算法，有数据分析经验。",
                "requirements": "Python, SQL, 机器学习, 数据分析",
                "city": "深圳", "salary": "300-400/天",
            },
            {
                "company": "华为", "title": "云计算实习生",
                "desc": "参与华为云基础设施研发，负责容器编排和K8s相关开发。"
                        "要求：Linux, Docker, Kubernetes, Python/Go。",
                "requirements": "Linux, Docker, Kubernetes, Python",
                "city": "西安", "salary": "250-350/天",
            },
            {
                "company": "美团", "title": "算法实习生",
                "desc": "参与外卖配送调度算法优化。"
                        "要求：扎实的算法基础，Python/C++，熟悉运筹优化者优先。",
                "requirements": "Python, C++, 算法, 运筹优化",
                "city": "北京", "salary": "350-450/天",
            },
            {
                "company": "字节跳动", "title": "测试开发实习生",
                "desc": "负责飞书自动化测试框架开发。"
                        "要求：Python, 测试框架, CI/CD, 良好的逻辑思维能力。",
                "requirements": "Python, 测试, CI/CD",
                "city": "上海", "salary": "400-500/天",
            },
            {
                "company": "百度", "title": "NLP算法实习生",
                "desc": "参与大模型应用开发，RAG 系统优化。"
                        "要求：Python, PyTorch, NLP基础, 了解 Transformer。",
                "requirements": "Python, PyTorch, NLP, 深度学习",
                "city": "北京", "salary": "350-450/天",
            },
            {
                "company": "网易", "title": "游戏后端实习生",
                "desc": "参与游戏服务器开发。要求：C++/Python，熟悉网络编程。",
                "requirements": "C++, Python, 网络编程, Linux",
                "city": "杭州", "salary": "300-400/天",
            },
            {
                "company": "滴滴", "title": "后端开发实习生",
                "desc": "负责出行平台核心服务开发。"
                        "要求：Java/Python, MySQL, Redis, 高并发经验。",
                "requirements": "Java, Python, MySQL, Redis",
                "city": "北京", "salary": "350-450/天",
            },
            {
                "company": "小米", "title": "嵌入式实习生",
                "desc": "参与 IoT 设备固件开发。要求：C/C++，了解 RTOS 或 Linux 内核。",
                "requirements": "C, C++, 嵌入式, Linux",
                "city": "北京", "salary": "300-400/天",
            },
            {
                "company": "华为", "title": "后端开发实习生",
                "desc": "参与鸿蒙生态服务端开发。"
                        "要求：Java/Python, Spring Boot, 分布式系统。",
                "requirements": "Java, Python, Spring, 分布式",
                "city": "西安", "salary": "250-350/天",
            },
            {
                "company": "京东", "title": "Java开发实习生",
                "desc": "参与京东物流仓储系统开发。"
                        "要求：Java, Spring Cloud, MySQL, Kafka。",
                "requirements": "Java, Spring, MySQL, Kafka",
                "city": "北京", "salary": "300-400/天",
            },
            {
                "company": "拼多多", "title": "后端实习生",
                "desc": "参与电商平台后端服务开发。"
                        "要求：Python/Java, MySQL, Redis, 高并发。",
                "requirements": "Python, Java, MySQL, Redis",
                "city": "上海", "salary": "400-500/天",
            },
            {
                "company": "字节跳动", "title": "前端开发实习生",
                "desc": "参与飞书前端开发。要求：Vue/React, TypeScript, CSS。",
                "requirements": "Vue, React, TypeScript, JavaScript",
                "city": "上海", "salary": "400-500/天",
            },
            {
                "company": "小红书", "title": "数据开发实习生",
                "desc": "负责数据仓库建设和 ETL 流程开发。"
                        "要求：SQL, Python, Spark, 数据仓库理论。",
                "requirements": "SQL, Python, Spark, 数仓",
                "city": "上海", "salary": "350-450/天",
            },
            # ---- 西安本地企业 ----
            {
                "company": "荣耀", "title": "软件开发实习生",
                "desc": "参与手机系统应用开发。要求：Java/Kotlin/Python，熟悉 Android。",
                "requirements": "Java, Python, Android, Kotlin",
                "city": "西安", "salary": "200-300/天",
            },
            {
                "company": "中兴通讯", "title": "通信软件实习生",
                "desc": "参与 5G 基站软件开发。要求：C/C++, Linux, 通信协议基础。",
                "requirements": "C, C++, Linux, 通信",
                "city": "西安", "salary": "200-300/天",
            },
            {
                "company": "ThoughtWorks", "title": "软件开发实习生",
                "desc": "参与敏捷开发项目。要求：Java/Python/C#，良好的沟通能力。",
                "requirements": "Java, Python, C#, 敏捷开发",
                "city": "西安", "salary": "250-350/天",
            },
            {
                "company": "海康威视", "title": "AI算法实习生",
                "desc": "参与计算机视觉算法研发。"
                        "要求：Python, PyTorch/OpenCV, 深度学习基础。",
                "requirements": "Python, PyTorch, OpenCV, 计算机视觉",
                "city": "西安", "salary": "250-350/天",
            },
            {
                "company": "中国电子科技集团", "title": "软件开发实习生",
                "desc": "参与军工信息化系统开发。要求：Java/C++, SQL, Linux。",
                "requirements": "Java, C++, SQL, Linux",
                "city": "西安", "salary": "150-250/天",
            },
        ]

        # 根据城市筛选
        filtered = [
            c for c in mock_companies
            if c["city"] in cities or any(k in c["title"] or k in c["desc"]
                                          for k in keywords)
        ]
        if not filtered:
            filtered = mock_companies

        jobs = []
        for mc in filtered:
            job_id = f"sxs_mock_{hash(mc['company'] + mc['title']) & 0x7FFFFFFF:x}"
            jobs.append({
                "source": "shixiseng",
                "job_id": job_id,
                "title": mc["title"],
                "company": mc["company"],
                "city": mc["city"],
                "district": "",
                "description": mc["desc"],
                "requirements": mc["requirements"],
                "url": f"{ShixisengCollector.BASE_URL}/interns?k={mc['title']}&c={mc['city']}",
                "salary": mc["salary"],
                "job_type": "实习",
                "post_date": datetime.now().strftime("%Y-%m-%d"),
            })

        logger.info(f"Mock 数据生成: {len(jobs)} 条岗位")
        return jobs
