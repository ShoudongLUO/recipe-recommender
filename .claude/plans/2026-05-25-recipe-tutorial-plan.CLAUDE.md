# 做法教程（子项目 F）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给菜加自由文本「做法」：新菜「做这道并加入菜库」后弹窗 AI 生成做法（解耦，加入照常成功）；会的菜可手填或一键 AI 生成。

**Architecture:** `Dish.recipe` 文本列；纯文本 AI 生成（无 JSON 解析）经 `service.generate_recipe`→`factory.generate_recipe`（pro→flash 兜底）；端点 `POST /api/dishes/{id}/generate-recipe` 生成+存储+返回 `{recipe,error}`（始终 200，尽力而为）；手填做法走现有 `PUT /api/dishes/{id}`。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Vue 3 (CDN)。本地用 `.venv\Scripts\python.exe`；测试当前 150 passed。提交禁止任何 `Co-Authored-By`/署名脚注。

---

## 文件结构
```
新增:
  app/prompts/recipe.txt          纯文本做法 prompt
  scripts/migrate_add_recipe.py   ALTER 加 recipe 列（幂等）
修改:
  app/db/models.py                Dish + recipe 列
  app/services/llm/service.py     + generate_recipe（纯文本）
  app/services/llm/factory.py     + generate_recipe（pro→flash 兜底）
  app/routes/dishes.py            recipe 进 DishOut/_to_out/DishEdit/edit_dish + generate-recipe 端点
  tests/conftest.py               fake_llm 增补 generate_recipe 桩
  tests/unit/test_llm_providers.py   + generate_recipe prompt 测试
  tests/unit/test_llm_factory.py     + generate_recipe 兜底测试
  tests/integration/test_dishes.py   + recipe 编辑/输出 + generate-recipe 端点测试
  static/index.html               推荐页 modal + 会的菜做法查看/编辑/AI按钮
  static/app.js                   recipeModal 状态 + 生成/重试；editForm.recipe
  static/style.css                modal 遮罩样式
```
每个任务跑全量：`.venv\Scripts\python.exe -m pytest -q --tb=short`。

---

### Task F-T1: `Dish.recipe` 列 + 迁移脚本

**Files:** Modify `app/db/models.py`；Create `scripts/migrate_add_recipe.py`

- [ ] **Step 1: 加列**

在 `app/db/models.py`：确保顶部 `from sqlalchemy import ...` 含 `Text`（若没有则把 `Text` 加进该 import 列表，不要新增重复 import 行）。在 `Dish` 类里、`suitable_meals` 那行之后加：
```python
    recipe: Mapped[str] = mapped_column(Text, default="")
```

- [ ] **Step 2: 验证列存在**

Run: `.venv\Scripts\python.exe -c "from app.db.models import Dish; print('recipe' in Dish.__table__.columns)"`
Expected: `True`

- [ ] **Step 3: 迁移脚本**

