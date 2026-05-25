# 采购清单规划（子项目 E）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在「本周食材」里按口味推荐 ~10 道菜（会的菜 + AI 新菜），用户多选后生成「只列还没的」采购清单并写回本周食材。

**Architecture:** 新增 `POST /api/plan/candidates` 返回候选菜；选择/集合差/写回在前端完成并复用现有 `PUT /api/ingredients`。AI 新菜用独立 planning prompt（不约束本周食材），尽力而为，失败降级为只给会的菜。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Vue 3 (CDN) + pytest。本地用 `.venv\Scripts\python.exe`；测试当前 140 passed。

---

## 文件结构

```
新增:
  app/services/quota.py        bump_quota / today_quota（从 recommend.py 抽出，两路由共用）
  app/prompts/plan_dishes.txt  规划用 AI prompt（按口味，不约束本周食材）
  app/routes/plan.py           /api/plan/candidates + compose_candidates 纯函数
  tests/integration/test_plan.py
修改:
  app/services/llm/service.py  + generate_plan_dishes
  app/services/llm/factory.py  + plan_new_dishes（pro→flash 兜底）
  app/routes/recommend.py      改用 app/services/quota
  app/main.py                  注册 plan 路由
  tests/conftest.py            fake_llm 增补 plan_new_dishes 桩
  tests/unit/test_llm_providers.py  + generate_plan_dishes prompt 测试
  tests/unit/test_llm_factory.py    + plan_new_dishes 兜底测试
  static/index.html            本周食材 tab 规划入口 + 候选/清单 UI
  static/app.js                planning 状态 + 取候选 + 算清单 + 写回
```

每个任务跑全量：`.venv\Scripts\python.exe -m pytest -q --tb=short`。提交禁止任何 `Co-Authored-By` / 署名脚注。

---

### Task E-T1: 抽出配额助手到 `app/services/quota.py`

**Files:**
- Create: `app/services/quota.py`
- Modify: `app/routes/recommend.py`（删除本地 `_bump_quota`/`_today_quota`，改为 import）

纯搬运重构，行为不变，既有 recommend 测试保持绿。

- [ ] **Step 1: 创建共享模块**

`app/services/quota.py`：
```python
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.db.models import ApiQuota


def bump_quota(db: Session, user_id) -> int:
    today = date.today()
    row = db.get(ApiQuota, (user_id, today))
    if row is None:
        row = ApiQuota(user_id=user_id, quota_date=today, count=1)
        db.add(row)
    else:
        row.count += 1
    db.commit()
    return row.count


def today_quota(db: Session, user_id) -> int:
    row = db.get(ApiQuota, (user_id, date.today()))
    return row.count if row else 0
```

- [ ] **Step 2: recommend.py 改用共享模块**

在 `app/routes/recommend.py` 顶部 import 区加：
```python
from app.services.quota import bump_quota, today_quota
```
删除文件中的 `def _bump_quota(...)` 和 `def _today_quota(...)` 两个函数定义。
把调用处 `_bump_quota(db, user.id)` → `bump_quota(db, user.id)`，`_today_quota(db, user.id)` → `today_quota(db, user.id)`（共两处：配额门 `if _today_quota(...) >= ...` 和成功后的 `_bump_quota(...)`）。

- [ ] **Step 3: 全量测试保持绿**

Run: `.venv\Scripts\python.exe -m pytest -q --tb=short`
Expected: `140 passed`（仅重构，数量不变）。

- [ ] **Step 4: Commit**

```bash
git add app/services/quota.py app/routes/recommend.py
git commit -m "refactor(quota): extract bump/today quota helpers to shared module"
```

---

### Task E-T2: planning prompt + `LLMService.generate_plan_dishes`

**Files:**
- Create: `app/prompts/plan_dishes.txt`
- Modify: `app/services/llm/service.py`
- Test: `tests/unit/test_llm_providers.py`

`generate_new_dishes` 受「本周食材」约束，不适合规划（规划就是要决定买什么），所以另起 prompt。

- [ ] **Step 1: 写失败测试**

