const { createApp, reactive, ref, onMounted } = Vue;

const TOKEN_KEY = "rr_token";
const USERNAME_KEY = "rr_username";
const COMMON_INGREDIENTS = ["番茄","鸡蛋","猪肉","鸡肉","牛肉","青菜","白菜","土豆","豆腐","大蒜","洋葱","胡萝卜","香菇","虾","豆角","茄子","黄瓜","青椒"];

async function api(path, opts = {}) {
  const token = localStorage.getItem(TOKEN_KEY);
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(path, { ...opts, headers, body: opts.body ? JSON.stringify(opts.body) : undefined });
  if (res.status === 401) { const e = new Error("Unauthorized"); e.status = 401; throw e; }
  if (!res.ok && res.status !== 409) {
    const e = new Error(`HTTP ${res.status}`); e.status = res.status;
    try { e.detail = (await res.json()).detail; } catch {}
    throw e;
  }
  return { status: res.status, data: res.status === 204 ? null : await res.json() };
}

createApp({
  setup() {
    const view = ref("loading");
    const auth = reactive({ token: null, username: null });
    const authMode = ref("login");
    const authForm = reactive({ username: "", password: "", invite_code: "" });
    const authError = ref(""); const authBusy = ref(false);

    const tab = ref("home");
    const loading = ref(false);
    const result = reactive({});

    const dishes = ref([]);
    const newDishName = ref(""); const addError = ref(""); const addBusy = ref(false); const addProgress = ref("");
    const editingId = ref(null);
    const editForm = reactive({ name: "", cuisine: "", ingredients: "", spicy: 0, category: "", meals: [], recipe: "" });
    const mealOpts = [["breakfast", "早餐"], ["lunch", "午餐"], ["dinner", "晚餐"]];
    const editError = ref("");
    const recipeViewId = ref(null);
    const recipeModal = reactive({ open: false, loading: false, title: "", text: "", error: "", dishId: null });

    const ingredientsText = ref(""); const ingredientsSaved = ref(false);
    const commonIngredients = COMMON_INGREDIENTS;
    const quantities = reactive({});   // { name: 份量文本 }
    const usedUp = ref([]);            // [已用完的 name]

    const planning = reactive({ open: false, loading: false, candidates: [], selected: [], aiWarning: "" });

    const history = ref(null);

    const profile = reactive({ cuisine_prefs: [], spicy: 2, dislikes: [] });
    const profileText = reactive({ cuisine: "", dislikes: "" });
    const profileSaved = ref(false);

    const llm = reactive({ provider: "gemini", base_url: "", model: "", api_key: "",
      has_key: false, key_tail: null, editingKey: false, usingDefault: true,
      models: [], fetching: false, modelError: "", saved: false });
    const LLM_PRESETS = { deepseek: "https://api.deepseek.com", openai: "https://api.openai.com/v1", moonshot: "https://api.moonshot.cn/v1" };
    function pickPreset(k) { llm.base_url = LLM_PRESETS[k]; }

    function mealLabel(m) { return { breakfast: "早餐", lunch: "午餐", dinner: "晚餐" }[m] || m; }
    function mealsShort(arr) {
      if (!arr || !arr.length) return "全部餐次";
      return arr.map(m => ({ breakfast: "早", lunch: "午", dinner: "晚" }[m] || m)).join("·");
    }
    function toggleEditMeal(m) {
      const i = editForm.meals.indexOf(m);
      if (i >= 0) editForm.meals.splice(i, 1); else editForm.meals.push(m);
    }
    function fmtDate(iso) { try { const d = new Date(iso); return `${d.getMonth()+1}/${d.getDate()}`; } catch { return ""; } }
    function splitItems(s) { return s.split(/[,，]/).map(x => x.trim()).filter(Boolean); }

    function setLoggedIn(token, username) {
      localStorage.setItem(TOKEN_KEY, token); localStorage.setItem(USERNAME_KEY, username);
      auth.token = token; auth.username = username; view.value = "main";
      loadDishes(); loadIngredients(); loadProfile();
    }
    function logout() {
      localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USERNAME_KEY);
      auth.token = null; auth.username = null; view.value = "login";
      authForm.username = ""; authForm.password = ""; authForm.invite_code = "";
    }
    function handle401() { logout(); }

    async function submitAuth() {
      authBusy.value = true; authError.value = "";
      try {
        const url = authMode.value === "login" ? "/api/auth/login" : "/api/auth/register";
        const body = authMode.value === "login"
          ? { username: authForm.username, password: authForm.password }
          : { username: authForm.username, password: authForm.password, invite_code: authForm.invite_code };
        const { status, data } = await api(url, { method: "POST", body });
        if (status !== 200 || !data || !data.token) { authError.value = (data && data.detail) || "注册或登录失败"; return; }
        setLoggedIn(data.token, data.username);
      } catch (e) {
        authError.value = e.status === 401 ? "用户名或密码错误" : (e.detail || e.message);
      } finally { authBusy.value = false; }
    }

    async function safeApi(...args) {
      try { return await api(...args); }
      catch (e) { if (e.status === 401) handle401(); throw e; }
    }

    function go(t) { tab.value = t; if (t === "history") loadHistory(); if (t === "settings") loadLlm(); }

    async function loadLlm() {
      try {
        const { data } = await safeApi("/api/llm-config");
        llm.provider = data.provider || "gemini"; llm.base_url = data.base_url || "";
        llm.model = data.model || ""; llm.has_key = data.has_key; llm.key_tail = data.key_tail;
        llm.usingDefault = data.using_default; llm.editingKey = !data.has_key; llm.api_key = "";
      } catch {}
    }
    async function fetchModels() {
      llm.modelError = ""; llm.fetching = true;
      try {
        const body = { provider: llm.provider, api_key: llm.api_key || "", base_url: llm.base_url || null };
        const { data } = await safeApi("/api/llm-config/models", { method: "POST", body });
        llm.models = data.models || [];
        if (!llm.model && llm.models.length) llm.model = llm.models[0];
      } catch (e) { llm.modelError = e.detail || "无法获取模型，请检查 key 或服务地址"; }
      finally { llm.fetching = false; }
    }
    async function saveLlm() {
      const body = { provider: llm.provider, base_url: llm.base_url || null, model: llm.model || null };
      if (llm.api_key) body.api_key = llm.api_key;
      try {
        await safeApi("/api/llm-config", { method: "PUT", body });
        llm.saved = true; setTimeout(() => (llm.saved = false), 2000);
        await loadLlm();
      } catch (e) { llm.modelError = e.detail || e.message; }
    }

    async function loadDishes() { try { const { data } = await safeApi("/api/dishes"); dishes.value = data; } catch {} }
    async function loadIngredients() {
      try {
        const { data } = await safeApi("/api/ingredients");
        ingredientsText.value = (data.items || []).join(", ");
        Object.keys(quantities).forEach(k => delete quantities[k]);
        Object.assign(quantities, data.quantities || {});
        usedUp.value = data.used_up || [];
      } catch {}
    }
    async function loadProfile() {
      try {
        const { data } = await safeApi("/api/profile");
        profile.cuisine_prefs = data.cuisine_prefs; profile.spicy = data.spicy; profile.dislikes = data.dislikes;
        profileText.cuisine = data.cuisine_prefs.join(", "); profileText.dislikes = data.dislikes.join(", ");
      } catch {}
    }
    async function loadHistory() { history.value = null; try { const { data } = await safeApi("/api/history"); history.value = data; } catch {} }

    async function recommend(meal) {
      loading.value = true; Object.keys(result).forEach(k => delete result[k]);
      try { const { data } = await safeApi("/api/recommend", { method: "POST", body: { meal_type: meal } }); Object.assign(result, data); result._meal = meal; }
      catch {} finally { loading.value = false; }
    }

    async function addDishes() {
      addError.value = "";
      const names = splitItems(newDishName.value);
      if (!names.length) return;
      addBusy.value = true;
      const dupes = [];
      try {
        for (let i = 0; i < names.length; i++) {
          addProgress.value = `添加中 (${i+1}/${names.length})`;
          const { status } = await safeApi("/api/dishes", { method: "POST", body: { name: names[i] } });
          if (status === 409) dupes.push(names[i]);
        }
        newDishName.value = "";
        if (dupes.length) addError.value = `已在库中：${dupes.join("、")}`;
        await loadDishes();
      } catch (e) { addError.value = e.detail || e.message; }
      finally { addBusy.value = false; addProgress.value = ""; }
    }

    async function removeDish(d) {
      if (!confirm(`删除「${d.name}」？做过记录也会一起删。`)) return;
      try { await safeApi(`/api/dishes/${d.id}`, { method: "DELETE" }); await loadDishes(); } catch {}
    }

    function startEdit(d) {
      editingId.value = d.id; editError.value = "";
      editForm.name = d.name; editForm.cuisine = d.cuisine || "";
      editForm.ingredients = (d.main_ingredients || []).join(", ");
      editForm.spicy = d.spicy; editForm.category = d.category || "";
      editForm.meals = [...(d.suitable_meals || [])];
      editForm.recipe = d.recipe || "";
    }
    function toggleRecipeView(id) { recipeViewId.value = recipeViewId.value === id ? null : id; }
    async function genEditRecipe(d) {
      editError.value = "";
      try {
        const { data } = await safeApi(`/api/dishes/${d.id}/generate-recipe`, { method: "POST", body: {} });
        if (data.error) editError.value = data.error;
        editForm.recipe = data.recipe || editForm.recipe;
      } catch (e) { editError.value = e.detail || "生成失败"; }
    }
    async function saveEdit(d) {
      editError.value = "";
      const body = {
        name: editForm.name.trim(), category: editForm.category.trim() || null,
        cuisine: editForm.cuisine.trim() || null, main_ingredients: splitItems(editForm.ingredients),
        spicy: Number(editForm.spicy) || 0, tags: d.tags || [],
        suitable_meals: editForm.meals, recipe: editForm.recipe,
      };
      try { const { status } = await safeApi(`/api/dishes/${d.id}`, { method: "PUT", body });
        if (status === 409) { editError.value = "已有同名菜"; return; }
        editingId.value = null; await loadDishes();
      } catch (e) { editError.value = e.detail || e.message; }
    }

    function currentIngredients() { return splitItems(ingredientsText.value); }
    function hasIngredient(ing) { return currentIngredients().includes(ing); }
    function toggleChip(ing) {
      const items = currentIngredients();
      const idx = items.indexOf(ing);
      if (idx >= 0) items.splice(idx, 1); else items.push(ing);
      ingredientsText.value = items.join(", ");
    }
    function setQty(name, val) { quantities[name] = val; }
    function isUsedUp(name) { return usedUp.value.includes(name); }
    function toggleUsedUp(name) {
      const i = usedUp.value.indexOf(name);
      if (i >= 0) usedUp.value.splice(i, 1); else usedUp.value.push(name);
    }
    async function saveIngredients() {
      const items = currentIngredients();
      const itemSet = new Set(items);
      const qty = {}; for (const n of items) if (quantities[n]) qty[n] = quantities[n];
      const used = usedUp.value.filter(n => itemSet.has(n));
      try { await safeApi("/api/ingredients", { method: "PUT", body: { items, quantities: qty, used_up: used } });
        usedUp.value = used;
        ingredientsSaved.value = true; setTimeout(() => (ingredientsSaved.value = false), 2000);
      } catch {}
    }

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
      if (!planning.selected.length) { planning.aiWarning = "先勾选几道菜"; return; }
      const merged = Array.from(new Set([...currentIngredients(), ...shoppingList()]));
      try {
        await safeApi("/api/ingredients", { method: "PUT", body: { items: merged } });
        ingredientsText.value = merged.join(", ");
        planning.open = false;
        ingredientsSaved.value = true; setTimeout(() => (ingredientsSaved.value = false), 2000);
      } catch (e) { planning.aiWarning = e.detail || "保存失败，请重试"; }
    }

    async function saveProfile() {
      const cuisine_prefs = splitItems(profileText.cuisine);
      const dislikes = splitItems(profileText.dislikes);
      try { await safeApi("/api/profile", { method: "PUT", body: { cuisine_prefs, spicy: profile.spicy, dislikes } });
        profile.cuisine_prefs = cuisine_prefs; profile.dislikes = dislikes;
        profileSaved.value = true; setTimeout(() => (profileSaved.value = false), 2000);
      } catch {}
    }

    async function logKnown(d) { try { await safeApi("/api/log", { method: "POST", body: { dish_id: d.id, meal_type: result._meal } }); await recommend(result._meal); } catch {} }
    async function logNew(d, addToLibrary) {
      try {
        const { data } = await safeApi("/api/log", { method: "POST", body: { gemini_dish: d, meal_type: result._meal, add_to_library: addToLibrary } });
        if (addToLibrary) { await loadDishes(); openRecipeModal(data.dish_id, d.name); }
        await recommend(result._meal);
      } catch {}
    }

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

    onMounted(async () => {
      const token = localStorage.getItem(TOKEN_KEY), username = localStorage.getItem(USERNAME_KEY);
      if (!token || !username) { view.value = "login"; return; }
      auth.token = token; auth.username = username;
      try {
        const { data } = await api("/api/profile");
        profile.cuisine_prefs = data.cuisine_prefs; profile.spicy = data.spicy; profile.dislikes = data.dislikes;
        profileText.cuisine = data.cuisine_prefs.join(", "); profileText.dislikes = data.dislikes.join(", ");
        await loadDishes(); await loadIngredients(); view.value = "main";
      } catch { logout(); }
    });

    return {
      view, auth, authMode, authForm, authError, authBusy, submitAuth, logout,
      tab, go, loading, result,
      dishes, newDishName, addError, addBusy, addProgress, addDishes, removeDish,
      editingId, editForm, editError, startEdit, saveEdit, mealOpts, toggleEditMeal, mealsShort,
      recipeViewId, toggleRecipeView, genEditRecipe,
      recipeModal, fetchRecipe, openRecipeModal, closeRecipeModal,
      ingredientsText, ingredientsSaved, saveIngredients, commonIngredients, hasIngredient, toggleChip,
      quantities, usedUp, setQty, isUsedUp, toggleUsedUp,
      planning, openPlanner, togglePlanPick, shoppingList, addPlanToIngredients,
      history, loadHistory,
      profile, profileText, profileSaved, saveProfile,
      llm, pickPreset, fetchModels, saveLlm,
      recommend, logKnown, logNew, mealLabel, fmtDate,
    };
  },
}).mount("#app");