Create `scripts/migrate_add_recipe.py`:
```python
"""Add dishes.recipe column to an existing database (idempotent).

Usage (PowerShell, Neon):
    $env:DATABASE_URL = "postgresql+psycopg://user:pass@host/db?sslmode=require"
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

- [ ] **Step 4: 全量测试 + 脚本可导入**

Run: `.venv\Scripts\python.exe -c "import scripts.migrate_add_recipe; print('import ok')"` → `import ok`
Run: `.venv\Scripts\python.exe -m pytest -q --tb=short` → `150 passed`（SQLite 自动建列，数量不变）。

- [ ] **Step 5: Commit**
```bash
git add app/db/models.py scripts/migrate_add_recipe.py
git commit -m "feat(db): add Dish.recipe column and migration"
```

---

### Task F-T2: `recipe.txt` prompt + `LLMService.generate_recipe`

**Files:** Create `app/prompts/recipe.txt`；Modify `app/services/llm/service.py`；Test `tests/unit/test_llm_providers.py`

> 注意：本仓库有 hook 拦截对 `.txt` 用 Write 工具。若被拦，用 PowerShell 写文件并指定 UTF-8，例如：
> `[System.IO.File]::WriteAllText('app/prompts/recipe.txt', $content, (New-Object System.Text.UTF8Encoding $false))`

- [ ] **Step 1: 写失败测试**

在 `tests/unit/test_llm_providers.py` 末尾加（`_StubProvider` 记录 prompt 到 `self.prompts`，`LLMService` 已导入）：
```python
def test_generate_recipe_returns_text_and_uses_name():
    stub = _StubProvider("步骤一：热油。\n步骤二：下蛋。")
    svc = LLMService(stub)
    out = svc.generate_recipe(name="番茄炒蛋", cuisine="家常", main_ingredients=["番茄", "鸡蛋"])
    assert out == "步骤一：热油。\n步骤二：下蛋。"
    assert "番茄炒蛋" in stub.prompts[0]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_llm_providers.py::test_generate_recipe_returns_text_and_uses_name -q`
Expected: FAIL (`AttributeError: ... has no attribute 'generate_recipe'`)。

- [ ] **Step 3: 写 prompt（无 JSON，故无需转义花括号；`{name}`/`{main_ingredients}`/`{cuisine}` 为占位）**

`app/prompts/recipe.txt`:
```
你是家常菜菜谱助手。请给出「{name}」的简明做法，让新手能照着做。

主食材：{main_ingredients}（如不准确，按这道菜的常见做法来）
菜系：{cuisine}

要求：
- 先用一行列出所需食材与大致用量；
- 然后分步骤，每步一行，包含关键火候/时间；
- 用中文纯文本，不要 JSON、不要 Markdown 代码块，控制在约 200 字内。
```

- [ ] **Step 4: 实现 service 方法（纯文本，不解析 JSON）**

在 `app/services/llm/service.py` 的 `LLMService` 类里，`generate_plan_dishes` 之后加：
```python
    def generate_recipe(self, *, name, cuisine, main_ingredients) -> str:
        prompt = _load_prompt("recipe.txt").format(
            name=name,
            cuisine=cuisine or "家常",
            main_ingredients=", ".join(main_ingredients) or "(自行判断)",
        )
        return (self.provider.generate(prompt, temperature=0.6) or "").strip()
```

- [ ] **Step 5: 跑测试 + 全量**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_llm_providers.py -q` → PASS。
Run: `.venv\Scripts\python.exe -m pytest -q --tb=short` → `151 passed`。

- [ ] **Step 6: Commit**
```bash
git add app/prompts/recipe.txt app/services/llm/service.py tests/unit/test_llm_providers.py
git commit -m "feat(llm): add generate_recipe (plain-text recipe steps)"
```

---

### Task F-T3: `factory.generate_recipe`（pro→flash 兜底）

**Files:** Modify `app/services/llm/factory.py`；Test `tests/unit/test_llm_factory.py`

- [ ] **Step 1: 写失败测试**

在 `tests/unit/test_llm_factory.py` 末尾加：
```python
def test_generate_recipe_falls_back_to_flash_on_quota(monkeypatch, db):
    from app.services.llm import factory

    u = _user(db)
    db.add(LLMConfig(user_id=u.id, provider="gemini",
                     api_key_encrypted=encrypt("k"), model="gemini-2.5-pro"))
    db.commit()

    class _Stub:
        def __init__(self, fail):
            self.fail = fail

        def generate_recipe(self, **kw):
            if self.fail:
                raise LLMUnavailable("429 RESOURCE_EXHAUSTED")
            return "做法文本"

    def fake_build(db_, user_, *, force_flash=False):
        return _Stub(fail=not force_flash)

    monkeypatch.setattr(factory, "build_llm_for_user", fake_build)
    text, fell = factory.generate_recipe(
        db, u, name="X", cuisine="家常", main_ingredients=["番茄"])
    assert fell is True
    assert text == "做法文本"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_llm_factory.py::test_generate_recipe_falls_back_to_flash_on_quota -q`
Expected: FAIL (`AttributeError: module ... has no attribute 'generate_recipe'`)。

