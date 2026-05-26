# 子项目 G：本周食材份量 + 已用完 + 自动结转 设计文档

> 本周食材给每个食材加自由文本份量；加「已用完」开关（用完的不再推荐、不结转）；
> 进入新一周自动带上周没用完的食材+份量。
> 设计冻结日期：2026-05-26

---

## 1. 目标与范围

食材现在只有名字。加：
- 每个食材一个**自由文本份量**（"2个"/"一把"/"500g"），仅记录/显示。
- 每个食材一个**「已用完」开关**：用完的食材推荐时排除（不会推到需要它的菜），且不结转下周。
- 进入新一周时，自动把上周**没用完**的食材+份量带过来（用完的丢弃）。

### In Scope
- `WeeklyIngredients` 加 `quantities`（dict 名→份量文本）和 `used_up`（list 名）两列 + 迁移脚本。
- `ensure_current_week(db, user)` 结转助手：当周无行时，从最近一个有食材的历史周复制「未用完」items+quantities 到当周（used_up 清空）。ingredients GET 与 recommend 都用它。
- ingredients GET 返回 items+quantities+used_up；PUT 接收并存三者，并清理 quantities/used_up 中已不在 items 的名字。
- recommend 的 pantry = items − used_up（这是 recommend 唯一改动）。
- 前端「本周食材」加份量表：每行 名字·份量输入·「已用完」开关；一个保存键存三者。

### Out of Scope
- 份量数值化/单位/换算（纯文本）。
- 份量影响推荐数量（不做）。
- 采购清单（子项目 E）与 used_up 的联动（已用完的食材在采购清单里仍按"已有名字"算，不自动重买）——本版不动。
- 做菜自动扣减份量（自由文本无法可靠扣减）。

---

## 2. 数据模型 + 迁移

### 2.1 `WeeklyIngredients` 现状
`app/db/models.py`：
```python
class WeeklyIngredients(Base):
    __tablename__ = "weekly_ingredients"
    __table_args__ = (UniqueConstraint("user_id", "week_start", name="uq_weekly_user_week"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    items: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

### 2.2 加两列
```python
    quantities: Mapped[dict] = mapped_column(JSON, default=dict)   # {name: "份量文本"}
    used_up: Mapped[list] = mapped_column(JSON, default=list)      # [已用完的 name]