在 `tests/unit/test_llm_providers.py` 末尾（`_StubProvider` 已定义，会记录 prompt 到 `self.prompts`）加：
```python
def test_generate_plan_dishes_includes_count_and_known_in_prompt():
    out = _json.dumps({"dishes": []})
    stub = _StubProvider(out)
    svc = LLMService(stub)
    svc.generate_plan_dishes(
        cuisine_prefs=["川"], spicy=2, dislikes=[],
        known_names=["番茄炒蛋"], count=3,
    )
    p = stub.prompts[0]
    assert "番茄炒蛋" in p
    assert "3" in p
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_llm_providers.py::test_generate_plan_dishes_includes_count_and_known_in_prompt -q`
Expected: FAIL（`AttributeError: 'LLMService' object has no attribute 'generate_plan_dishes'`）。

- [ ] **Step 3: 写 prompt 文件**

`app/prompts/plan_dishes.txt`（`{count}`/`{cuisine_prefs}`/`{dislikes}`/`{known_names}`/`{spicy}` 为真实占位；JSON 花括号一律 `{{`/`}}`）：
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
    {{"name":"...","category":"主菜|素食|汤类|饮品|西餐","cuisine":"...","spicy":0,"main_ingredients":["...","..."],"why_recommended":"一句话理由"}}
  ]
}}
共返回 {count} 道。
```

- [ ] **Step 4: 实现 service 方法**

在 `app/services/llm/service.py` 的 `LLMService` 类里，`generate_new_dishes` 之后加：
```python
    def generate_plan_dishes(
        self,
        *,
        cuisine_prefs,
        spicy,
        dislikes,
        known_names,
        count: int = 4,
    ) -> list[dict]:
        prompt = _load_prompt("plan_dishes.txt").format(
            cuisine_prefs=", ".join(cuisine_prefs) or "(无)",
            spicy=spicy,
            dislikes=", ".join(dislikes) or "(无)",
            known_names=", ".join(known_names) or "(无)",
            count=count,
        )
        data = parse_llm_json(self.provider.generate(prompt, temperature=0.8))
        return list(data.get("dishes", []))
```

- [ ] **Step 5: 跑测试 + 全量**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_llm_providers.py -q`
Expected: PASS。
Run: `.venv\Scripts\python.exe -m pytest -q --tb=short`
Expected: `141 passed`。

- [ ] **Step 6: Commit**

```bash
git add app/prompts/plan_dishes.txt app/services/llm/service.py tests/unit/test_llm_providers.py
git commit -m "feat(llm): add generate_plan_dishes with pantry-free planning prompt"
```

---

### Task E-T3: `factory.plan_new_dishes`（pro→flash 兜底）

**Files:**
- Modify: `app/services/llm/factory.py`
- Test: `tests/unit/test_llm_factory.py`

与 `recommend_new_dishes` 同样的 429→flash 兜底，返回 `(list, fell_back)`。

- [ ] **Step 1: 写失败测试**

在 `tests/unit/test_llm_factory.py` 末尾加（文件已 import `encrypt`、`LLMConfig`、`LLMUnavailable`、`build_llm_for_user`，并有 `db`/`_user` fixture）：
```python
def test_plan_new_dishes_falls_back_to_flash_on_quota(monkeypatch, db):
    from app.services.llm import factory

    u = _user(db)
    db.add(LLMConfig(user_id=u.id, provider="gemini",
                     api_key_encrypted=encrypt("k"), model="gemini-2.5-pro"))
    db.commit()

    class _Stub:
        def __init__(self, fail):
            self.fail = fail

        def generate_plan_dishes(self, **kw):
            if self.fail:
                raise LLMUnavailable("429 RESOURCE_EXHAUSTED")
            return [{"name": "X"}]

    def fake_build(db_, user_, *, force_flash=False):
        return _Stub(fail=not force_flash)

    monkeypatch.setattr(factory, "build_llm_for_user", fake_build)
    dishes, fell = factory.plan_new_dishes(
        db, u, cuisine_prefs=[], spicy=2, dislikes=[], known_names=[], count=4)
    assert fell is True
    assert dishes == [{"name": "X"}]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_llm_factory.py::test_plan_new_dishes_falls_back_to_flash_on_quota -q`
Expected: FAIL（`AttributeError: module 'app.services.llm.factory' has no attribute 'plan_new_dishes'`）。

- [ ] **Step 3: 实现 factory 函数**

在 `app/services/llm/factory.py` 末尾（`recommend_new_dishes` 之后）加：
```python
def plan_new_dishes(
    db: Session, user: User, **kwargs
) -> tuple[list[dict], bool]:
    svc = build_llm_for_user(db, user)
    try:
        return svc.generate_plan_dishes(**kwargs), False
    except LLMUnavailable as e:
        if _is_quota_error(e) and is_gemini_pro_config(db, user):
            mark_pro_exhausted(db, user)
            return (
                build_llm_for_user(db, user, force_flash=True).generate_plan_dishes(
                    **kwargs
                ),
                True,
            )
        raise
```

