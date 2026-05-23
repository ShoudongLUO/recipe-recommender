# 菜谱推荐系统

> 本地 Web 应用 + Gemini API
> 单用户自用工具
> 设计冻结日期：2026-05-22

---

## 1. 目标与范围

帮个人用户解决"今天吃什么"这一日常决策问题。系统根据用户的口味画像、会做的菜库与本周可用食材，为每餐推荐**会做的菜** + **可尝试的新菜**两类候选；通过打卡数据隐式学习偏好，越用越准。

### 1.1 In Scope
- 单用户（自用，不区分账号）
- 口味画像维护（菜系 + 辣度 + 忌口）
- "会做的菜"录入（仅菜名，Gemini 后台补食材/菜系/口味标签）
- 每周可用食材的维护
- 按餐推荐（早/午/晚），输出"会的菜 Top 2" + "新菜 2 道"
- 打卡（记录实际做了哪道菜）
- 隐式偏好学习（基于打卡频次）
- 一菜一周不重复推荐
- Gemini API 调用，失败降级

### 1.2 Out of Scope（v1 不做）
- 多用户 / 账号系统 / 登录
- 显式评分（1–5 星）
- 周计划表（7 × 3 网格）
- 食材采购清单导出
- 菜品图片
- 营养成分分析
- 公网部署 / HTTPS / 反向代理
- 微信小程序

### 1.3 运行前提
- 本机已能访问 `generativelanguage.googleapis.com`（自带 VPN/代理）
- 本机已装 Python 3.10+
- 浏览器（Chrome/Edge/Safari 均可）

---

## 2. 技术栈与架构

### 2.1 技术栈

| 层 | 技术 | 选型理由 |
|---|---|---|
| 后端 | Python 3.10+ / FastAPI | async、自动 OpenAPI 文档、对 LLM 集成友好 |
| 数据库 | SQLite（单文件 `data.db`） | 零部署、零配置、自用足够；用 SQLAlchemy 2.0 |
| Gemini 客户端 | `google-genai` 官方 SDK | 官方支持、文档全 |
| 前端 | 单页 HTML + Vue 3（CDN 引入）+ 原生 fetch | 零构建、零 npm、改一行刷一下就生效 |
| 配置 | `.env` + `python-dotenv` | `GEMINI_API_KEY` 放这里，不进 git |
| 测试 | pytest + httpx | FastAPI 官方测试栈 |

### 2.2 架构

```
浏览器 (localhost:8000)
   │
   │  HTML + Vue + fetch
   ▼
FastAPI 服务 (uvicorn)
   │
   ├─ routes/profile.py        口味画像 CRUD
   ├─ routes/dishes.py         会做菜库 CRUD
   ├─ routes/ingredients.py    本周食材 CRUD
   ├─ routes/recommend.py      推荐与打卡
   │
   ├─ services/gemini.py       Gemini 客户端（限频、重试、宽松 JSON 解析）
   ├─ services/scoring.py      打分函数
   ├─ services/filters.py      "主食材齐"等规则过滤
   ├─ services/week.py         周边界工具
   │
   └─ db/                      SQLAlchemy 模型 + session
        └─ data.db             SQLite 文件
   │
   ▼
Gemini API (generativelanguage.googleapis.com)
```

启动方式：
```bash
uvicorn app.main:app --reload --port 8000
# 浏览器打开 http://localhost:8000
```

---

## 3. 数据模型

SQLite 共 6 张表。单用户，**所有表无 user_id 字段**。

### 3.1 `profile`（口味画像，单行表）
| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK | 固定为 1 |
| `cuisine_prefs` | TEXT (JSON) | `["川","粤","日式"]` |
| `spicy` | INTEGER | 0–5 |
| `dislikes` | TEXT (JSON) | `["香菜","内脏"]` |
| `updated_at` | TIMESTAMP | |

### 3.2 `dishes`
| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK | |
| `name` | TEXT UNIQUE | 菜名 |
| `category` | TEXT | 主菜 / 素食 / 汤类 / 饮品 / 西餐 |
| `cuisine` | TEXT | 川 / 粤 / 湘 / 淮扬 / 鲁 / 日式 / 意式 / ... |
| `main_ingredients` | TEXT (JSON) | 主食材数组 |
| `spicy` | INTEGER | 0–5 |
| `tags` | TEXT (JSON) | 自由标签 |
| `source` | TEXT | `"user_known"` / `"gemini_suggested"` |
| `cook_count` | INTEGER | 打卡累计（隐式偏好） |
| `needs_review` | BOOLEAN | Gemini 解析失败时为 true，前端高亮 |
| `created_at` | TIMESTAMP | |

