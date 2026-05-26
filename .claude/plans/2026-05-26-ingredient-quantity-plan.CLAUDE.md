# 本周食材份量 + 已用完 + 结转（子项目 G）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 本周食材给每个食材加自由文本份量 + 「已用完」开关（用完的推荐时排除、不结转）；进入新一周自动带上周未用完的食材+份量。

**Architecture:** `WeeklyIngredients` 加 `quantities`(dict 名→份量文本) 与 `used_up`(list 名) 两列；`ensure_current_week` 助手在当周无行时从最近历史周结转「未用完」项；ingredients GET/PUT 带这两字段；recommend 的 pantry = items − used_up（唯一改动）。份量纯展示，不参与推荐计算。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Vue 3 (CDN)。所有命令在 `D:\recipe-recommender` 下用 `.venv\Scripts\python.exe`。当前测试 158 passed。提交禁止任何 `Co-Authored-By`/署名脚注。

---

## 文件结构
```
新增:
  app/services/pantry.py             ensure_current_week 结转助手
  scripts/migrate_add_quantities.py  加 quantities + used_up 列（幂等，两 ALTER）
  tests/unit/test_pantry.py
修改:
  app/db/models.py                   WeeklyIngredients + quantities + used_up
  app/routes/ingredients.py          GET/PUT 带 quantities + used_up；GET 用结转助手；PUT 清理孤儿键
  app/routes/recommend.py            用结转助手；pantry 排除 used_up
  static/index.html                  份量表（份量输入 + 已用完开关）
  static/app.js                      quantities/usedUp 状态 + load/save
  static/style.css                   份量表行 + .used 样式
  tests/integration/test_ingredients.py   + quantities/used_up/carryover
  tests/integration/test_recommend.py     + used_up 排除
```

---

### Task G-T1: `WeeklyIngredients` 加列 + 迁移脚本

**Files:** Modify `app/db/models.py`；Create `scripts/migrate_add_quantities.py`

- [ ] **Step 1: 加两列**

在 `app/db/models.py` 的 `WeeklyIngredients` 类里，`items: Mapped[list] = mapped_column(JSON, default=list)` 之后加：
```python
    quantities: Mapped[dict] = mapped_column(JSON, default=dict)
    used_up: Mapped[list] = mapped_column(JSON, default=list)
```
（`JSON` 已导入；无需改 import。）

- [ ] **Step 2: 验证列存在**

Run: `.venv\Scripts\python.exe -c "from app.db.models import WeeklyIngredients as W; print('quantities' in W.__table__.columns and 'used_up' in W.__table__.columns)"`
Expected: `True`

- [ ] **Step 3: 迁移脚本**

Create `scripts/migrate_add_quantities.py`:
```python
"""Add weekly_ingredients.quantities and used_up columns (idempotent).

Usage (PowerShell, Neon):
    $env:DATABASE_URL = "postgresql+psycopg://user:pass@host/db?sslmode=require"
    python -m scripts.migrate_add_quantities
"""
from __future__ import annotations

from sqlalchemy import text

from app.db.session import engine


def main() -> int:
    print(f"Ensuring quantity columns on: {engine.url.render_as_string(hide_password=True)}")
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE weekly_ingredients ADD COLUMN IF NOT EXISTS quantities JSON DEFAULT '{}'"))
        conn.execute(text("ALTER TABLE weekly_ingredients ADD COLUMN IF NOT EXISTS used_up JSON DEFAULT '[]'"))
    print("quantity columns ensured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 脚本可导入 + 全量绿**

Run: `.venv\Scripts\python.exe -c "import scripts.migrate_add_quantities; print('import ok')"` → `import ok`
Run: `.venv\Scripts\python.exe -m pytest -q --tb=short` → `158 passed`（SQLite 自动建列）。不要对真实库跑脚本。

- [ ] **Step 5: Commit**
```bash
git add app/db/models.py scripts/migrate_add_quantities.py
git commit -m "feat(db): add WeeklyIngredients quantities and used_up columns"
```

---

### Task G-T2: `ensure_current_week` 结转助手

**Files:** Create `app/services/pantry.py`；Test `tests/unit/test_pantry.py`

- [ ] **Step 1: 写失败测试**

Create `tests/unit/test_pantry.py`（用 root conftest 的 `db_session`/`test_user` fixture）：
```python
from datetime import date, timedelta