- [ ] **Step 4: 跑测试 + 全量**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_llm_factory.py -q`
Expected: PASS。
Run: `.venv\Scripts\python.exe -m pytest -q --tb=short`
Expected: `142 passed`。

- [ ] **Step 5: Commit**

```bash
git add app/services/llm/factory.py tests/unit/test_llm_factory.py
git commit -m "feat(llm): add plan_new_dishes factory with pro->flash fallback"
```

---

### Task E-T4: `compose_candidates` 纯函数

**Files:**
- Create: `app/routes/plan.py`（先只放纯函数，端点在 E-T5 加）
- Test: `tests/unit/test_plan_compose.py`（新建）

- [ ] **Step 1: 写失败测试**

`tests/unit/test_plan_compose.py`：
```python
from app.routes.plan import compose_candidates


def test_compose_candidates_known_first_ai_deduped_capped():
    known = [{"name": f"k{i}"} for i in range(8)]
    ai = [{"name": "k0"}, {"name": "a1"}, {"name": "a2"}, {"name": "a3"}]
    out = compose_candidates(known, ai, limit=10)
    assert [c["name"] for c in out] == [
        "k0", "k1", "k2", "k3", "k4", "k5", "k6", "k7", "a1", "a2",
    ]


def test_compose_candidates_empty_ai():
    known = [{"name": "a"}, {"name": "b"}]
    assert compose_candidates(known, [], limit=10) == known
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_plan_compose.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.routes.plan'`）。

- [ ] **Step 3: 创建 `app/routes/plan.py`（纯函数部分）**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Dish, Profile, User
from app.db.session import get_db
from app.services.auth import current_user
from app.services.filters import has_forbidden
from app.services.llm import factory
from app.services.llm.base import LLMParseError, LLMUnavailable
from app.services.quota import bump_quota, today_quota
from app.services.scoring import score_dish

router = APIRouter(prefix="/api/plan", tags=["plan"])

MAX_KNOWN = 8
AI_COUNT = 4
TOTAL = 10


def compose_candidates(
    known_dicts: list[dict], ai_dicts: list[dict], limit: int = TOTAL
) -> list[dict]:
    """known 在前（调用方已排序），ai 去掉与 known 重名的，合并截断到 limit。"""
    known_names = {d["name"] for d in known_dicts}
    ai_unique = [d for d in ai_dicts if d["name"] not in known_names]
    return (known_dicts + ai_unique)[:limit]
```

- [ ] **Step 4: 跑测试 + 全量**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_plan_compose.py -q`
Expected: PASS。
Run: `.venv\Scripts\python.exe -m pytest -q --tb=short`
Expected: `144 passed`（+2）。

- [ ] **Step 5: Commit**

```bash
git add app/routes/plan.py tests/unit/test_plan_compose.py
git commit -m "feat(plan): add compose_candidates helper"
```

---

### Task E-T5: `/api/plan/candidates` 端点 + 注册 + conftest 桩

**Files:**
- Modify: `app/routes/plan.py`（加端点）
- Modify: `app/main.py`（注册路由）
- Modify: `tests/conftest.py`（fake_llm 增补 plan 桩）
- Test: `tests/integration/test_plan.py`（新建）

- [ ] **Step 1: conftest 增补 plan 桩**

在 `tests/conftest.py` 的 `FakeLLM.__init__` 里加：
```python
        self.plan_queue = []     # lists or Exceptions
        self.plan_calls = 0
```
在 `FakeLLM` 里加方法：
```python
    def plan_dishes(self):
        self.plan_calls += 1
        r = self.plan_queue.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
```
在 `fake_llm` fixture 里（已 monkeypatch classify/recommend 处）加：
```python
    def _plan(db, user, **kwargs):
        return f.plan_dishes(), False

    monkeypatch.setattr(_llm_factory, "plan_new_dishes", _plan)
```

- [ ] **Step 2: 写失败测试**