### 3.3 `weekly_ingredients`
| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK | |
| `week_start` | DATE UNIQUE | 本周一日期 |
| `items` | TEXT (JSON) | 食材清单 |
| `updated_at` | TIMESTAMP | |

### 3.4 `cooking_log`
| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK | |
| `dish_id` | INTEGER FK → dishes.id | |
| `meal_type` | TEXT | `"breakfast"` / `"lunch"` / `"dinner"` |
| `cooked_at` | TIMESTAMP | |

**索引**：`cooked_at`。

### 3.5 `recommend_cache`（30 秒去重）
> 实现备注：可以放进程内存（dict + 过期时间）即可，无需持久化。
> 列在数据模型里只是为了概念完整；实现时不建表，做成 `services/cache.py` 的进程级 LRU。

### 3.6 `api_quota`
| 字段 | 类型 | 说明 |
|---|---|---|
| `date` | DATE PK | UTC+8 当日 |
| `count` | INTEGER | 已调 Gemini 次数 |

**用途**：单用户自用，配额改为**每天 100 次**（更宽松，主要防呆与防 bug 死循环）。超限静默降级。

---

## 4. 核心流程

### 4.1 录入"会做的菜"  `POST /api/dishes` body: `{name}`

1. 若 `name` 已存在 → 返回 409 + 友好提示
2. 调 `gemini.classify_dish(name)`：
   - Prompt：`给定菜名"{name}"，返回 JSON {category, cuisine, main_ingredients(3–7 个), spicy(0–5), tags}`
   - 严格 JSON；解析失败 → temperature +0.2 重试 1 次；仍失败 → 仅存 `name + needs_review=true`
3. 插入 `dishes`，`source="user_known"`, `cook_count=0`
4. 返回结构化结果给前端展示

### 4.2 更新本周食材  `PUT /api/ingredients` body: `{items: [...]}`

1. `week_start = get_monday(today)`
2. `INSERT ON CONFLICT(week_start) DO UPDATE SET items = ...`
3. 不调 Gemini

前端提供：常见食材快捷标签 + 自定义输入。

### 4.3 更新口味画像  `PUT /api/profile` body: `{cuisine_prefs, spicy, dislikes}`

直接 upsert `profile`（id=1）。

### 4.4 每餐推荐  `POST /api/recommend` body: `{meal_type}` — **核心**

```
1. 读上下文
   profile = profile.get()
   week    = weekly_ingredients.get(this_monday)
   cooked  = cooking_log.find(cooked_at >= this_monday)
   dishes  = dishes.all()

   若 week 为空 → 返回 { error: "INGREDIENTS_EMPTY" }
   不调 Gemini，不消耗配额。

2. 命中 cache(meal_type) 且未过期 (<30s) → 直接返回

3. 「会的菜」分支（规则，无 Gemini）
   candidates = dishes.filter(d =>
        d.source == "user_known"
     && d.id 不在 cooked
     && d.main_ingredients ⊂ week.items                       // 主食材齐
     && d.cuisine 不在 profile.dislikes
     && d.main_ingredients ∩ profile.dislikes == ∅
   )
   score(d) =
        1.0 * (d.cuisine in profile.cuisine_prefs ? 1 : 0)
      + 0.5 * (|d.spicy - profile.spicy| <= 1 ? 1 : 0)
      + 0.3 * log(1 + d.cook_count)
   known = top 2 by score

   说明：本周已做的菜已在 candidates 过滤阶段排除。
   推荐过但用户没做的菜下次仍可被推 —— 与"隐式打卡学习"思路一致：
   没做 = 没采纳信号，不扣分；做了 cook_count 上升、加分。

4. 「新菜」分支（调 Gemini）
   if api_quota.today() >= 100:
       new_dishes = []
       warning = "今日 AI 配额已用尽，明日恢复"
   else:
       prompt = build_new_dish_prompt({
           cuisine_prefs, spicy, dislikes,
           ingredients: week.items,
           cuisine_histogram: 统计 dishes.cuisine 的频次,
           cooked_this_week: 取菜名
       })
       try:
           raw = gemini.generate(prompt, timeout=8s)
           parsed = parse_gemini_json(raw)
           new_dishes = parsed.dishes.filter(d =>
               d.main_ingredients ⊂ week.items
               && d.cuisine 不在 profile.dislikes
           )
           api_quota.increment(today)
           if not new_dishes:
               # 二次重试，prompt 追加约束
               raw2 = gemini.generate(prompt + 约束提示, temp+0.2)
               ...
       except Timeout | NetworkError:
           new_dishes = []
           warning = "新菜推荐暂不可用"

5. cache.set(meal_type, payload, ttl=30s)

6. 返回 { known, new: new_dishes, warning? }
```

