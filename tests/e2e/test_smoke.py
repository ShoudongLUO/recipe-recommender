"""Browser smoke test: load every tab and fail on any uncaught JS / console error.

Catches the class of bug where a template references something not exported from
the Vue setup() (e.g. a missing `currentIngredients`), which throws during render
and blanks the page.
"""
from __future__ import annotations

NAV_LABELS = ["推荐", "会的菜", "本周食材", "历史", "口味画像", "设置"]


def test_all_tabs_load_without_console_errors(page, live_server):
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))

    def _on_console(msg):
        # Ignore network resource 404s (e.g. favicon); we care about JS errors.
        if msg.type == "error" and "Failed to load resource" not in msg.text:
            errors.append(f"console.error: {msg.text}")

    page.on("console", _on_console)

    base_url = live_server["base_url"]
    # Inject the auth token before any app script runs so the SPA boots into the
    # main view without going through the login form.
    page.add_init_script(
        "localStorage.setItem('rr_token', {token!r});"
        "localStorage.setItem('rr_username', {username!r});".format(
            token=live_server["token"], username=live_server["username"]
        )
    )

    page.goto(base_url + "/", wait_until="networkidle")
    page.wait_for_selector("nav button", timeout=10000)

    for label in NAV_LABELS:
        page.click(f"nav button:has-text('{label}')")
        page.wait_for_timeout(400)  # let the section render + any API call settle

    assert errors == [], "Console/page errors detected:\n" + "\n".join(errors)
