# 子项目 F：做法教程 设计文档

> 给菜加「做法」：新菜「做这道并加入菜库」后弹窗 AI 生成做法；会的菜可手填或一键 AI 生成。
> 设计冻结日期：2026-05-25

---

## 1. 目标与范围

让用户知道一道菜怎么做：新菜决定要做时弹出 AI 生成的做法；已会做的菜可自己写做法或让 AI 生成。

### In Scope
- `Dish` 加 `recipe` 文本列（自由文本，默认空）。
- AI 生成做法：`recipe.txt` prompt + `LLMService.generate_recipe` + `factory.generate_recipe`（纯文本，无 JSON 解析；pro→flash 兜底）。
- 端点 `POST /api/dishes/{id}/generate-recipe`：AI 生成 → 存到 dish.recipe → 返回 `{recipe, error}`。尽力而为，失败返回 error，不改 dish、不阻断。
- `recipe` 进 `DishOut` / `DishEdit`（手填做法走现有 `PUT /api/dishes/{id}`）。
- 前端：推荐页「做这道并加入菜库」后弹窗加载做法（解耦：加入照常成功）；会的菜可查看做法 + 编辑表单加做法 textarea + 「AI 生成做法」按钮。
- 迁移脚本 `scripts/migrate_add_recipe.py`（ALTER TABLE 加列，幂等）。

### Out of Scope
- 结构化食材用量表（做法是自由文本，按行分步）。
- 图片/视频教程。
- 做法版本历史。
- 做法的多语言。

---

## 2. 数据模型 + 迁移

### 2.1 Dish 加列
`app/db/models.py` 的 `Dish` 加：
```python
    recipe: Mapped[str] = mapped_column(Text, default="")
```
（`Text` 从 `sqlalchemy` 导入；若已导入则复用。）存自由文本做法，默认 `""`。

### 2.2 迁移脚本 `scripts/migrate_add_recipe.py`（幂等）
`create_all` 不会给已存在的 dishes 表加列；Neon 需手动 ALTER：
```python
"""Add dishes.recipe column to an existing database (idempotent).
Usage (PowerShell, Neon):
    $env:DATABASE_URL = "postgresql+psycopg://..."
    python -m scripts.migrate_add_recipe
"""
from __future__ import annotations

from sqlalchemy import text

from app.db.session import engine


def main() -> int:
    print(f"Ensuring recipe column on: {engine.url.render_as_string(hide_password=True)}")
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE dishes ADD COLUMN IF NOT EXISTS recipe TEXT DEFAULT ''"))
    print("recipe column ensured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

---

## 3. 后端

### 3.1 prompt `app/prompts/recipe.txt`（纯文本输出）
```
你是家常菜菜谱助手。请给出「{name}」的简明做法，让新手能照着做。

主食材：{main_ingredients}（如不准确，按这道菜的常见做法来）
菜系：{cuisine}

要求：
- 先用一行列出所需食材与大致用量；
- 然后分步骤，每步一行，包含关键火候/时间；
- 用中文纯文本，不要 JSON、不要 Markdown 代码块，控制在约 200 字内。
```
`{name}` / `{main_ingredients}` / `{cuisine}` 为真实占位（此文件无 JSON 花括号，无需转义）。

### 3.2 `LLMService.generate_recipe`
返回**纯文本**（不走 `parse_llm_json`，规避解析失败）：
```python
def generate_recipe(self, *, name, cuisine, main_ingredients) -> str:
    prompt = _load_prompt("recipe.txt").format(
        name=name,
        cuisine=cuisine or "家常",
        main_ingredients=", ".join(main_ingredients) or "(自行判断)",
    )
    return (self.provider.generate(prompt, temperature=0.6) or "").strip()
```

### 3.3 `factory.generate_recipe`
pro→flash 兜底，返回 `(str, fell_back)`：
```python
def generate_recipe(db, user, **kwargs) -> tuple[str, bool]:
    svc = build_llm_for_user(db, user)
    try:
        return svc.generate_recipe(**kwargs), False
    except LLMUnavailable as e:
        if _is_quota_error(e) and is_gemini_pro_config(db, user):
            mark_pro_exhausted(db, user)
            return build_llm_for_user(db, user, force_flash=True).generate_recipe(**kwargs), True
        raise
```

### 3.4 端点 `POST /api/dishes/{id}/generate-recipe`（在 `app/routes/dishes.py`）
```python
@router.post("/{dish_id}/generate-recipe")
def generate_recipe(dish_id, db, user) -> dict:
    dish = <select own dish or 404>
    if today_quota(db, user.id) >= settings.daily_gemini_quota:
        return {"recipe": dish.recipe, "error": "今日 AI 配额已用尽，明日恢复"}
    try:
        text, _fell = factory.generate_recipe(
            db, user, name=dish.name, cuisine=dish.cuisine,
            main_ingredients=dish.main_ingredients,
        )
        bump_quota(db, user.id)
        dish.recipe = text
        db.commit()
        return {"recipe": text, "error": None}
    except LLMUnavailable as e:  # recipe is plain text -> no LLMParseError path
        msg = str(e)
        if "timed out" in msg or "timeout" in msg.lower():
            err = "AI 响应超时，请重试"
        elif "decrypt" in msg:
            err = "保存的 AI key 无法读取，请到「设置」重新输入"
        elif "RESOURCE_EXHAUSTED" in msg or "429" in msg:
            err = "今日 AI 额度已用尽（免费层限制），明日恢复"
        elif "no LLM configured" in msg or "no api key" in msg:
            err = "请先在「设置」里配置 AI"
        else:
            err = "做法生成失败，请重试"
        return {"recipe": dish.recipe, "error": err}
