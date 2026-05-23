const { createApp, reactive, ref, onMounted } = Vue;

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok && res.status !== 409) {
    throw new Error(`HTTP ${res.status}`);
  }
  return { status: res.status, data: res.status === 204 ? null : await res.json() };
}

createApp({
  setup() {
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

    async function loadDishes() {
      const { data } = await api("/api/dishes");
      dishes.value = data;
    }

    async function loadIngredients() {
      const { data } = await api("/api/ingredients");
      ingredientsText.value = (data.items || []).join(", ");
    }

    async function loadProfile() {
      const { data } = await api("/api/profile");
      profile.cuisine_prefs = data.cuisine_prefs;
      profile.spicy = data.spicy;
      profile.dislikes = data.dislikes;
      profileText.cuisine = data.cuisine_prefs.join(", ");
      profileText.dislikes = data.dislikes.join(", ");
    }

    async function recommend(meal) {
      loading.value = true;
      Object.keys(result).forEach((k) => delete result[k]);
      try {
        const { data } = await api("/api/recommend", { method: "POST", body: { meal_type: meal } });
        Object.assign(result, data);
        result._meal = meal;
      } finally {
        loading.value = false;
      }
    }

    async function addDish() {
      addError.value = "";
      try {
        const { status } = await api("/api/dishes", { method: "POST", body: { name: newDishName.value.trim() } });
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
      await api("/api/ingredients", { method: "PUT", body: { items } });
      ingredientsSaved.value = true;
      setTimeout(() => (ingredientsSaved.value = false), 2000);
    }

    async function saveProfile() {
      const cuisine_prefs = profileText.cuisine.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
      const dislikes = profileText.dislikes.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
      await api("/api/profile", {
        method: "PUT",
        body: { cuisine_prefs, spicy: profile.spicy, dislikes },
      });
      profile.cuisine_prefs = cuisine_prefs;
      profile.dislikes = dislikes;
      profileSaved.value = true;
      setTimeout(() => (profileSaved.value = false), 2000);
    }

    async function logKnown(d) {
      await api("/api/log", { method: "POST", body: { dish_id: d.id, meal_type: result._meal } });
      await recommend(result._meal);
    }

    async function logNew(d, addToLibrary) {
      const body = {
        gemini_dish: d,
        meal_type: result._meal,
        add_to_library: addToLibrary,
      };
      await api("/api/log", { method: "POST", body });
      if (addToLibrary) await loadDishes();
      await recommend(result._meal);
    }

    onMounted(() => {
      loadDishes();
      loadIngredients();
      loadProfile();
    });

    return {
      tab, loading, result,
      dishes, newDishName, addError, addDish,
      ingredientsText, ingredientsSaved, saveIngredients,
      profile, profileText, profileSaved, saveProfile,
      recommend, logKnown, logNew, mealLabel,
    };
  },
}).mount("#app");
