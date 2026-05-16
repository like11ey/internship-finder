"""
采集器基类 —— 提供通用的 HTTP 请求、重试、反爬策略
"""

import time
import random
import requests
from abc import ABC, abstractmethod
from typing import Optional
from loguru import logger


class BaseCollector(ABC):
    """所有采集器的抽象基类"""

    def __init__(self, config: dict):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": config.get("user_agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        })
        self.request_delay = config.get("request_delay", 2.0)
        self._last_request = 0

    def _rate_limit(self):
        """请求限速"""
        elapsed = time.time() - self._last_request
        if elapsed < self.request_delay:
            sleep_time = self.request_delay - elapsed + random.uniform(0, 0.5)
            time.sleep(sleep_time)
        self._last_request = time.time()

    def get(self, url: str, params: dict = None, retries: int = 3) -> Optional[requests.Response]:
        """带重试的 GET 请求"""
        for attempt in range(retries):
            try:
                self._rate_limit()
                resp = self.session.get(url, params=params, timeout=15)
                if resp.status_code == 200:
                    return resp
                elif resp.status_code == 403:
                    logger.warning(f"请求被拒绝 (403): {url}")
                    # 可能被反爬，等待更长时间
                    time.sleep(10 * (attempt + 1))
                elif resp.status_code == 429:
                    logger.warning(f"请求过于频繁 (429): {url}，等待中...")
                    time.sleep(15 * (attempt + 1))
                else:
                    logger.warning(f"HTTP {resp.status_code}: {url}")
            except requests.RequestException as e:
                logger.warning(f"请求异常 (第{attempt+1}次): {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
        return None

    def post(self, url: str, data: dict = None, json: dict = None,
             retries: int = 3) -> Optional[requests.Response]:
        """带重试的 POST 请求"""
        for attempt in range(retries):
            try:
                self._rate_limit()
                resp = self.session.post(url, data=data, json=json, timeout=15)
                if resp.status_code == 200:
                    return resp
                elif resp.status_code in (403, 429):
                    time.sleep(10 * (attempt + 1))
            except requests.RequestException as e:
                logger.warning(f"POST 请求异常 (第{attempt+1}次): {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
        return None

    @abstractmethod
    def collect_jobs(self, cities: list[str], keywords: list[str]) -> list[dict]:
        """采集岗位信息，返回 dict 列表"""
        ...

    @abstractmethod
    def collect_interviews(self, companies: list[str]) -> list[dict]:
        """采集面经信息，返回 dict 列表"""
        ...