```
- 始终 200；失败时 `error` 非空、`recipe` 为现有值（可能空），dish 不变。前端据此显示错误 + 重试。
- 用 `app/services/quota.py` 的 `bump_quota`/`today_quota`（已存在）。

### 3.5 `recipe` 进 `DishOut` / `_to_out` / `DishEdit` / `edit_dish`
- `DishOut` 加 `recipe: str`；`_to_out` 传 `recipe=d.recipe`。
- `DishEdit` 加 `recipe: str = ""`；`edit_dish` 里 `dish.recipe = body.recipe`。
- `add_dish` 新建 Dish 时 `recipe=""`（新列默认即空，可不显式传）。

---

## 4. 前端

### 4.1 推荐页：做这道并加入菜库 → 弹窗做法
- `logNew(d, true)` 现有逻辑不变（POST `/api/log`，即时加入+打卡），其返回含 `dish_id`。
- 成功后打开 modal：`recipeModal = { open, loading, title, text, error, dishId }`，并调 `POST /api/dishes/{dish_id}/generate-recipe`：
  - loading 期间转圈；返回 `recipe` 显示文本；`error` 非空显示错误 + 「重试」按钮（重试再调同端点）。
- modal 有关闭按钮；关闭不影响已加入的菜。
- 「先不加入」按钮（`logNew(d, false)`）不弹做法（没加入菜库，无 dish 持久化做法的载体）。

### 4.2 会的菜：查看 + 编辑 + AI 生成
- 列表项加「做法」展开/查看：有 `recipe` 显示文本（`white-space: pre-wrap`），无则提示「暂无做法，可编辑或 AI 生成」。
- 编辑表单加：
  - `做法` textarea（`v-model="editForm.recipe"`）。
  - 「AI 生成做法」按钮：调 `/api/dishes/{id}/generate-recipe`，成功把返回 `recipe` 填进 textarea（`error` 显示在 `editError`）；用户可再改，保存走现有 `saveEdit`（PUT body 带 `recipe`）。
- `startEdit` 初始化 `editForm.recipe = d.recipe || ""`；`saveEdit` body 加 `recipe: editForm.recipe`。

### 4.3 modal 样式
复用 `.card` + 一个轻量遮罩（`.modal-overlay` 固定定位半透明背景，`.modal` 居中卡片）。新增少量 CSS 到 `style.css`。

---

## 5. 错误处理
| 场景 | 处理 |
|---|---|
| 生成 AI 超时/失败 | 端点返回 `error`、`recipe` 不变；前端显示错误 + 重试 |
| 今日配额用尽 | 端点返回 `error="今日 AI 配额已用尽"`，不调 AI |
| 解密失败/无 key | `error` 提示去设置（复用判断） |
| 生成成功但文本为空 | 存空串；前端显示「未生成有效做法，请重试」（text 为空且无 error 时） |
| 对别人的菜生成 | 404 |
| 「先不加入」 | 不弹 modal |

## 6. 测试
- **单元**：`generate_recipe` service 把 name/cuisine/ingredients 放进 prompt 并返回 trim 文本（stub provider）；`factory.generate_recipe` 429→flash 兜底。
- **集成** `POST /api/dishes/{id}/generate-recipe`：
  - 成功 → 返回 recipe 文本 + `error=None`，且 dish.recipe 被持久化（再 GET 能看到）。
  - AI 抛 `LLMUnavailable("timed out")` → 200，`error` 含「超时」，dish.recipe 不变。
  - 配额用尽 → `error` 含「配额」，未调 AI（fake 计数 0）。
  - 别人的菜 → 404；无 auth → 401。
- **集成** dishes：`DishOut` 含 `recipe`；`PUT` 改 `recipe` 持久化。
- conftest：`FakeLLM` 加 `recipe_queue`/`recipe_calls`/`recipe()`，`fake_llm` fixture monkeypatch `factory.generate_recipe`（返回 `(text, False)`）。
- 预估 +9 测试（当前 150 → ~159）。

## 7. 文件改动清单
```
新增:
  app/prompts/recipe.txt
  scripts/migrate_add_recipe.py
修改:
  app/db/models.py             Dish + recipe 列
  app/services/llm/service.py  + generate_recipe
  app/services/llm/factory.py  + generate_recipe
  app/routes/dishes.py         recipe 进 DishOut/_to_out/DishEdit/edit_dish + generate-recipe 端点
  static/index.html            推荐页 modal + 会的菜做法查看/编辑/AI按钮
  static/app.js                recipeModal 状态 + 生成/重试；editForm.recipe
  static/style.css             modal 遮罩样式
  tests/...                    新增/更新（见 §6）
依赖：无新增
```

## 8. 部署注记
- push 前/后对 Neon 跑 `python -m scripts.migrate_add_recipe`（ALTER 加 recipe 列）。SQLite 测试自动建列，无影响。

## 9. 澄清记录
| 维度 | 决策 |
|---|---|
| 新菜教程来源 | AI 生成做法 |
| 生成 vs 加入 | 解耦：加入即时成功，做法弹窗单独加载，失败可重试不阻断 |
| 会的菜 | 手填 + AI 生成都支持 |
| 做法格式 | 纯自由文本（分行步骤），非结构化 |
| 端点返回 | 始终 200，`{recipe, error}` |
| 加列迁移 | 手动 ALTER（幂等脚本） |

## 10. 变更记录
- 2026-05-25：子项目 F 设计冻结
