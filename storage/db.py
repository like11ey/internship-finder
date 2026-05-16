"""
数据存储层 —— SQLite 数据库模型与数据访问对象 (DAO)

表结构:
  - jobs:          实习岗位信息
  - interviews:    面经信息
  - match_results: 匹配结果
  - run_log:       运行日志
"""

import sqlite3
import json
import os
from datetime import datetime
from contextlib import contextmanager
from typing import Optional, Any
from loguru import logger

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "internship.db")


def get_connection() -> sqlite3.Connection:
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def get_db():
    """上下文管理器，自动提交/回滚"""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ============================================================
# 建表
# ============================================================

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT    NOT NULL,       -- shixiseng / nowcoder
    job_id        TEXT    NOT NULL,       -- 原始平台 ID
    title         TEXT    NOT NULL,
    company       TEXT    NOT NULL,
    city          TEXT    DEFAULT '',
    district      TEXT    DEFAULT '',
    description   TEXT    DEFAULT '',
    requirements  TEXT    DEFAULT '',
    url           TEXT    DEFAULT '',
    salary        TEXT    DEFAULT '',
    job_type      TEXT    DEFAULT '实习',
    post_date     TEXT    DEFAULT '',
    crawl_date    TEXT    NOT NULL,
    is_active     INTEGER DEFAULT 1,
    UNIQUE(source, job_id)
);

CREATE TABLE IF NOT EXISTS interviews (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT    NOT NULL,
    interview_id    TEXT    NOT NULL,
    company         TEXT    NOT NULL,
    position        TEXT    DEFAULT '',
    title           TEXT    DEFAULT '',
    content         TEXT    DEFAULT '',
    difficulty      TEXT    DEFAULT '',    -- 简单/中等/困难
    difficulty_score REAL  DEFAULT 0,      -- 1-5 量化
    likes           INTEGER DEFAULT 0,
    post_date       TEXT    DEFAULT '',
    crawl_date      TEXT    NOT NULL,
    UNIQUE(source, interview_id)
);

CREATE TABLE IF NOT EXISTS match_results (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id            INTEGER NOT NULL REFERENCES jobs(id),
    city_match        REAL    DEFAULT 0,   -- 0-1
    skill_match       REAL    DEFAULT 0,   -- 0-1
    company_pref      REAL    DEFAULT 0,   -- 0-1
    degree_match      REAL    DEFAULT 0,   -- 0-1
    total_score       REAL    DEFAULT 0,   -- 加权总分
    interview_prob    REAL    DEFAULT 0,   -- 面试通过概率 0-1
    skill_detail      TEXT    DEFAULT '{}',-- JSON: {skill: score}
    match_date        TEXT    NOT NULL,
    UNIQUE(job_id, match_date)
);

CREATE TABLE IF NOT EXISTS run_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time  TEXT    NOT NULL,
    end_time    TEXT,
    jobs_fetched INTEGER DEFAULT 0,
    interviews_fetched INTEGER DEFAULT 0,
    matches     INTEGER DEFAULT 0,
    status      TEXT    DEFAULT 'running',  -- running / success / failed
    error       TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_company  ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_city     ON jobs(city);
