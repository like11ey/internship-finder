# 实习岗位智能筛查工具

> 面向计算机专业研究生，每日自动采集实习僧+牛客网岗位，根据个人技能智能匹配排序，结合面经评估面试通过概率。

## 功能

- **多源采集** — 实习僧岗位 + 牛客网面经，断网自动降级 Mock 数据
- **智能匹配** — 四维打分（技能/城市/学历/公司偏好），支持关联技能弥补
- **面试评估** — 结合面经难度 + 城市竞争度 + 技能匹配度计算通过概率
- **大模型增强** — 接入 DeepSeek/智谱GLM/通义千问，语义匹配 + 个性化建议
- **Web 界面** — Flask 表单编辑个人信息，一键筛查，报告在线查看
- **HTML 报告** — 交互式筛选（概率/城市/搜索），浏览器直接打开

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 复制配置并填写个人信息
copy config.example.yaml config.yaml
# 编辑 config.yaml：填技能、城市、可选大模型 API Key

# 3. 运行（Mock 模式先看效果）
python main.py --mock

# 4. 启动 Web 界面
python main.py --web
# 浏览器打开 http://127.0.0.1:5000/
```

## 项目结构

```
├── main.py                 # 入口：筛查 / Web / 定时
├── config.example.yaml     # 配置模板
├── core/                   # 核心引擎
│   ├── collector.py        #   采集器基类
│   ├── shixiseng.py        #   实习僧采集
│   ├── nowcoder.py         #   牛客网面经采集
│   ├── matcher.py          #   匹配引擎（技能/城市/学历）
│   └── config.py           #   配置加载
├── analyzer/               # 分析模块
│   └── interview_prob.py   #   面试概率评估
├── llm/                    # 大模型
│   └── analyzer.py         #   DeepSeek/GLM API 调用
├── storage/db.py           # SQLite 数据层
├── output/                 # 报告生成
│   ├── reporter.py         #   Jinja2 渲染
│   └── templates/          #   HTML 模板
└── web/                    # Web 界面
    ├── app.py              #   Flask 服务
    └── templates/          #   页面模板
```

## 大模型配置（可选）

在 `config.yaml` 中填写：

```yaml
llm:
  enabled: true
  provider: "deepseek"
  api_key: "你的API_KEY"    # https://platform.deepseek.com 免费注册
  model: "deepseek-chat"
```

大模型可以：从自然语言提取技能标签、做语义匹配打分、生成个性化投递建议。

## 注意事项

- `config.yaml` 包含 API Key，**不会被 Git 提交**（已在 .gitignore 中）
- 真实采集需要调整 CSS 选择器（网站 DOM 结构变化）
- Mock 模式内置 20 家公司真实面经，离线可用
