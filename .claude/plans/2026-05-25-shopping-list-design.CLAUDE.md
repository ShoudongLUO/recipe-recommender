# 子项目 E：按菜规划采购清单 设计文档

> 在「本周食材」里，用户点「帮我规划」→ 系统按口味推荐 ~10 道菜（会的菜 + AI 新菜）
> → 用户多选 → 生成采购清单（只列还没的食材）→ 写回本周食材。
> 设计冻结日期：2026-05-25

---

## 1. 目标与范围

让用户在还没买菜时，先选「想做哪几道」，再据此得到要买的食材，而不是凭空手填本周食材。

### In Scope
- 新端点 `POST /api/plan/candidates`：返回 ~10 道候选菜（会的菜按口味打分 + AI 新菜，AI 尽力而为）。
- 前端「本周食材」tab 加规划入口：候选多选 → 算采购清单 → 一键写回本周食材。
- 采购清单 = 选中菜的主食材并集 − 当前本周食材（只列还没的）。
- AI 新菜用独立 planning prompt（不受当前食材约束，因为目的就是决定要买什么）。
- 把 `_bump_quota`/`_today_quota` 抽到共享模块，两个路由复用。

### Out of Scope
- 按数量/份数算用量（清单只列食材名，不算克数）。
- 采购清单导出/分享（先只在 app 内显示 + 写回）。
- 餐次维度（不分早午晚，纯规划）。
- 历史「规划记录」。

---

## 2. 数据流（Approach A）

```
本周食材 tab
  └─[帮我规划本周] → POST /api/plan/candidates
        → { candidates: [...~10...], ai_warning: str|null }
  └─ 渲染候选（复选框，会的菜 + AI 新菜区分）
  └─ 用户勾选若干
  └─ 客户端算采购清单 = 并集(选中.main_ingredients) − Set(当前本周食材)
  └─ 显示采购清单
  └─[加入本周食材] → PUT /api/ingredients { items: 当前 ∪ 采购清单 }（复用现有端点，去重）
  └─ 刷新本周食材，收起规划区
```

后端只新增「取候选」一个端点；选择、集合差、写回都复用前端 + 现有 `PUT /api/ingredients`。

---

## 3. 后端

### 3.1 候选组成端点 `app/routes/plan.py`
`POST /api/plan/candidates`（需登录）

请求体：无（或预留 `count: int = 10`，本版固定 10，不暴露）。

逻辑：
1. **会的菜**：取本用户 `source == "user_known"` 的菜，排除 `has_forbidden(cuisine, main_ingredients, profile.dislikes)`，按 `score_dish(d, profile)` 降序，取前 **8**。
   - 不按当前食材过滤（规划阶段就是要决定买什么）。
   - 不排除「本周已做」（规划用）。
2. **AI 新菜**（尽力而为）：若今日配额未用尽，调 `factory.plan_new_dishes(...)` 取 ~4 道；排除 dislikes；按菜名去重（不和会的菜重名）。失败/超时/无 key/配额尽 → 跳过，置 `ai_warning`。
3. 合并：会的菜在前，AI 新菜在后，整体截断到 **10**。

响应：
```json
{
  "candidates": [
    {"id": 12, "name": "番茄炒蛋", "category": "主菜", "cuisine": "家常",
     "spicy": 0, "main_ingredients": ["番茄","鸡蛋"], "source": "known",
     "why_recommended": null},
    {"id": null, "name": "罗宋汤", "category": "汤类", "cuisine": "俄式",
     "spicy": 0, "main_ingredients": ["牛肉","土豆","卷心菜","番茄"],
     "source": "ai", "why_recommended": "换换口味的暖汤"}
  ],
  "ai_warning": null
}
```
- `source`：`"known"`（会的菜，有 `id`）或 `"ai"`（AI 新菜，`id` 为 null）。
- `ai_warning`：AI 部分失败时的中文提示（如「AI 新菜暂时没取到，可只从会做的菜里挑」），否则 null。

### 3.2 候选组成纯函数（可测）
在 `app/routes/plan.py` 或 `app/services/planning.py` 放一个纯函数便于单测：
```python
def compose_candidates(known_dicts: list[dict], ai_dicts: list[dict], limit: int = 10) -> list[dict]:
    """known 在前（已按分排好），ai 去掉与 known 重名的，合并截断到 limit。"""
    known_names = {d["name"] for d in known_dicts}
    ai_unique = [d for d in ai_dicts if d["name"] not in known_names]
    return (known_dicts + ai_unique)[:limit]
```
排序/打分/dislikes 过滤在端点里用现有 `score_dish` / `has_forbidden`；compose 只管合并去重截断。

### 3.3 AI 规划 prompt `app/prompts/plan_dishes.txt`
独立于 `new_dish.txt`：**不**约束本周食材（规划就是要决定买什么），按口味推荐若干「不在已会列表」的菜。
```
你是中西餐家常菜推荐助手。请根据用户口味，推荐 {count} 道适合本周做的家常菜，
帮用户规划采购。不要推荐与「已会做」重复的菜。

# 用户口味
- 偏爱菜系：{cuisine_prefs}
- 可接受辣度：{spicy}/5
- 忌口/不吃：{dislikes}

# 已会做（不要重复推荐）
{known_names}

# 输出要求（严格 JSON，不要任何额外文字）
{{
  "dishes": [
    {{"name":"...","category":"主菜|素食|汤类|饮品|西餐","cuisine":"...",
      "spicy":0,"main_ingredients":["...","..."],"why_recommended":"一句话理由"}}
  ]
}}
共返回 {count} 道。
```