from app.db.models import WeeklyIngredients
from app.services.pantry import ensure_current_week
from app.services.week import get_monday


def _prev_monday():
    return get_monday(date.today()) - timedelta(days=7)


def test_ensure_returns_existing_current_week(db_session, test_user):
    ws = get_monday(date.today())
    db_session.add(WeeklyIngredients(user_id=test_user.id, week_start=ws,
        items=["番茄"], quantities={"番茄": "2个"}, used_up=[]))
    db_session.commit()
    got = ensure_current_week(db_session, test_user)
    assert got.week_start == ws
    assert got.items == ["番茄"]


def test_ensure_carries_unused_from_prev_week(db_session, test_user):
    db_session.add(WeeklyIngredients(user_id=test_user.id, week_start=_prev_monday(),
        items=["番茄", "鸡蛋", "牛奶"],
        quantities={"番茄": "2个", "鸡蛋": "3个", "牛奶": "1盒"}, used_up=["鸡蛋"]))
    db_session.commit()
    got = ensure_current_week(db_session, test_user)
    assert got.week_start == get_monday(date.today())
    assert got.items == ["番茄", "牛奶"]
    assert got.quantities == {"番茄": "2个", "牛奶": "1盒"}
    assert got.used_up == []


def test_ensure_no_history_returns_none(db_session, test_user):
    assert ensure_current_week(db_session, test_user) is None


def test_ensure_all_used_up_returns_none(db_session, test_user):
    db_session.add(WeeklyIngredients(user_id=test_user.id, week_start=_prev_monday(),
        items=["番茄"], quantities={"番茄": "2个"}, used_up=["番茄"]))
    db_session.commit()
    assert ensure_current_week(db_session, test_user) is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_pantry.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.services.pantry'`)。

- [ ] **Step 3: 实现助手**

Create `app/services/pantry.py`:
```python
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User, WeeklyIngredients
from app.services.week import get_monday


def ensure_current_week(db: Session, user: User) -> WeeklyIngredients | None:
    """Return the current week's row; if absent, carry over the not-used-up
    items + quantities from the most recent prior week (used_up reset). Returns
    None when there's no prior data to carry."""
    ws = get_monday(date.today())
    row = db.scalar(
        select(WeeklyIngredients).where(
            WeeklyIngredients.user_id == user.id,
            WeeklyIngredients.week_start == ws,
        )
    )
    if row is not None:
        return row
    prev = db.scalar(
        select(WeeklyIngredients)
        .where(WeeklyIngredients.user_id == user.id, WeeklyIngredients.week_start < ws)
        .order_by(WeeklyIngredients.week_start.desc())
    )
    if prev is None or not prev.items:
        return None
    used = set(prev.used_up or [])
    kept = [n for n in prev.items if n not in used]
    if not kept:
        return None
    qty = {n: v for n, v in (prev.quantities or {}).items() if n in kept}
    row = WeeklyIngredients(
        user_id=user.id, week_start=ws, items=kept, quantities=qty, used_up=[]
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
```

- [ ] **Step 4: 跑测试 + 全量**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_pantry.py -q` → 4 passed。
Run: `.venv\Scripts\python.exe -m pytest -q --tb=short` → `162 passed`（+4）。

- [ ] **Step 5: Commit**
```bash
git add app/services/pantry.py tests/unit/test_pantry.py
git commit -m "feat(pantry): add ensure_current_week carryover helper"
```

---

### Task G-T3: ingredients GET/PUT 带 quantities + used_up + 结转

**Files:** Modify `app/routes/ingredients.py`；Test `tests/integration/test_ingredients.py`

- [ ] **Step 1: 写失败测试**

在 `tests/integration/test_ingredients.py` 末尾加：
```python
def test_put_get_quantities_and_used_up(authed_client):
    r = authed_client.put("/api/ingredients", json={
        "items": ["番茄", "鸡蛋"], "quantities": {"番茄": "2个"}, "used_up": ["鸡蛋"]})
    assert r.status_code == 200
    g = authed_client.get("/api/ingredients").json()
    assert g["items"] == ["番茄", "鸡蛋"]
    assert g["quantities"] == {"番茄": "2个"}
    assert g["used_up"] == ["鸡蛋"]