```
`items` 仍是规范的食材名有序列表（recommend 的 pantry 来源）。`quantities` 按名映射份量文本；`used_up` 是已用完名字集合。

### 2.3 迁移脚本 `scripts/migrate_add_quantities.py`（幂等，两个 ALTER）
```python
"""Add weekly_ingredients.quantities and used_up columns (idempotent).
Usage (PowerShell, Neon):
    $env:DATABASE_URL = "postgresql+psycopg://..."
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

---

## 3. 结转助手 `app/services/pantry.py`

```python
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User, WeeklyIngredients
from app.services.week import get_monday


def ensure_current_week(db: Session, user: User) -> WeeklyIngredients | None:
    """当周行存在则返回；否则从最近一个有食材的历史周结转「未用完」的
    items+quantities 到当周（used_up 清空），并持久化。无历史则返回 None。"""
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
- 只复制未用完的食材；份量同带；used_up 重置空。
- recommend 与 ingredients GET 共用，保证"开新页/直接推荐"都能自动结转。

---

## 4. 后端路由改动

### 4.1 `app/routes/ingredients.py`
- `IngredientsOut` 加 `quantities: dict[str, str]` 和 `used_up: list[str]`。
- `IngredientsIn` 加 `quantities: dict[str, str] = {}` 和 `used_up: list[str] = []`。
- GET：用 `ensure_current_week(db, user)`；无则返回 `week_start=None, items=[], quantities={}, used_up=[]`；有则返回该行四字段。
- PUT：存 items；并把 `quantities` 清理为只含 items 里的名字（`{n: q for n,q in body.quantities.items() if n in body.items}`）；`used_up` 清理为只含 items 里的名字（`[n for n in body.used_up if n in body.items]`）。返回存后的四字段。

### 4.2 `app/routes/recommend.py`
- 把当周查询替换为 `from app.services.pantry import ensure_current_week` → `week = ensure_current_week(db, user)`。
- `if week is None or not week.items: return {"error": "INGREDIENTS_EMPTY"}`（不变）。
- pantry 改为排除已用完：
```python
    used = set(week.used_up or [])
    pantry = [n for n in week.items if n not in used]
    if not pantry:
        return {"error": "INGREDIENTS_EMPTY"}
```
（其余 candidates/can_cook_with/Gemini 逻辑不变；pantry 仍是名字列表。）

---

## 5. 前端（本周食材 tab）

- 状态：`quantities`（reactive map 名→份量文本）、`usedUp`（reactive 数组，名字）。
- 名字仍由 chips + textarea 决定（现有 `ingredientsText`/`currentIngredients()`）。
- **份量表**：对 `currentIngredients()` 每个名字渲染一行：
  - 名字
  - 份量 `<input v-model="quantities[name]">`（窄输入）
  - 「已用完」开关（chip 或 checkbox），点了把名字加入/移出 `usedUp`；已用完行加 `.used` 灰/删除线样式。
  - 表在有食材时显示（录入/保存后自然出现）。
- 加载（loadIngredients）：从 GET 拿 items/quantities/used_up，填 `ingredientsText`、`quantities`、`usedUp`。
- 保存（saveIngredients）：PUT `{ items: currentIngredients(), quantities, used_up: usedUp }`。
- chips/textarea 改名字后，份量表实时跟随；保存时后端再清理孤儿键。

CSS：份量表行布局（flex）；`.used` 样式（灰 + line-through）。

---

## 6. 错误处理
| 场景 | 处理 |
|---|---|
| 当周无行、有上周 | 结转未用完项；recommend/GET 正常 |
| 当周无行、无历史 | GET 返回空；recommend INGREDIENTS_EMPTY |
| 全部已用完 | pantry 空 → recommend INGREDIENTS_EMPTY；结转时 kept 空 → 不建行 |
| quantities/used_up 含已删名字 | PUT 时清理掉 |
| 旧行无 quantities/used_up（迁移前数据） | 列默认 `{}`/`[]`；读时 `or {}` / `or []` 兜底 |

## 7. 测试
- **单元** `ensure_current_week`：当周已存在→原样返回；无当周+上周有未用完→建当周（只含未用完 + 对应份量 + used_up 空）；无历史→None；上周全用完→None。
- **集成** ingredients：GET 返回 items+quantities+used_up；PUT 存三者并清理孤儿 quantities/used_up 键；新周 GET 自动结转上周未用完。
- **集成** recommend：用 ensure_current_week 后，已用完食材不进 pantry（标 used_up 的菜不推荐）；全用完→INGREDIENTS_EMPTY；既有 recommend 测试（无 used_up）保持绿。
- 预估 +10 测试（当前 158 → ~168）。

## 8. 文件改动清单
```
新增:
  app/services/pantry.py          ensure_current_week 结转助手
  scripts/migrate_add_quantities.py  加 quantities + used_up 列（幂等）
修改:
  app/db/models.py                WeeklyIngredients + quantities + used_up
  app/routes/ingredients.py       GET/PUT 带 quantities + used_up；GET 用结转助手
  app/routes/recommend.py         用结转助手；pantry 排除 used_up
  static/index.html               份量表（份量输入 + 已用完开关）
  static/app.js                   quantities/usedUp 状态 + load/save
  static/style.css                份量表行 + .used 样式
  tests/...                       新增/更新（见 §7）
依赖：无新增
```

## 9. 部署注记
- push 前/后对 Neon 跑 `python -m scripts.migrate_add_quantities`（加两列）。SQLite 测试自动建列。

## 10. 澄清记录
| 维度 | 决策 |
|---|---|
| 份量格式 | 自由文本 |
| 结转 | 新周自动带上周「未用完」items+quantities，used_up 清空 |
| 份量影响推荐 | 否（仅记录/显示） |
| 已用完按钮 | 加；用完的食材 recommend 排除、不结转 |
| 数据模型 | 加 quantities(dict) + used_up(list) 两列（additive，items 仍是名字列表） |
| 采购清单联动 | 本版不动 |

## 11. 变更记录
- 2026-05-26：子项目 G 设计冻结