`tests/integration/test_plan.py`：
```python
from datetime import date

from app.db.models import ApiQuota, Dish
from app.services.auth import create_token


def _seed_dish(db_session, user_id, **kw) -> Dish:
    d = Dish(
        user_id=user_id, name=kw["name"],
        category=kw.get("category", "主菜"), cuisine=kw.get("cuisine", "家常"),
        main_ingredients=kw.get("main_ingredients", []), spicy=kw.get("spicy", 0),
        tags=[], source=kw.get("source", "user_known"),
        cook_count=kw.get("cook_count", 0), needs_review=False,
    )
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    return d


def test_plan_candidates_known_sorted_and_dislikes_filtered(authed_client, db_session, fake_llm, test_user):
    authed_client.put("/api/profile", json={"cuisine_prefs": [], "spicy": 2, "dislikes": ["香菜"]})
    _seed_dish(db_session, test_user.id, name="A", cook_count=5)
    _seed_dish(db_session, test_user.id, name="B", cook_count=0)
    _seed_dish(db_session, test_user.id, name="香菜鸡", main_ingredients=["香菜", "鸡肉"])
    fake_llm.plan_queue.append([])
    r = authed_client.post("/api/plan/candidates", json={})
    assert r.status_code == 200
    names = [c["name"] for c in r.json()["candidates"]]
    assert "香菜鸡" not in names
    assert names[0] == "A"


def test_plan_candidates_merges_ai_dishes(authed_client, db_session, fake_llm, test_user):
    _seed_dish(db_session, test_user.id, name="番茄炒蛋", main_ingredients=["番茄", "鸡蛋"])
    fake_llm.plan_queue.append([
        {"name": "罗宋汤", "category": "汤类", "cuisine": "俄式", "spicy": 0,
         "main_ingredients": ["牛肉", "土豆"], "why_recommended": "暖"},
        {"name": "番茄炒蛋", "category": "主菜", "cuisine": "家常", "spicy": 0,
         "main_ingredients": ["番茄", "鸡蛋"], "why_recommended": "dup"},
    ])
    r = authed_client.post("/api/plan/candidates", json={})
    by_name = {c["name"]: c for c in r.json()["candidates"]}
    assert by_name["番茄炒蛋"]["source"] == "known"
    assert by_name["罗宋汤"]["source"] == "ai"
    assert by_name["罗宋汤"]["id"] is None
    assert [c["name"] for c in r.json()["candidates"] if c["source"] == "ai"] == ["罗宋汤"]
    assert r.json()["ai_warning"] is None


def test_plan_candidates_ai_failure_degrades(authed_client, db_session, fake_llm, test_user):
    from app.services.llm.base import LLMUnavailable
    _seed_dish(db_session, test_user.id, name="番茄炒蛋", main_ingredients=["番茄", "鸡蛋"])
    fake_llm.plan_queue.append(LLMUnavailable("network"))
    r = authed_client.post("/api/plan/candidates", json={})
    body = r.json()
    assert [c["name"] for c in body["candidates"]] == ["番茄炒蛋"]
    assert body["ai_warning"]


def test_plan_candidates_quota_exhausted_skips_ai(authed_client, db_session, fake_llm, test_user):
    _seed_dish(db_session, test_user.id, name="番茄炒蛋", main_ingredients=["番茄", "鸡蛋"])
    db_session.add(ApiQuota(user_id=test_user.id, quota_date=date.today(), count=999))
    db_session.commit()
    r = authed_client.post("/api/plan/candidates", json={})
    body = r.json()
    assert [c["name"] for c in body["candidates"]] == ["番茄炒蛋"]
    assert "配额" in body["ai_warning"]
    assert fake_llm.plan_calls == 0


def test_plan_candidates_isolation(authed_client, db_session, fake_llm, test_user, test_user_b):
    _seed_dish(db_session, test_user.id, name="A's dish", main_ingredients=["番茄"])
    b_token = create_token(user_id=test_user_b.id, username=test_user_b.username)
    authed_client.headers.update({"Authorization": f"Bearer {b_token}"})
    fake_llm.plan_queue.append([])
    r = authed_client.post("/api/plan/candidates", json={})
    assert r.json()["candidates"] == []


def test_plan_candidates_requires_auth(client):
    assert client.post("/api/plan/candidates", json={}).status_code == 401
```

- [ ] **Step 3: 跑测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_plan.py -q`
Expected: FAIL（404 / 路由未注册）。

- [ ] **Step 4: 实现端点**

在 `app/routes/plan.py` 末尾加候选构造器与端点：
```python
def _known_to_candidate(d: Dish) -> dict:
    return {
        "id": d.id, "name": d.name, "category": d.category, "cuisine": d.cuisine,
        "spicy": d.spicy, "main_ingredients": d.main_ingredients,
        "source": "known", "why_recommended": None,
    }