def test_put_prunes_orphan_quantities_and_used_up(authed_client):
    r = authed_client.put("/api/ingredients", json={
        "items": ["番茄"], "quantities": {"番茄": "2个", "旧菜": "x"}, "used_up": ["旧菜"]})
    b = r.json()
    assert b["quantities"] == {"番茄": "2个"}
    assert b["used_up"] == []


def test_get_carries_over_from_prev_week(authed_client, db_session, test_user):
    from datetime import date, timedelta
    from app.db.models import WeeklyIngredients
    from app.services.week import get_monday
    db_session.add(WeeklyIngredients(
        user_id=test_user.id, week_start=get_monday(date.today()) - timedelta(days=7),
        items=["番茄", "鸡蛋"], quantities={"番茄": "2个"}, used_up=["鸡蛋"]))
    db_session.commit()
    g = authed_client.get("/api/ingredients").json()
    assert g["items"] == ["番茄"]
    assert g["quantities"] == {"番茄": "2个"}
    assert g["used_up"] == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_ingredients.py -q -k "quantities or carries"`
Expected: FAIL（响应无 quantities/used_up 键，或无结转）。

- [ ] **Step 3: 重写 `app/routes/ingredients.py`**

完整替换为：
```python
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User, WeeklyIngredients
from app.db.session import get_db
from app.services.auth import current_user
from app.services.pantry import ensure_current_week
from app.services.week import get_monday

router = APIRouter(prefix="/api/ingredients", tags=["ingredients"])


class IngredientsIn(BaseModel):
    items: list[str]
    quantities: dict[str, str] = {}
    used_up: list[str] = []


class IngredientsOut(BaseModel):
    week_start: date | None
    items: list[str]
    quantities: dict[str, str]
    used_up: list[str]