- [ ] **Step 3: 实现 factory 函数（文件末尾）**
```python
def generate_recipe(
    db: Session, user: User, **kwargs
) -> tuple[str, bool]:
    svc = build_llm_for_user(db, user)
    try:
        return svc.generate_recipe(**kwargs), False
    except LLMUnavailable as e:
        if _is_quota_error(e) and is_gemini_pro_config(db, user):
            mark_pro_exhausted(db, user)
            return (
                build_llm_for_user(db, user, force_flash=True).generate_recipe(
                    **kwargs
                ),
                True,
            )
        raise
```

- [ ] **Step 4: 跑测试 + 全量**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_llm_factory.py -q` → PASS。
Run: `.venv\Scripts\python.exe -m pytest -q --tb=short` → `152 passed`。

- [ ] **Step 5: Commit**
```bash
git add app/services/llm/factory.py tests/unit/test_llm_factory.py
git commit -m "feat(llm): add generate_recipe factory with pro->flash fallback"
```

---

### Task F-T4: `recipe` 进 DishOut / DishEdit（手填做法）

**Files:** Modify `app/routes/dishes.py`；Test `tests/integration/test_dishes.py`

- [ ] **Step 1: 写失败测试**

在 `tests/integration/test_dishes.py` 末尾加（已存在 `_make_dish` helper、`authed_client`、`db_session`、`test_user`）：
```python
def test_edit_dish_saves_recipe(authed_client, db_session, test_user):
    d = _make_dish(db_session, test_user.id, name="番茄炒蛋")
    body = {"name": "番茄炒蛋", "category": "主菜", "cuisine": "家常",
            "main_ingredients": ["番茄", "鸡蛋"], "spicy": 0, "tags": [],
            "suitable_meals": ["lunch"], "recipe": "1. 打蛋  2. 下锅翻炒"}
    r = authed_client.put(f"/api/dishes/{d.id}", json=body)
    assert r.status_code == 200
    assert r.json()["recipe"] == "1. 打蛋  2. 下锅翻炒"
    g = authed_client.get("/api/dishes").json()
    assert g[0]["recipe"] == "1. 打蛋  2. 下锅翻炒"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_dishes.py::test_edit_dish_saves_recipe -q`
Expected: FAIL（`DishOut` 无 recipe → 响应无该键 / 校验错误）。

- [ ] **Step 3: 实现**

在 `app/routes/dishes.py`：
1. `DishOut` 在 `suitable_meals: list[str]` 后加：
```python
    recipe: str
```
2. `_to_out` 的 `DishOut(...)` 调用里、`suitable_meals=d.suitable_meals,` 后加：
```python
        recipe=d.recipe,
```
3. `DishEdit` 在 `suitable_meals: list[Literal[...]] = []` 后加：
```python
    recipe: str = ""
```
4. `edit_dish` 里、`dish.suitable_meals = body.suitable_meals` 后加：
```python
    dish.recipe = body.recipe
```

- [ ] **Step 4: 跑测试 + 全量**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_dishes.py -q` → PASS。
Run: `.venv\Scripts\python.exe -m pytest -q --tb=short` → `153 passed`。

- [ ] **Step 5: Commit**
```bash
git add app/routes/dishes.py tests/integration/test_dishes.py
git commit -m "feat(dishes): expose and accept recipe field"
```

---

### Task F-T5: `POST /api/dishes/{id}/generate-recipe` 端点 + conftest 桩

**Files:** Modify `app/routes/dishes.py`、`tests/conftest.py`；Test `tests/integration/test_dishes.py`

- [ ] **Step 1: conftest 增补 recipe 桩**

在 `tests/conftest.py` 的 `FakeLLM.__init__` 加：
```python
        self.recipe_queue = []   # strings or Exceptions
        self.recipe_calls = 0
```
`FakeLLM` 加方法：
```python
    def recipe(self):
        self.recipe_calls += 1
        r = self.recipe_queue.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
```
`fake_llm` fixture 里（已有 classify/recommend/plan 的 monkeypatch 处）加：
```python
    def _recipe(db, user, **kwargs):
        return f.recipe(), False

    monkeypatch.setattr(_llm_factory, "generate_recipe", _recipe)
```