def _ai_to_candidate(d: dict) -> dict:
    return {
        "id": None, "name": d.get("name"), "category": d.get("category"),
        "cuisine": d.get("cuisine"), "spicy": int(d.get("spicy", 0) or 0),
        "main_ingredients": d.get("main_ingredients", []) or [],
        "source": "ai", "why_recommended": d.get("why_recommended", ""),
    }


@router.post("/candidates")
def candidates(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    profile = db.get(Profile, user.id)
    all_known = list(
        db.scalars(select(Dish).where(Dish.user_id == user.id, Dish.source == "user_known"))
    )
    eligible = [
        d for d in all_known
        if not has_forbidden(d.cuisine, d.main_ingredients, profile.dislikes)
    ]
    eligible.sort(key=lambda d: score_dish(d, profile), reverse=True)
    known_dicts = [_known_to_candidate(d) for d in eligible[:MAX_KNOWN]]

    ai_dicts: list[dict] = []
    ai_warning: str | None = None
    if today_quota(db, user.id) >= settings.daily_gemini_quota:
        ai_warning = "今日 AI 配额已用尽，仅从会做的菜推荐"
    else:
        try:
            raw, _fell = factory.plan_new_dishes(
                db, user,
                cuisine_prefs=profile.cuisine_prefs, spicy=profile.spicy,
                dislikes=profile.dislikes,
                known_names=[d.name for d in all_known], count=AI_COUNT,
            )
            bump_quota(db, user.id)
            for d in raw:
                if has_forbidden(d.get("cuisine"), d.get("main_ingredients", []) or [], profile.dislikes):
                    continue
                ai_dicts.append(_ai_to_candidate(d))
        except (LLMUnavailable, LLMParseError):
            ai_warning = "AI 新菜暂时没取到，可只从会做的菜里挑"

    return {
        "candidates": compose_candidates(known_dicts, ai_dicts, limit=TOTAL),
        "ai_warning": ai_warning,
    }
```

- [ ] **Step 5: 注册路由**

在 `app/main.py`，跟着已有 `from app.routes import ...` 把 `plan` 加进 import，并在注册区加 `app.include_router(plan.router)`（与 recommend 等同样方式）。

- [ ] **Step 6: 跑测试 + 全量**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_plan.py -q`
Expected: PASS（6 passed）。
Run: `.venv\Scripts\python.exe -m pytest -q --tb=short`
Expected: `150 passed`（144 + 6）。

- [ ] **Step 7: Commit**

```bash
git add app/routes/plan.py app/main.py tests/conftest.py tests/integration/test_plan.py
git commit -m "feat(plan): add /api/plan/candidates endpoint"
```

---

### Task E-T6: 前端规划 UI（控制器直接写，不派 subagent）

**Files:**
- Modify: `static/index.html`（本周食材 section）
- Modify: `static/app.js`

> 执行说明：前端由控制器直接编辑（本仓库既有约定，转写更可靠），不派 subagent。spec 审查后做浏览器手测。

- [ ] **Step 1: app.js 加 planning 状态与方法**

在 `setup()` 内、`ingredientsText` 附近加：
```javascript
    const planning = reactive({ open: false, loading: false, candidates: [], selected: [], aiWarning: "" });

    async function openPlanner() {
      planning.open = true; planning.loading = true; planning.candidates = []; planning.selected = []; planning.aiWarning = "";
      try {
        const { data } = await safeApi("/api/plan/candidates", { method: "POST", body: {} });
        planning.candidates = data.candidates || [];
        planning.aiWarning = data.ai_warning || "";
      } catch (e) { planning.aiWarning = e.detail || "规划失败，请稍后再试"; }
      finally { planning.loading = false; }
    }
    function togglePlanPick(name) {
      const i = planning.selected.indexOf(name);
      if (i >= 0) planning.selected.splice(i, 1); else planning.selected.push(name);
    }
    function shoppingList() {
      const have = new Set(currentIngredients());
      const need = [];
      for (const c of planning.candidates) {
        if (!planning.selected.includes(c.name)) continue;
        for (const ing of (c.main_ingredients || [])) {
          if (!have.has(ing) && !need.includes(ing)) need.push(ing);
        }
      }
      return need;
    }
    async function addPlanToIngredients() {
      const need = shoppingList();
      if (!planning.selected.length) { planning.aiWarning = "先勾选几道菜"; return; }
      const merged = Array.from(new Set([...currentIngredients(), ...need]));
      try {
        await safeApi("/api/ingredients", { method: "PUT", body: { items: merged } });
        ingredientsText.value = merged.join(", ");
        planning.open = false;
        ingredientsSaved.value = true; setTimeout(() => (ingredientsSaved.value = false), 2000);
      } catch {}
    }
```
并把这些加入 `setup()` 的 `return { ... }`：`planning, openPlanner, togglePlanPick, shoppingList, addPlanToIngredients,`。

- [ ] **Step 2: index.html 本周食材 section 加规划入口与面板**

在 `本周食材` `<section v-if="tab==='ingredients'">` 顶部（`<p class="hint">常见食材…` 之前）插入：
```html
        <button class="btn btn-primary" style="margin-bottom:.75rem" @click="openPlanner">还没买菜？帮我规划本周</button>
        <div v-if="planning.open" class="card">
          <p v-if="planning.loading" class="empty">规划中…</p>
          <div v-if="planning.aiWarning" class="warning">{{ planning.aiWarning }}</div>
          <div v-if="!planning.loading && planning.candidates.length">
            <div class="section-head"><span class="dot sage"></span>挑几道想做的</div>
            <div class="chip-row">
              <span v-for="c in planning.candidates" :key="c.source + c.name"
                    class="chip" :class="{ on: planning.selected.includes(c.name) }"
                    @click="togglePlanPick(c.name)">
                {{ c.name }}<span v-if="c.source==='ai'" class="new-tag">新</span>
              </span>
            </div>
            <div v-if="shoppingList().length">
              <div class="section-head"><span class="dot yellow"></span>需要采购</div>
              <div class="chip-row"><span v-for="ing in shoppingList()" :key="ing" class="chip on">{{ ing }}</span></div>
              <button class="btn btn-primary" @click="addPlanToIngredients">加入本周食材</button>
            </div>
            <p v-else-if="planning.selected.length" class="empty">这些菜的食材你都已有，无需采购。</p>
          </div>
          <p v-if="!planning.loading && !planning.candidates.length && !planning.aiWarning" class="empty">还没有可推荐的菜，先去「会的菜」添加几道。</p>
        </div>
```

- [ ] **Step 3: 语法自检**

Run: `node --check static/app.js`
Expected: 无输出（语法 OK）。

- [ ] **Step 4: 浏览器手测（spec 审查后）**

本地起服务（`.venv\Scripts\python.exe -m uvicorn app.main:app --reload`），登录 → 本周食材 → 点「还没买菜？帮我规划本周」：
- 出候选（会的菜 + AI 新菜带「新」标签）；勾选若干 → 出「需要采购」（只列当前食材里没有的）。
- 点「加入本周食材」→ 文本框合并去重、面板收起、显示「已保存」。
- 全选已有食材的菜 → 显示「无需采购」。

- [ ] **Step 5: Commit**

```bash
git add static/index.html static/app.js
git commit -m "feat(ui): weekly shopping-list planner in ingredients tab"
```

---

### Task E-T7: 部署（用户）

- [ ] push（触发 Vercel）。无 DB schema 变更（不需要迁移）。
- [ ] 线上手测同 E-T6 Step 4。

---

## Self-Review

**Spec coverage:** §3.1 端点→E-T5；§3.2 compose→E-T4；§3.3 prompt + §3.4 service→E-T2；§3.5 factory→E-T3；§3.6 quota.py→E-T1；§3.7 main 注册→E-T5 Step 5；§4 前端→E-T6；§5 错误处理→E-T5 测试（AI 失败/配额/无菜）+ E-T6（0 选/全已有）；§6 测试→各任务。全覆盖。

**Placeholder scan:** 无 TBD/TODO；每个改代码步骤都给了完整代码。

**Type consistency:** 候选字典键 `id/name/category/cuisine/spicy/main_ingredients/source/why_recommended` 在 `_known_to_candidate`/`_ai_to_candidate`/compose/测试/前端一致；`source` 取值 `"known"`/`"ai"` 一致；`plan_new_dishes` 返回 `(list, bool)` 与 recommend 一致；前端按 `c.name` 选择、`c.source` 判 AI，与端点字段一致。