返回结构示例：
```json
{
  "known": [
    {"id": 12, "name": "番茄炒蛋", "cuisine": "家常", "spicy": 0,
     "main_ingredients": ["番茄","鸡蛋"], "source": "user_known"}
  ],
  "new": [
    {"name": "蒜蓉粉丝蒸虾", "category": "主菜", "cuisine": "粤",
     "spicy": 1, "main_ingredients": ["虾","粉丝","大蒜"],
     "why_recommended": "你常做炒菜，换个蒸的尝鲜",
     "source": "gemini_suggested"}
  ],
  "warning": null
}
```

### 4.5 Gemini Prompt — 新菜分支

```
你是中西餐家常菜推荐助手。请根据以下用户画像与本周可用食材，
推荐 2 道用户尚未做过的新菜，使他/她拓展烹饪范围。

# 用户画像
- 偏爱菜系：{cuisine_prefs}
- 可接受辣度：{spicy}/5
- 忌口/不吃：{dislikes}

# 本周可用食材（主食材必须从这里出，调料默认有）
{ingredients}

# 用户已会做的菜系分布（推荐时要多样化，不要只推一个菜系）
{cuisine_histogram}

# 本周已做过的菜（不要重复推）
{cooked_this_week}

# 输出要求（严格 JSON，不要任何额外文字）
{
  "dishes": [
    {
      "name": "...",
      "category": "主菜|素食|汤类|饮品|西餐",
      "cuisine": "...",
      "spicy": 0-5,
      "main_ingredients": ["...","..."],
      "why_recommended": "一句话推荐理由"
    },
    ...共 2 道
  ]
}
```

### 4.6 打卡  `POST /api/log` body: `{dish_id?: int, gemini_dish?: {...}, meal_type, add_to_library?: bool}`

打卡有两种来源：
- **打卡会的菜**：传 `dish_id`（已在库）
- **打卡新菜**：传 `gemini_dish`（推荐返回的对象，尚未在库）+ `add_to_library`

逻辑：
```
1. 若是新菜:
     if add_to_library == true:
         在 dishes 表 insert 这道菜，source="user_known", cook_count=1
         dish_id = 新插入的 id
     else:
         在 dishes 表 insert 这道菜，source="gemini_suggested", cook_count=1
         dish_id = 新插入的 id
2. 否则（会的菜）:
     UPDATE dishes SET cook_count = cook_count + 1 WHERE id = dish_id
3. INSERT INTO cooking_log (dish_id, meal_type, cooked_at)
```

**前端交互**：打卡按钮点击后，若是新菜，先弹"是否加入会做菜库？"，用户确认后再带 `add_to_library=true` 调 API。

### 4.7 周边界

- `get_monday(date)` 返回该日所在周的周一 00:00（本地时区 UTC+8）
- `weekly_ingredients.week_start` 按周隔行存储
- `cooking_log` 用 `cooked_at >= get_monday(today)` 查询本周
- 无需定时迁移任务

---

## 5. 错误处理

| 失败点 | 处理 |
|---|---|
| Gemini API 超时/网络 | 8 秒超时；新菜返回空，加 `warning: "新菜推荐暂不可用"`；会的菜照常 |
| Gemini 返回非 JSON | 宽松解析（截取首个 `{` 到末尾 `}`）；失败 → temperature+0.2 重试 1 次；再失败 → 同上 |
| Gemini 返回 `main_ingredients` 含未提供食材 | 该菜丢弃；剩 0 道则一次重试，prompt 追加约束 |
| `weekly_ingredients` 为空 | 返回 `INGREDIENTS_EMPTY`；前端引导去录入；不调 Gemini |
| 会的菜库为空 | 仅返回新菜；不报错 |
| `addDish` 时 Gemini 失败 | 仅存 `name + needs_review=true`，前端黄色高亮 |
| 重复录入同名菜 | DB UNIQUE 约束；返回 409 友好提示 |
| 每日 Gemini 配额 100 次用尽 | 新菜返回空 + warning；会的菜照常 |
| `GEMINI_API_KEY` 未配置 | 启动时检测，主入口打印警告但允许启动；推荐时降级为"只返回会的菜" |

---

## 6. 测试策略

目标：核心逻辑（services/）覆盖率 80%+；routes 用集成测试覆盖。