### 3.4 service `LLMService.generate_plan_dishes`
```python
def generate_plan_dishes(self, *, cuisine_prefs, spicy, dislikes, known_names, count=4) -> list[dict]:
    prompt = _load_prompt("plan_dishes.txt").format(
        cuisine_prefs=", ".join(cuisine_prefs) or "(无)",
        spicy=spicy, dislikes=", ".join(dislikes) or "(无)",
        known_names=", ".join(known_names) or "(无)", count=count,
    )
    data = parse_llm_json(self.provider.generate(prompt, temperature=0.8))
    return list(data.get("dishes", []))
```

### 3.5 factory `plan_new_dishes`
与 `recommend_new_dishes` 同样的 pro→flash 429 兜底；返回 `(list[dict], fell_back: bool)`：
```python
def plan_new_dishes(db, user, **kwargs) -> tuple[list[dict], bool]:
    svc = build_llm_for_user(db, user)
    try:
        return svc.generate_plan_dishes(**kwargs), False
    except LLMUnavailable as e:
        if _is_quota_error(e) and is_gemini_pro_config(db, user):
            mark_pro_exhausted(db, user)
            return build_llm_for_user(db, user, force_flash=True).generate_plan_dishes(**kwargs), True
        raise
```

### 3.6 配额助手抽共享 `app/services/quota.py`
把 `recommend.py` 里的 `_bump_quota` / `_today_quota` 移到这里（`bump_quota` / `today_quota`），`recommend.py` 与 `plan.py` 都 import。纯搬运，行为不变。

### 3.7 main 注册
`app/main.py` 注册 `plan` 路由。

---

## 4. 前端（`本周食材` tab）

- 顶部加按钮 **「还没买菜？帮我规划」**（莫兰迪灰按钮 `.btn-primary`）。
- 点击 → `loadPlanCandidates()`：POST `/api/plan/candidates`，`planning.loading` 期间显示「规划中…」。
- 候选区：每项一行复选（复用 `.chip` 选中态或简单 checkbox 行），显示菜名 + 菜系 + 主食材；AI 新菜标个「新」小标签；`ai_warning` 用 `.warning` 显示。
- 选中后实时算 **采购清单**：`union(选中.main_ingredients) − Set(splitItems(ingredientsText))`，显示为一串 chips/文本。
- **「加入本周食材」** 按钮：`PUT /api/ingredients { items: 当前 ∪ 采购清单 }`，成功后刷新 `ingredientsText`、收起规划区、`saved` 提示。
- 状态：`planning = { open, loading, candidates:[], selected:Set, aiWarning }`。集合差/并集用现有 `splitItems` + Set。

---

## 5. 错误处理
| 场景 | 处理 |
|---|---|
| AI 超时/失败/无 key | 只返回会的菜 + `ai_warning`，功能不崩 |
| 今日配额已用尽 | 跳过 AI，`ai_warning="今日 AI 配额已用尽，仅从会做的菜推荐"` |
| 没有会的菜且 AI 也失败 | `candidates=[]`，前端提示「先去『会的菜』添加，或稍后重试」 |
| 选中 0 道点生成 | 前端拦截，提示「先勾选几道菜」 |
| 采购清单为空（全已有） | 提示「这些菜的食材你都已有，无需采购」 |
| dislikes | 会的菜与 AI 新菜都过滤 |

---

## 6. 测试
- **单元**：`compose_candidates`（known 在前、ai 去重、截断 10）；`generate_plan_dishes` 把 count/known_names 放进 prompt（stub provider 断言）。
- **集成** `/api/plan/candidates`：
  - 会的菜按分排序 + dislikes 排除（fake AI 返回空）。
  - fake AI 返回新菜 → 合并、去重、`source` 正确。
  - AI 抛 `LLMUnavailable` → 只返回会的菜 + `ai_warning` 非空（不 500）。
  - 配额已用尽 → 跳过 AI + `ai_warning`。
  - 多用户隔离；无 auth 401。
- **回归**：`recommend.py` 改用 `quota.py` 后既有 recommend 测试保持绿。
- 预估 +10 测试（当前 140 → ~150）。

---

## 7. 文件改动清单
```
新增:
  app/routes/plan.py              候选端点 + compose_candidates
  app/prompts/plan_dishes.txt     规划用 AI prompt（不约束本周食材）
  app/services/quota.py           bump_quota / today_quota（从 recommend 抽出）
修改:
  app/services/llm/service.py     + generate_plan_dishes
  app/services/llm/factory.py     + plan_new_dishes
  app/routes/recommend.py         改用 app/services/quota
  app/main.py                     注册 plan 路由
  static/index.html               本周食材 tab 规划入口 + 候选/清单 UI
  static/app.js                   planning 状态 + 取候选 + 算清单 + 写回
  tests/...                       新增/更新（见 §6）
依赖：无新增
```

---

## 8. 澄清记录
| 维度 | 决策 |
|---|---|
| 推荐对象 | 菜（选菜→清单为其食材） |
| 菜来源 | 会的菜（打分）+ AI 新菜 |
| 清单去向 | 写入本周食材（追加去重） |
| 清单范围 | 只列还没的（选中食材 − 当前本周食材） |
| 架构 | Approach A：1 个取候选端点，选择/集合差/写回在前端复用 PUT ingredients |
| AI 失败 | 尽力而为，降级为只给会的菜 + 提示 |
| AI 约束 | 规划 prompt 不受本周食材约束 |

---

## 9. 变更记录
- 2026-05-25：子项目 E 设计冻结
