const { createApp, reactive, ref, onMounted } = Vue;

const TOKEN_KEY = "rr_token";
const USERNAME_KEY = "rr_username";

async function api(path, opts = {}) {
  const token = localStorage.getItem(TOKEN_KEY);
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(path, {
    ...opts,
    headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 401) {
    const err = new Error("Unauthorized");
    err.status = 401;
    throw err;
  }
  if (!res.ok && res.status !== 409) {
    const err = new Error(`HTTP ${res.status}`);
    err.status = res.status;
    try { err.detail = (await res.json()).detail; } catch {}
    throw err;
  }
  return { status: res.status, data: res.status === 204 ? null : await res.json() };
}

createApp({
  setup() {
    // --- auth state ---
    const view = ref("loading");
    const auth = reactive({ token: null, username: null });
    const authMode = ref("login");
    const authForm = reactive({ username: "", password: "", invite_code: "" });
    const authError = ref("");
    const authBusy = ref(false);

    // --- main app state ---
    const tab = ref("home");
    const loading = ref(false);
    const result = reactive({});

    const dishes = ref([]);
    const newDishName = ref("");
    const addError = ref("");

    const ingredientsText = ref("");
    const ingredientsSaved = ref(false);

    const profile = reactive({ cuisine_prefs: [], spicy: 2, dislikes: [] });
    const profileText = reactive({ cuisine: "", dislikes: "" });
    const profileSaved = ref(false);

    function mealLabel(m) {
      return { breakfast: "早餐", lunch: "午餐", dinner: "晚餐" }[m];
    }

    function setLoggedIn(token, username) {
      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem(USERNAME_KEY, username);
      auth.token = token;
      auth.username = username;
      view.value = "main";
      loadDishes();
      loadIngredients();
      loadProfile();
    }

    function logout() {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USERNAME_KEY);
      auth.token = null;
      auth.username = null;
      view.value = "login";
      authForm.username = "";
      authForm.password = "";
      authForm.invite_code = "";
    }

    function handle401() {
      logout();
    }

    async function submitAuth() {
      authBusy.value = true;
      authError.value = "";
      try {
        const url = authMode.value === "login" ? "/api/auth/login" : "/api/auth/register";
        const body = authMode.value === "login"
          ? { username: authForm.username, password: authForm.password }
          : { username: authForm.username, password: authForm.password, invite_code: authForm.invite_code };
        const { status, data } = await api(url, { method: "POST", body });
        if (status !== 200 || !data || !data.token) {
          authError.value = (data && data.detail) || "注册或登录失败";
          return;
        }
        setLoggedIn(data.token, data.username);
      } catch (e) {
        if (e.status === 401) {
          authError.value = "用户名或密码错误";
        } else if (e.detail) {
          authError.value = e.detail;
        } else {
          authError.value = e.message;
        }
      } finally {
        authBusy.value = false;
      }
    }

    async function safeApi(...args) {
      try {
        return await api(...args);
      } catch (e) {
        if (e.status === 401) {
          handle401();
        }
        throw e;
      }
    }

    async function loadDishes() {
      try {
        const { data } = await safeApi("/api/dishes");
        dishes.value = data;
      } catch (e) {}
    }

    async function loadIngredients() {
      try {
        const { data } = await safeApi("/api/ingredients");
        ingredientsText.value = (data.items || []).join(", ");
      } catch (e) {}
    }

    async function loadProfile() {
      try {
        const { data } = await safeApi("/api/profile");
        profile.cuisine_prefs = data.cuisine_prefs;
        profile.spicy = data.spicy;
        profile.dislikes = data.dislikes;
        profileText.cuisine = data.cuisine_prefs.join(", ");
        profileText.dislikes = data.dislikes.join(", ");
      } catch (e) {}
    }

    async function recommend(meal) {
      loading.value = true;
      Object.keys(result).forEach((k) => delete result[k]);
      try {
        const { data } = await safeApi("/api/recommend", { method: "POST", body: { meal_type: meal } });
        Object.assign(result, data);
        result._meal = meal;
      } catch (e) {} finally {
        loading.value = false;
      }
    }

    async function addDish() {
      addError.value = "";
      try {
        const { status } = await safeApi("/api/dishes", { method: "POST", body: { name: newDishName.value.trim() } });
        if (status === 409) {
          addError.value = "已在库中";
          return;
        }
        newDishName.value = "";
        await loadDishes();
      } catch (e) {
        addError.value = e.message;
      }
    }

    async function saveIngredients() {
      const items = ingredientsText.value
        .split(/[,，]/)
        .map((s) => s.trim())
        .filter(Boolean);
      try {
        await safeApi("/api/ingredients", { method: "PUT", body: { items } });
        ingredientsSaved.value = true;
        setTimeout(() => (ingredientsSaved.value = false), 2000);
      } catch (e) {}
    }

    async function saveProfile() {
      const cuisine_prefs = profileText.cuisine.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
      const dislikes = profileText.dislikes.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
      try {
        await safeApi("/api/profile", {
          method: "PUT",
          body: { cuisine_prefs, spicy: profile.spicy, dislikes },
        });
        profile.cuisine_prefs = cuisine_prefs;
        profile.dislikes = dislikes;
        profileSaved.value = true;
        setTimeout(() => (profileSaved.value = false), 2000);
      } catch (e) {}
    }

    async function logKnown(d) {
      try {
        await safeApi("/api/log", { method: "POST", body: { dish_id: d.id, meal_type: result._meal } });
        await recommend(result._meal);
      } catch (e) {}
    }

    async function logNew(d, addToLibrary) {
      const body = {
        gemini_dish: d,
        meal_type: result._meal,
        add_to_library: addToLibrary,
      };
      try {
        await safeApi("/api/log", { method: "POST", body });
        if (addToLibrary) await loadDishes();
        await recommend(result._meal);
      } catch (e) {}
    }

    onMounted(async () => {
      const token = localStorage.getItem(TOKEN_KEY);
      const username = localStorage.getItem(USERNAME_KEY);
      if (!token || !username) {
        view.value = "login";
        return;
      }
      auth.token = token;
      auth.username = username;
      try {
        // Validate token by hitting /api/profile
        const { data } = await api("/api/profile");
        profile.cuisine_prefs = data.cuisine_prefs;
        profile.spicy = data.spicy;
        profile.dislikes = data.dislikes;
        profileText.cuisine = data.cuisine_prefs.join(", ");
        profileText.dislikes = data.dislikes.join(", ");
        await loadDishes();
        await loadIngredients();
        view.value = "main";
      } catch (e) {
        logout();
      }
    });

    return {
      view, auth, authMode, authForm, authError, authBusy, submitAuth, logout,
      tab, loading, result,
      dishes, newDishName, addError, addDish,
      ingredientsText, ingredientsSaved, saveIngredients,
      profile, profileText, profileSaved, saveProfile,
      recommend, logKnown, logNew, mealLabel,
    };
  },
}).mount("#app");