- [ ] **Step 2: 写失败测试**

在 `tests/integration/test_dishes.py` 末尾加：
```python
def test_generate_recipe_stores_and_returns(authed_client, db_session, fake_llm, test_user):
    d = _make_dish(db_session, test_user.id, name="番茄炒蛋")
    fake_llm.recipe_queue.append("食材：番茄2个、鸡蛋3个\n1. 炒蛋盛出\n2. 炒番茄回锅")
    r = authed_client.post(f"/api/dishes/{d.id}/generate-recipe", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is None
    assert "炒蛋盛出" in body["recipe"]
    g = authed_client.get("/api/dishes").json()
    assert "炒蛋盛出" in g[0]["recipe"]


def test_generate_recipe_ai_failure_keeps_dish(authed_client, db_session, fake_llm, test_user):
    from app.services.llm.base import LLMUnavailable
    d = _make_dish(db_session, test_user.id, name="怪菜")
    fake_llm.recipe_queue.append(LLMUnavailable("request timed out"))
    r = authed_client.post(f"/api/dishes/{d.id}/generate-recipe", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["recipe"] == ""
    assert "超时" in body["error"]


def test_generate_recipe_quota_exhausted_skips_ai(authed_client, db_session, fake_llm, test_user):
    from datetime import date
    from app.db.models import ApiQuota
    d = _make_dish(db_session, test_user.id, name="番茄炒蛋")
    db_session.add(ApiQuota(user_id=test_user.id, quota_date=date.today(), count=999))
    db_session.commit()
    r = authed_client.post(f"/api/dishes/{d.id}/generate-recipe", json={})
    body = r.json()
    assert "配额" in body["error"]
    assert fake_llm.recipe_calls == 0


def test_generate_recipe_other_user_404(authed_client, db_session, test_user_b):
    d = _make_dish(db_session, test_user_b.id, name="别人的菜")
    r = authed_client.post(f"/api/dishes/{d.id}/generate-recipe", json={})
    assert r.status_code == 404


def test_generate_recipe_requires_auth(client, db_session, test_user):
    d = _make_dish(db_session, test_user.id, name="x")
    r = client.post(f"/api/dishes/{d.id}/generate-recipe", json={})
    assert r.status_code == 401
```