@router.get("", response_model=IngredientsOut)
def get_ingredients(db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = ensure_current_week(db, user)
    if row is None:
        return IngredientsOut(week_start=None, items=[], quantities={}, used_up=[])
    return IngredientsOut(
        week_start=row.week_start, items=row.items,
        quantities=row.quantities or {}, used_up=row.used_up or [],
    )


@router.put("", response_model=IngredientsOut)
def put_ingredients(
    body: IngredientsIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = get_monday(date.today())
    row = db.scalar(
        select(WeeklyIngredients).where(
            WeeklyIngredients.user_id == user.id,
            WeeklyIngredients.week_start == ws,
        )
    )
    item_set = set(body.items)
    quantities = {n: q for n, q in body.quantities.items() if n in item_set}
    used_up = [n for n in body.used_up if n in item_set]
    if row is None:
        row = WeeklyIngredients(
            user_id=user.id, week_start=ws, items=body.items,
            quantities=quantities, used_up=used_up,
        )
        db.add(row)
    else:
        row.items = body.items
        row.quantities = quantities
        row.used_up = used_up
        row.updated_at = datetime.utcnow()
    db.commit()
    return IngredientsOut(week_start=ws, items=body.items, quantities=quantities, used_up=used_up)
```

- [ ] **Step 4: 跑测试 + 全量**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_ingredients.py -q` → all pass。
Run: `.venv\Scripts\python.exe -m pytest -q --tb=short` → `165 passed`（+3）。

- [ ] **Step 5: Commit**
```bash
git add app/routes/ingredients.py tests/integration/test_ingredients.py
git commit -m "feat(ingredients): persist quantities/used_up and carry over weeks"
```

---

### Task G-T4: recommend 用结转助手 + pantry 排除 used_up

**Files:** Modify `app/routes/recommend.py`；Test `tests/integration/test_recommend.py`

- [ ] **Step 1: 写失败测试**

在 `tests/integration/test_recommend.py` 末尾加（文件已有 `_seed_dish`、`date` import、`fake_llm` 等）：
```python
def test_recommend_excludes_used_up_ingredients(authed_client, db_session, fake_llm, test_user):
    from app.db.models import WeeklyIngredients
    from app.services.week import get_monday
    db_session.add(WeeklyIngredients(
        user_id=test_user.id, week_start=get_monday(date.today()),
        items=["番茄", "鸡蛋"], quantities={}, used_up=["鸡蛋"]))
    db_session.commit()
    _seed_dish(db_session, test_user.id, name="番茄炒蛋", main_ingredients=["番茄", "鸡蛋"])
    _seed_dish(db_session, test_user.id, name="凉拌番茄", main_ingredients=["番茄"])
    fake_llm.new_dishes_queue.append([])
    r = authed_client.post("/api/recommend", json={"meal_type": "lunch"})
    names = [d["name"] for d in r.json()["known"]]
    assert "番茄炒蛋" not in names   # 鸡蛋 已用完，做不了
    assert "凉拌番茄" in names
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_recommend.py::test_recommend_excludes_used_up_ingredients -q`
Expected: FAIL（当前 pantry=全部 items，番茄炒蛋 会出现在 known）。

- [ ] **Step 3: 改 recommend**

在 `app/routes/recommend.py`：
1. 顶部加 import：
```python
from app.services.pantry import ensure_current_week
```
2. 把这段：
```python
    ws = get_monday(date.today())
    week = db.scalar(
        select(WeeklyIngredients).where(
            WeeklyIngredients.user_id == user.id,
            WeeklyIngredients.week_start == ws,
        )
    )
    if week is None or not week.items:
        return {"error": "INGREDIENTS_EMPTY"}
```
改为：
```python
    ws = get_monday(date.today())
    week = ensure_current_week(db, user)
    if week is None or not week.items:
        return {"error": "INGREDIENTS_EMPTY"}
```
（保留 `ws = get_monday(date.today())` —— 后面 cooked_ids 查询要用 `ws`。）
3. 把 `pantry = week.items` 改为：
```python
    used = set(week.used_up or [])
    pantry = [n for n in week.items if n not in used]
    if not pantry:
        return {"error": "INGREDIENTS_EMPTY"}
```
4. 删掉 import 行里现在不再使用的 `WeeklyIngredients`（用 Grep 确认 recommend.py 里 `WeeklyIngredients` 已无引用后，从 `from app.db.models import ...` 移除它；其余符号保留）。`select` 仍被 CookingLog/Dish 查询使用，保留。

- [ ] **Step 4: 跑测试 + 全量**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_recommend.py -q` → all pass。
Run: `.venv\Scripts\python.exe -m pytest -q --tb=short` → `166 passed`（+1）。

- [ ] **Step 5: Commit**
```bash
git add app/routes/recommend.py tests/integration/test_recommend.py
git commit -m "feat(recommend): carry over week and exclude used-up ingredients"
```

---

### Task G-T5: 前端份量表 + 已用完开关（控制器直接写，不派 subagent）

**Files:** Modify `static/app.js`、`static/index.html`、`static/style.css`

> 前端由控制器直接编辑（既有约定）。spec 审查后浏览器手测。

- [ ] **Step 1: app.js — quantities/usedUp 状态 + load/save**

在 `ingredientsText` 附近加：
```javascript
    const quantities = reactive({});   // { name: 份量文本 }
    const usedUp = ref([]);            // [已用完的 name]
```
方法（放在 `currentIngredients`/`toggleChip` 附近）：
```javascript
    function setQty(name, val) { quantities[name] = val; }
    function isUsedUp(name) { return usedUp.value.includes(name); }
    function toggleUsedUp(name) {
      const i = usedUp.value.indexOf(name);
      if (i >= 0) usedUp.value.splice(i, 1); else usedUp.value.push(name);
    }
```
改 `loadIngredients`：
```javascript
    async function loadIngredients() {
      try {
        const { data } = await safeApi("/api/ingredients");
        ingredientsText.value = (data.items || []).join(", ");
        Object.keys(quantities).forEach(k => delete quantities[k]);
        Object.assign(quantities, data.quantities || {});
        usedUp.value = data.used_up || [];
      } catch {}
    }
```
改 `saveIngredients`：
```javascript
    async function saveIngredients() {
      const items = currentIngredients();
      const itemSet = new Set(items);
      const qty = {}; for (const n of items) if (quantities[n]) qty[n] = quantities[n];
      const used = usedUp.value.filter(n => itemSet.has(n));
      try {
        await safeApi("/api/ingredients", { method: "PUT", body: { items, quantities: qty, used_up: used } });
        usedUp.value = used;
        ingredientsSaved.value = true; setTimeout(() => (ingredientsSaved.value = false), 2000);
      } catch {}
    }
```
在 `return { ... }` 加：`quantities, usedUp, setQty, isUsedUp, toggleUsedUp,`

- [ ] **Step 2: index.html — 份量表**

在「本周食材」section 里、`<textarea v-model="ingredientsText" ...>` 之后、保存按钮之前，插入：
```html
        <div v-if="currentIngredients().length" class="qty-table">
          <div class="section-head"><span class="dot sage"></span>份量（用完点「已用完」，下周不再带上）</div>
          <div v-for="name in currentIngredients()" :key="name" class="qty-row" :class="{ used: isUsedUp(name) }">
            <span class="qty-name">{{ name }}</span>
            <input class="qty-input" :value="quantities[name] || ''" @input="setQty(name, $event.target.value)" placeholder="份量，如 2个/一把/500g" />
            <span class="qty-flag" :class="{ on: isUsedUp(name) }" @click="toggleUsedUp(name)">已用完</span>
          </div>
        </div>
```
（保存按钮、已保存提示保持原样在其后。）

- [ ] **Step 3: style.css — 份量表样式（文件末尾）**
```css
/* === Quantity table === */
.qty-table { margin: .5rem 0 1rem; }
.qty-row { display: flex; align-items: center; gap: .5rem; padding: .35rem 0; border-bottom: 1px solid var(--border); }
.qty-row:last-child { border-bottom: none; }
.qty-row.used .qty-name { color: var(--text-3); text-decoration: line-through; }
.qty-name { flex: 0 0 5.5rem; font-size: 13px; }
.qty-input { flex: 1; padding: .35rem .5rem; border: 1px solid var(--border); border-radius: 8px; font-size: 13px; }
.qty-flag { flex: 0 0 auto; font-size: 11px; color: var(--text-2); border: 1px solid var(--border); border-radius: var(--radius-pill); padding: .2rem .6rem; cursor: pointer; user-select: none; }
.qty-flag.on { background: var(--coral); color: #fff; border-color: var(--coral); }
```

- [ ] **Step 4: 语法自检**

Run: `node --check static/app.js` → 无输出。

- [ ] **Step 5: 浏览器手测（spec 审查后）**

起服务 `.venv\Scripts\python.exe -m uvicorn app.main:app --reload`：
- 本周食材输入几个食材 → 下方份量表每行出现，填份量 → 保存 → 重进仍在。
- 点某食材「已用完」→ 行变灰删除线 → 保存 → 去推荐页，该食材不进 pantry（需要它的菜不出现）。
- 模拟新一周（可临时改系统时间或在 Neon 手动造上周行）→ 进本周食材，自动带上周未用完项+份量。

- [ ] **Step 6: Commit**
```bash
git add static/app.js static/index.html static/style.css
git commit -m "feat(ui): per-ingredient quantity input and used-up toggle"
```

---

### Task G-T6: 部署（用户）

- [ ] 对 Neon 跑 `python -m scripts.migrate_add_quantities`（加两列）。
- [ ] push（触发 Vercel）。
- [ ] 线上手测同 G-T5 Step 5。

---

## Self-Review

**Spec coverage:** §2.2 两列→G-T1；§2.3 迁移→G-T1；§3 结转助手→G-T2；§4.1 ingredients→G-T3；§4.2 recommend→G-T4；§5 前端→G-T5；§6 错误处理→G-T2/G-T3/G-T4 测试（无历史/全用完/孤儿键/排除）；§7 测试→各任务；§9 部署→G-T6。全覆盖。

**Placeholder scan:** 无 TBD/TODO；每个改代码步骤给了完整代码。

**Type consistency:** `quantities`(dict[str,str]) 与 `used_up`(list[str]) 在 model/IngredientsIn/IngredientsOut/ensure_current_week/recommend/前端一致；`ensure_current_week(db,user)->WeeklyIngredients|None` 在 ingredients GET 与 recommend 调用一致；recommend `pantry=[n for n in week.items if n not in set(week.used_up)]` 与 §4.2 一致；前端 `quantities[name]`/`usedUp` 与 PUT body `{items, quantities, used_up}` 和后端字段名一致。