| 层 | 测试对象 | 关键用例 |
|---|---|---|
| 单元 | `services/scoring.py: score_dish(dish, profile)` | 各因子单独生效；菜系命中加分；辣度匹配加分；cook_count 单调贡献；排序正确 |
| 单元 | `services/filters.py: can_cook_with(dish, week_items, dislikes)` | 空食材、部分匹配、全匹配、忌口排除 |
| 单元 | `services/gemini.py: parse_gemini_json(raw)` | 正常 JSON、带前后缀文字、缺括号、字段缺失 |
| 单元 | `services/week.py: get_monday(date)` | 周一 0:00、周日 23:59、跨年、跨月 |
| 集成 | `POST /api/recommend` | mock gemini client：会的菜规则正确、新菜合并、缓存命中、配额耗尽降级、Gemini 失败降级、食材空时报错 |
| 集成 | `POST /api/dishes` | Gemini 成功解析 / 解析失败标 needs_review / 重复名拒绝 |
| 集成 | `POST /api/log` | cook_count +1；cooking_log 写入；新菜加入会做菜库流程；新菜不加入仅记录流程 |
| 手测 | 浏览器 4 条关键路径 | 1) 设口味 2) 录会的菜 3) 录本周食材 4) 请求推荐并打卡 |

工具：`pytest`、`httpx.AsyncClient`、用一个临时 SQLite 文件做集成测试隔离。Gemini client 通过依赖注入 mock。

---

## 7. 目录结构

```
D:\recipe-recommender\
├── app\
│   ├── main.py                FastAPI app 入口，挂载 routes + 静态文件
│   ├── config.py              .env 读取，启动时校验
│   ├── routes\
│   │   ├── profile.py
│   │   ├── dishes.py
│   │   ├── ingredients.py
│   │   └── recommend.py       含 /api/recommend 和 /api/log
│   ├── services\
│   │   ├── gemini.py          Gemini SDK 封装、限频、重试、解析
│   │   ├── scoring.py
│   │   ├── filters.py
│   │   ├── week.py
│   │   └── cache.py           进程内 30s 缓存
│   ├── db\
│   │   ├── models.py          SQLAlchemy ORM
│   │   ├── session.py
│   │   └── init.py            首次启动建表
│   └── prompts\
│       ├── classify_dish.txt
│       └── new_dish.txt
├── static\                    Vue SPA
│   ├── index.html             单文件，Vue 3 CDN
│   ├── app.js                 Vue 组件 + fetch 调用
│   └── style.css
├── tests\
│   ├── unit\
│   │   ├── test_scoring.py
│   │   ├── test_filters.py
│   │   ├── test_gemini_parser.py
│   │   └── test_week.py
│   ├── integration\
│   │   ├── test_recommend.py
│   │   ├── test_dishes.py
│   │   └── test_log.py
│   └── conftest.py            临时 DB、mock Gemini fixture
├── data.db                    运行后生成（git 忽略）
├── .env                       GEMINI_API_KEY（git 忽略）
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

---

## 8. 开放问题与未来扩展

- **多设备使用**：当前是 localhost，若想在手机上用，可暴露 LAN IP（`uvicorn --host 0.0.0.0`），同 WiFi 即可。
- **数据备份**：`data.db` 是单文件，复制即备份。
- **历史菜谱回顾**：可基于 `cooking_log` 加一个"我的本月战绩"页面
- **菜品图片**：v2 加静态目录支持
- **显式评分**：若隐式打卡率信号不够，再加 1–5 星
- **周计划表视图**：v2 可加
- **正式上线小程序**：若未来想分享给别人，再迁移到云开发付费版 + 中转服务器

---

## 设计澄清记录

| 维度 | 决策 |
|---|---|
| 形态 | 本地 Web 应用（localhost 浏览器访问） |
| 后端 | Python FastAPI |
| 数据库 | SQLite 单文件 |
| 前端 | 单页 HTML + Vue 3 CDN，零构建 |
| 用户系统 | 无（单用户自用） |
| 触发/反馈 | 按餐推荐 + 点击打卡 |
| 菜品录入 | 只输菜名，Gemini 后台补食材/菜系/口味标签 |
| 新菜食材匹配 | 主食材齐即可（调料默认有） |
| 口味维度 | 菜系 + 辣度 + 忌口 |
| 偏好学习 | 隐式打卡率 |
| 算法策略 | 规则过滤"会的菜" + LLM 生成"新菜" |
| 打卡新菜处理 | 弹窗询问是否加入会做菜库 |
| 失败降级 | 静默：会的菜照常 + warning |
| API 限频 | 每日 100 次 Gemini（防呆，非成本控制） |
| 推荐缓存 | 进程内 30 秒去重 |
| 测试覆盖率 | services 模块 80%+ |
| 成本 | 完全免费（依赖本机能访问 Gemini） |

---

## 变更记录

- 2026-05-22 v1：初版（微信小程序 + 云开发架构）
- 2026-05-22 v2：因免费成本约束 + 自用场景，**架构改为本地 Web 应用**（FastAPI + SQLite + Vue CDN）