CREATE INDEX IF NOT EXISTS idx_jobs_crawl    ON jobs(crawl_date);
CREATE INDEX IF NOT EXISTS idx_interviews_company ON interviews(company);
CREATE INDEX IF NOT EXISTS idx_match_job     ON match_results(job_id);
CREATE INDEX IF NOT EXISTS idx_match_date    ON match_results(match_date);
"""


def init_db():
    """初始化数据库表结构"""
    with get_db() as conn:
        conn.executescript(SCHEMA)
    logger.info(f"数据库初始化完成: {DB_PATH}")


# ============================================================
# Jobs DAO
# ============================================================

class JobDAO:
    @staticmethod
    def upsert(source: str, job_id: str, title: str, company: str, **kwargs) -> int:
        """插入或更新岗位信息，返回内部 id"""
        fields = {
            "source": source, "job_id": job_id, "title": title, "company": company,
            "city": kwargs.get("city", ""),
            "district": kwargs.get("district", ""),
            "description": kwargs.get("description", ""),
            "requirements": kwargs.get("requirements", ""),
            "url": kwargs.get("url", ""),
            "salary": kwargs.get("salary", ""),
            "job_type": kwargs.get("job_type", "实习"),
            "post_date": kwargs.get("post_date", ""),
            "crawl_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        with get_db() as conn:
            conn.execute("""
                INSERT INTO jobs (source, job_id, title, company, city, district,
                    description, requirements, url, salary, job_type, post_date, crawl_date)
                VALUES (:source, :job_id, :title, :company, :city, :district,
                    :description, :requirements, :url, :salary, :job_type, :post_date, :crawl_date)
                ON CONFLICT(source, job_id) DO UPDATE SET
                    title=excluded.title, company=excluded.company,
                    city=excluded.city, description=excluded.description,
                    requirements=excluded.requirements, url=excluded.url,
                    salary=excluded.salary, crawl_date=excluded.crawl_date,
                    is_active=1
            """, fields)
            # 可靠获取内部 id（ON CONFLICT 时 lastrowid 不可靠）
            row = conn.execute(
                "SELECT id FROM jobs WHERE source=? AND job_id=?",
                (source, job_id)
            ).fetchone()
            return row["id"] if row else 0

    @staticmethod
    def get_recent(days: int = 3, limit: int = 200) -> list[dict]:
        """获取最近 N 天内的岗位"""
        with get_db() as conn:
            rows = conn.execute("""
                SELECT * FROM jobs
                WHERE is_active = 1
                  AND crawl_date >= date('now', '-' || ? || ' days')
                ORDER BY crawl_date DESC
                LIMIT ?
            """, (days, limit)).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def get_by_id(job_id: int) -> Optional[dict]:
        with get_db() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def mark_inactive(days: int = 30):
        """将超过 N 天未更新的岗位标记为失效"""
        with get_db() as conn:
            conn.execute("""
                UPDATE jobs SET is_active=0
                WHERE crawl_date < date('now', '-' || ? || ' days')
            """, (days,))


# ============================================================
# Interviews DAO
# ============================================================

class InterviewDAO:
    @staticmethod
    def upsert(source: str, interview_id: str, company: str, **kwargs) -> int:
        fields = {
            "source": source, "interview_id": interview_id, "company": company,
            "position": kwargs.get("position", ""),
            "title": kwargs.get("title", ""),
            "content": kwargs.get("content", ""),
            "difficulty": kwargs.get("difficulty", ""),
            "difficulty_score": kwargs.get("difficulty_score", 0),
            "likes": kwargs.get("likes", 0),
            "post_date": kwargs.get("post_date", ""),
            "crawl_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        with get_db() as conn:
            cursor = conn.execute("""
                INSERT INTO interviews (source, interview_id, company, position,
                    title, content, difficulty, difficulty_score, likes, post_date, crawl_date)
                VALUES (:source, :interview_id, :company, :position,
                    :title, :content, :difficulty, :difficulty_score, :likes, :post_date, :crawl_date)
                ON CONFLICT(source, interview_id) DO UPDATE SET
                    company=excluded.company, position=excluded.position,
                    title=excluded.title, content=excluded.content,
                    difficulty=excluded.difficulty, difficulty_score=excluded.difficulty_score,
                    likes=excluded.likes, crawl_date=excluded.crawl_date
            """, fields)
            return cursor.lastrowid

    @staticmethod
    def get_by_company(company: str, limit: int = 20) -> list[dict]:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT * FROM interviews
                WHERE company LIKE ?
                ORDER BY crawl_date DESC
                LIMIT ?
            """, (f"%{company}%", limit)).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def get_company_difficulty(company: str) -> Optional[float]:
        """获取某公司的平均面试难度评分"""
        with get_db() as conn:
            row = conn.execute("""
                SELECT AVG(difficulty_score) as avg_diff, COUNT(*) as cnt
                FROM interviews
                WHERE company LIKE ? AND difficulty_score > 0
            """, (f"%{company}%",)).fetchone()
        if row and row["cnt"] > 0:
            return row["avg_diff"]
        return None


# ============================================================
# Match Results DAO
# ============================================================

class MatchDAO:
    @staticmethod
    def save(job_id: int, city_match: float, skill_match: float,
             company_pref: float, degree_match: float, total_score: float,
             interview_prob: float, skill_detail: dict) -> int:
        fields = {
            "job_id": job_id,
            "city_match": city_match,
            "skill_match": skill_match,
            "company_pref": company_pref,
            "degree_match": degree_match,
            "total_score": total_score,
            "interview_prob": interview_prob,
            "skill_detail": json.dumps(skill_detail, ensure_ascii=False),
            "match_date": datetime.now().strftime("%Y-%m-%d"),
        }
        with get_db() as conn:
            cursor = conn.execute("""
                INSERT INTO match_results (job_id, city_match, skill_match,
                    company_pref, degree_match, total_score, interview_prob,
                    skill_detail, match_date)
                VALUES (:job_id, :city_match, :skill_match, :company_pref,
                    :degree_match, :total_score, :interview_prob,
                    :skill_detail, :match_date)
                ON CONFLICT(job_id, match_date) DO UPDATE SET
                    city_match=excluded.city_match,
                    skill_match=excluded.skill_match,
                    company_pref=excluded.company_pref,
                    degree_match=excluded.degree_match,
                    total_score=excluded.total_score,
                    interview_prob=excluded.interview_prob,
                    skill_detail=excluded.skill_detail
            """, fields)
            return cursor.lastrowid

    @staticmethod
    def get_today_top(limit: int = 30) -> list[dict]:
        """获取今日匹配结果的 Top N，带岗位详情"""
        with get_db() as conn:
            rows = conn.execute("""
                SELECT m.*, j.title, j.company, j.city, j.salary,
                       j.description, j.url, j.job_type
                FROM match_results m
                JOIN jobs j ON m.job_id = j.id
                WHERE m.match_date = date('now')
                ORDER BY m.total_score DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]


# ============================================================
# Run Log DAO
# ============================================================

class RunLogDAO:
    @staticmethod
    def start() -> int:
        with get_db() as conn:
            cursor = conn.execute(
                "INSERT INTO run_log (start_time, status) VALUES (?, 'running')",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),)
            )
            return cursor.lastrowid

    @staticmethod
    def finish(run_id: int, jobs: int = 0, interviews: int = 0,
               matches: int = 0, status: str = "success", error: str = None):
        with get_db() as conn:
            conn.execute("""
                UPDATE run_log
                SET end_time=?, jobs_fetched=?, interviews_fetched=?,
                    matches=?, status=?, error=?
                WHERE id=?
            """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                  jobs, interviews, matches, status, error, run_id))


if __name__ == "__main__":
    init_db()
    print("数据库初始化完成")
