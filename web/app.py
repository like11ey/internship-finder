"""
Web 服务 —— Flask 应用

提供：
  - 个人信息编辑表单（替代手动改 YAML）
  - 一键触发筛查
  - 报告在线查看
  - 大模型分析预览
"""

import sys
import os
import json
import threading
import time
from pathlib import Path

# 确保项目根在 sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

import yaml
from flask import Flask, render_template, request, jsonify, send_from_directory
from loguru import logger

from core.config import load_config, reload_config, CONFIG_PATH
from storage.db import init_db
from llm.analyzer import create_analyzer, build_user_profile_text

app = Flask(__name__,
            template_folder=str(Path(__file__).parent / "templates"),
            static_folder=str(Path(__file__).parent / "static"))

# 后台任务状态
_task_status = {"running": False, "result": None, "error": None, "report_path": None}

# ============================================================
# 工具函数
# ============================================================

def _read_config_raw() -> dict:
    """读取 config.yaml 原始内容"""
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def _write_config_raw(data: dict):
    """写入 config.yaml"""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

def _run_screening_async():
    """在后台线程中执行筛查"""
    global _task_status
    _task_status = {"running": True, "result": None, "error": None, "report_path": None}
    try:
        from main import run_once
        reload_config()
        report_path = run_once(mock=False)
        _task_status["result"] = "success"
        _task_status["report_path"] = report_path
    except Exception as e:
        logger.error(f"筛查失败: {e}")
        _task_status["result"] = "failed"
        _task_status["error"] = str(e)
    finally:
        _task_status["running"] = False

# ============================================================
# 页面路由
# ============================================================

@app.route("/")
def index():
    """主页 —— 报告查看"""
    # 找最新的报告文件
    outputs_dir = ROOT / "outputs"
    reports = sorted(outputs_dir.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
    latest_report = reports[0].name if reports else None
    return render_template("index.html", report_file=latest_report)

@app.route("/profile")
def profile_page():
    """个人信息编辑页面"""
    config = _read_config_raw()
    return render_template("profile.html", config=config)

# ============================================================
# API 路由
# ============================================================

@app.route("/api/profile", methods=["GET"])
def api_get_profile():
    """获取当前个人信息"""
    config = _read_config_raw()
    return jsonify({
        "profile": config.get("profile", {}),
        "cities": config.get("cities", []),
        "skills": config.get("skills", {}),
        "job_directions": config.get("job_directions", []),
        "preferred_companies": config.get("preferred_companies", []),
        "llm": {k: v for k, v in config.get("llm", {}).items() if k != "api_key"},
    })

@app.route("/api/profile", methods=["POST"])
def api_save_profile():
    """保存个人信息"""
    try:
        data = request.get_json()
        config = _read_config_raw()

        # 更新 profile 段
        if "profile" in data:
            config.setdefault("profile", {}).update(data["profile"])

        # 更新列表/字典字段
        for key in ["cities", "skills", "job_directions", "preferred_companies"]:
            if key in data and data[key] is not None:
                config[key] = data[key]

        # 更新 llm 段（保留 api_key 不被覆盖）
        if "llm" in data:
            llm_data = data["llm"]
            existing_llm = config.get("llm", {})
            existing_llm.update(llm_data)
            config["llm"] = existing_llm

        _write_config_raw(config)
        reload_config()
        return jsonify({"ok": True, "message": "保存成功"})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500

@app.route("/api/run", methods=["POST"])
def api_run_screening():
    """触发一次筛查"""
    global _task_status
    if _task_status.get("running"):
        return jsonify({"ok": False, "message": "筛查正在进行中，请稍候"}), 409

    thread = threading.Thread(target=_run_screening_async, daemon=True)
    thread.start()
    return jsonify({"ok": True, "message": "筛查已启动"})

@app.route("/api/status")
def api_status():
    """查询筛查任务状态"""
    return jsonify(_task_status)

@app.route("/api/report/<filename>")
def api_report_file(filename):
    """获取报告文件"""
    outputs_dir = ROOT / "outputs"
    return send_from_directory(str(outputs_dir), filename)

@app.route("/api/reports")
def api_list_reports():
    """列出所有报告"""
    outputs_dir = ROOT / "outputs"
    if not outputs_dir.exists():
        return jsonify([])
    reports = []
    for f in sorted(outputs_dir.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True):
        reports.append({
            "name": f.name,
            "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(f.stat().st_mtime)),
            "size": f.stat().st_size,
        })
    return jsonify(reports[:20])

@app.route("/api/llm/test", methods=["POST"])
def api_llm_test():
    """测试大模型连接"""
    config = load_config()
    analyzer = create_analyzer(config)
    if not analyzer.enabled:
        return jsonify({"ok": False, "message": "大模型未启用或 API Key 未配置"})

    # 发送测试请求
    user_text = build_user_profile_text(config)
    result = analyzer.semantic_match(
        user_text,
        "岗位：Python 后端开发实习生，要求：熟悉 Python、Django/Flask、MySQL、Git"
    )
    stats = analyzer.get_stats()

    return jsonify({
        "ok": True,
        "result": result,
        "stats": stats,
    })

@app.route("/api/llm/extract", methods=["POST"])
def api_llm_extract():
    """用大模型提取技能"""
    config = load_config()
    analyzer = create_analyzer(config)
    if not analyzer.enabled:
        return jsonify({"ok": False, "message": "大模型未启用"})

    data = request.get_json() or {}
    intro = data.get("self_intro", config.get("profile", {}).get("self_intro", ""))
    projects = data.get("projects", config.get("profile", {}).get("projects", []))

    result = analyzer.extract_skills(intro, projects)
    return jsonify({"ok": True, "result": result})

# ============================================================
# 启动
# ============================================================

def start_web(host: str = "0.0.0.0", port: int = 5000, debug: bool = False):
    """启动 Web 服务"""
    init_db()
    logger.info(f"Web 服务启动: http://{host}:{port}")
    print(f"\n  🌐 实习生岗位筛查工具\n")
    print(f"  📝 个人信息: http://{host}:{port}/profile")
    print(f"  📊 查看报告: http://{host}:{port}/\n")
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    import os as _os
    config = load_config()
    web_cfg = config.get("web", {})
    port = int(_os.environ.get("PORT", web_cfg.get("port", 5000)))
    start_web(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