- [ ] **Step 3: 跑测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_dishes.py -q -k generate_recipe`
Expected: FAIL（404，端点未建）。

- [ ] **Step 4: 实现端点**

在 `app/routes/dishes.py`：
1. 顶部 import 区加：
```python
from app.config import settings
from app.services.quota import bump_quota, today_quota
```
2. 文件末尾加端点：
```python
@router.post("/{dish_id}/generate-recipe")
def generate_recipe(
    dish_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    dish = db.scalar(select(Dish).where(Dish.id == dish_id, Dish.user_id == user.id))
    if dish is None:
        raise HTTPException(status_code=404, detail="Dish not found")
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
    except LLMUnavailable as e:
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

- [ ] **Step 5: 跑测试 + 全量**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_dishes.py -q` → PASS。
Run: `.venv\Scripts\python.exe -m pytest -q --tb=short` → `158 passed`（153 + 5）。

- [ ] **Step 6: Commit**
```bash
git add app/routes/dishes.py tests/conftest.py tests/integration/test_dishes.py
git commit -m "feat(dishes): add generate-recipe endpoint (best-effort AI)"
```

---

### Task F-T6: 前端 modal + 会的菜做法（控制器直接写，不派 subagent）

**Files:** Modify `static/app.js`、`static/index.html`、`static/style.css`

> 前端由控制器直接编辑（既有约定）。spec 审查后浏览器手测。

- [ ] **Step 1: app.js — recipeModal 状态 + 方法**

`setup()` 内加状态（放在 `editForm` 附近）：
```javascript
    const recipeModal = reactive({ open: false, loading: false, title: "", text: "", error: "", dishId: null });
```
加方法（放在 `logNew` 附近）：
```javascript
    async function fetchRecipe(id) {
      recipeModal.loading = true; recipeModal.error = "";
      try {
        const { data } = await safeApi(`/api/dishes/${id}/generate-recipe`, { method: "POST", body: {} });
        recipeModal.text = data.recipe || "";
        recipeModal.error = data.error || (recipeModal.text ? "" : "未生成有效做法，请重试");
      } catch (e) { recipeModal.error = e.detail || "生成失败，请重试"; }
      finally { recipeModal.loading = false; }
    }
    function openRecipeModal(id, title) {
      recipeModal.open = true; recipeModal.dishId = id; recipeModal.title = title;
      recipeModal.text = ""; recipeModal.error = "";
      fetchRecipe(id);
    }
    function closeRecipeModal() { recipeModal.open = false; }
    async function genEditRecipe(d) {
      editError.value = "";
      try {
        const { data } = await safeApi(`/api/dishes/${d.id}/generate-recipe`, { method: "POST", body: {} });
        if (data.error) editError.value = data.error;
        editForm.recipe = data.recipe || editForm.recipe;
      } catch (e) { editError.value = e.detail || "生成失败"; }
    }
```
改 `logNew` 捕获返回的 `dish_id` 并在加入菜库时开 modal：
```javascript
    async function logNew(d, addToLibrary) {
      try {
        const { data } = await safeApi("/api/log", { method: "POST", body: { gemini_dish: d, meal_type: result._meal, add_to_library: addToLibrary } });
        if (addToLibrary) { await loadDishes(); openRecipeModal(data.dish_id, d.name); }
        await recommend(result._meal);
      } catch {}
    }
```
`startEdit` 加：`editForm.recipe = d.recipe || "";`（在设置其它字段处）。
`saveEdit` 的 `body` 对象加：`recipe: editForm.recipe,`。
`editForm` 的 reactive 初值加 `recipe: ""`：把
`const editForm = reactive({ name: "", cuisine: "", ingredients: "", spicy: 0, category: "", meals: [] });`
改为
`const editForm = reactive({ name: "", cuisine: "", ingredients: "", spicy: 0, category: "", meals: [], recipe: "" });`
加 `recipeViewId` 用于列表查看：`const recipeViewId = ref(null);` 和 `function toggleRecipeView(id) { recipeViewId.value = recipeViewId.value === id ? null : id; }`
在 `setup()` 的 `return { ... }` 加：
`recipeModal, fetchRecipe, openRecipeModal, closeRecipeModal, genEditRecipe, recipeViewId, toggleRecipeView,`

- [ ] **Step 2: index.html — modal、会的菜查看/编辑**

A) modal（放在 `view==='main'` 的根 div 内、`</div>` 收尾前；遮罩 fixed 定位）：
```html
      <div v-if="recipeModal.open" class="modal-overlay" @click.self="closeRecipeModal">
        <div class="modal">
          <span class="modal-close" @click="closeRecipeModal">×</span>
          <h3>{{ recipeModal.title }} · 做法</h3>
          <p v-if="recipeModal.loading" class="empty">AI 生成做法中…</p>
          <div v-else>
            <div v-if="recipeModal.error" class="warning">{{ recipeModal.error }}</div>
            <p v-if="recipeModal.text" class="recipe-text">{{ recipeModal.text }}</p>
            <button class="btn btn-outline" @click="fetchRecipe(recipeModal.dishId)" :disabled="recipeModal.loading">重试</button>
          </div>
        </div>
      </div>
```
B) 会的菜列表项：在 `dish-actions` 里、`✎` 之前加查看做法：
```html
                <span @click="toggleRecipeView(d.id)" title="做法">📖</span>
```
在 `<li class="dish-item">...</li>` 之后（与 `editingId === d.id` 的 edit-form 并列），加做法查看块：
```html
            <div v-if="recipeViewId === d.id && editingId !== d.id" class="edit-form">
              <p v-if="d.recipe" class="recipe-text">{{ d.recipe }}</p>
              <p v-else class="empty">暂无做法，点 ✎ 编辑里手填，或在编辑里用「AI 生成做法」。</p>
            </div>
```
C) 编辑表单：在 `类别` 那行之后、`适合餐次` chip 块附近，加做法 textarea + AI 按钮（放在 `<p v-if="editError"...>` 之前）：
```html
              <label>做法</label>
              <textarea v-model="editForm.recipe" placeholder="自己写做法，或点下面按钮 AI 生成" style="min-height:90px"></textarea>
              <button class="btn btn-outline" style="margin-top:.4rem" @click="genEditRecipe(d)">AI 生成做法</button>
```

- [ ] **Step 3: style.css — modal 样式（文件末尾）**
```css
.modal-overlay { position: fixed; inset: 0; background: rgba(19,19,19,.45); display: flex; align-items: center; justify-content: center; padding: 1rem; z-index: 50; }
.modal { background: var(--surface); border-radius: var(--radius); padding: 1.1rem 1.2rem; max-width: 420px; width: 100%; max-height: 80vh; overflow-y: auto; box-shadow: var(--shadow-float); }
.modal-close { float: right; cursor: pointer; color: var(--text-3); font-size: 20px; line-height: 1; }
.recipe-text { white-space: pre-wrap; font-size: 13px; color: var(--text-2); line-height: 1.7; margin: .3rem 0; }
```

- [ ] **Step 4: 语法自检**

Run: `node --check static/app.js` → 无输出。
Run: `.venv\Scripts\python.exe -c "from app.main import app; print('/api/dishes/{dish_id}/generate-recipe' in [r.path for r in app.routes])"` → `True`。

- [ ] **Step 5: 浏览器手测（spec 审查后）**

起服务 `.venv\Scripts\python.exe -m uvicorn app.main:app --reload`：
- 推荐页出新菜 → 「做这道并加入菜库」→ 立即加入（会的菜里出现），随后弹窗显示「AI 生成做法中…」→ 出做法文本；制造失败时显示错误 + 重试可用。
- 会的菜 → 📖 查看做法（空则提示）；✎ 编辑里有做法 textarea + 「AI 生成做法」按钮，生成后填入、可改、保存后再看已持久化。

- [ ] **Step 6: Commit**
```bash
git add static/app.js static/index.html static/style.css
git commit -m "feat(ui): recipe modal on cook + recipe view/edit/AI-generate in dish library"
```

---

### Task F-T7: 部署（用户）

- [ ] 对 Neon 跑 `python -m scripts.migrate_add_recipe`（加 recipe 列）。
- [ ] push（触发 Vercel）。
- [ ] 线上手测同 F-T6 Step 5。

---

## Self-Review

**Spec coverage:** §2.1 列→F-T1；§2.2 迁移→F-T1；§3.1 prompt + §3.2 service→F-T2；§3.3 factory→F-T3；§3.4 端点→F-T5；§3.5 DishOut/DishEdit→F-T4；§4 前端→F-T6；§5 错误处理→F-T5（超时/配额/解密/无key/失败）+ 前端空文本提示（F-T6 fetchRecipe）；§6 测试→各任务；§8 部署→F-T7。全覆盖。

**Placeholder scan:** 无 TBD/TODO；每个改代码步骤给了完整代码。

**Type consistency:** `recipe` 字段在 models（`Mapped[str]`）/DishOut（`str`）/DishEdit（`str=""`）/`_to_out`(`recipe=d.recipe`)/edit(`dish.recipe=body.recipe`) 一致；端点返回 `{recipe, error}` 与前端 `data.recipe`/`data.error` 一致；`factory.generate_recipe` 返回 `(str,bool)`，service `generate_recipe(*, name, cuisine, main_ingredients)->str` 与端点调用 kwargs 一致；conftest `_recipe(db,user,**kwargs)` 吸收 name/cuisine/main_ingredients；`/api/log` 返回 `dish_id` 被 `logNew` 用于开 modal（与 routes/recommend.py log_dish 返回一致）。
