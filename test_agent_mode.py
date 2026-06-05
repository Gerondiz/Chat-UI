import asyncio
import httpx
from playwright.async_api import async_playwright

FRONTEND = "http://localhost:5173"
BACKEND = "http://localhost:8000"


async def backend_cfg(cfg: dict):
    r = httpx.put(f"{BACKEND}/api/provider/config", json=cfg, timeout=10)
    r.raise_for_status()


async def backend_chat(query: str, mode: str = "agent"):
    r = httpx.post(f"{BACKEND}/api/chat", json={
        "messages": [{"role": "user", "content": query}],
        "mode": mode, "stream": False, "max_tokens": 100,
    }, timeout=120)
    return r.json()


async def backend_stream(query: str, mode: str = "agent"):
    """Test streaming via direct HTTP (no browser). Returns (success, response_text)."""
    r = httpx.post(f"{BACKEND}/api/chat/stream", json={
        "messages": [{"role": "user", "content": query}],
        "mode": mode, "stream": True, "max_tokens": 50,
    }, timeout=90)
    full = ""
    thinking = ""
    done_data = {}
    for line in r.text.split("\n"):
        line = line.strip()
        if not line.startswith("data: "):
            continue
        import json
        data = json.loads(line[6:])
        if data.get("done"):
            done_data = data
            break
        full += data.get("token", "")
    done_full = done_data.get("full", "")
    done_thinking = done_data.get("thinking", "")
    metrics = done_data.get("metrics", {})
    return {
        "full": done_full,
        "thinking": done_thinking,
        "metrics": metrics,
    }


async def wait_for_frontend(page, timeout_ms: int = 15000):
    await page.goto(FRONTEND, wait_until="load", timeout=timeout_ms)
    await page.wait_for_timeout(4000)
    dot = page.locator(".status-dot").first
    cls = await dot.get_attribute("class")
    status = await page.locator(".status-text").text_content()
    online = 'online' in cls
    print(f"   Статус: {'🟢' if online else '🔴'} {status}", flush=True)
    return online


async def main():
    print("=" * 60, flush=True)
    print("ТЕСТ: AGENT MODE", flush=True)
    print("=" * 60, flush=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--window-size=1400,800"]
        )
        page = await browser.new_page(viewport={"width": 1400, "height": 800})
        page.on("pageerror", lambda err: print(f"  [ERR] {err}", flush=True))

        # ===== 1. OLLAMA =====
        print("\n1. OLLAMA", flush=True)
        print("=" * 60, flush=True)
        await backend_cfg({"name":"ollama","chat_model":"gemma4:e4b","base_url":"http://localhost:11434","api_key":"","embedding_model":""})

        print("\n   a) Backend non-streaming chat (chat mode)", flush=True)
        resp = await backend_chat("Say hello in 2 words", "chat")
        print(f"   Ответ: {resp.get('content','')[:80]}", flush=True)
        print(f"   Thinking: {repr(resp.get('thinking','')[:60])}", flush=True)
        assert "hello" in resp.get("content","").lower() or "привет" in resp.get("content","").lower()
        print("   ✅ chat mode OK", flush=True)

        print("\n   b) Backend non-streaming agent mode", flush=True)
        resp = await backend_chat("какая погода завтра в Пензе?", "agent")
        print(f"   Ответ: {resp.get('content','')[:80]}", flush=True)
        print(f"   Thinking: {repr(resp.get('thinking','')[:60])}", flush=True)
        print(f"   Sources: {resp.get('sources', [])}", flush=True)
        assert len(resp.get("content","")) > 0
        print("   ✅ agent mode OK", flush=True)

        print("\n   c) Backend streaming agent mode", flush=True)
        result = await backend_stream("какая погода завтра в Пензе?", "agent")
        print(f"   Full: {result['full'][:80]}", flush=True)
        print(f"   Thinking: {result['thinking'][:60]}", flush=True)
        m = result.get("metrics", {})
        print(f"   Metrics: tokens={m.get('tokens')} output_tokens={m.get('output_tokens')} tps={m.get('tokens_per_sec')} reasoning={m.get('reasoning_tokens')}", flush=True)
        assert len(result.get("full","")) > 0 or len(result.get("thinking","")) > 0
        print("   ✅ streaming agent OK", flush=True)

        print("\n   d) Frontend — загрузка страницы", flush=True)
        await wait_for_frontend(page)
        val = await page.locator(".header-select").first.input_value()
        print(f"   Провайдер: {val}", flush=True)
        await page.screenshot(path="/tmp/agent_ollama_loaded.png")

        # режимы
        for mode_label in ["Чат", "+RAG", "Агент"]:
            btn = page.locator(".mode-btn", has_text=mode_label)
            await btn.click()
            await page.wait_for_timeout(300)
            active = 'active' in (await btn.get_attribute("class") or "")
            print(f"   Режим {mode_label}: {'✅' if active else '❌'}", flush=True)
            assert active
        await page.screenshot(path="/tmp/agent_ollama_modes.png")
        print("   ✅ переключение режимов OK", flush=True)

        # ===== 2. LMSTUDIO (OPENAI) =====
        print("\n2. LMSTUDIO (OPENAI) — remote", flush=True)
        print("=" * 60, flush=True)
        await backend_cfg({"name":"openai","chat_model":"google/gemma-4-e4b","base_url":"http://26.55.98.240:1234/v1","api_key":"","embedding_model":""})

        # Проверка доступности
        bs = httpx.get(f"{BACKEND}/api/provider/status", timeout=15).json()
        print(f"   Статус: name={bs['name']} online={bs['online']} model={bs.get('chat_model','')}", flush=True)
        if not bs.get("online"):
            print("   ⚠ Пропускаем — LM Studio offline", flush=True)
        else:
            print("\n   a) Backend non-streaming chat (chat mode)", flush=True)
            resp = await backend_chat("Say hello in 2 words", "chat")
            print(f"   Ответ: {resp.get('content','')[:80]}", flush=True)
            print(f"   Thinking: {repr(resp.get('thinking','')[:60])}", flush=True)
            assert len(resp.get("content","")) > 0
            print("   ✅ chat mode OK", flush=True)

            print("\n   b) Backend non-streaming agent mode", flush=True)
            resp = await backend_chat("какая погода завтра в Москве?", "agent")
            print(f"   Ответ: {resp.get('content','')[:80]}", flush=True)
            print(f"   Thinking: {repr(resp.get('thinking','')[:60])}", flush=True)
            assert len(resp.get("content","")) > 0
            print("   ✅ agent mode OK", flush=True)

            print("\n   c) Backend streaming agent mode", flush=True)
            result = await backend_stream("какая погода завтра в Москве?", "agent")
            print(f"   Full: {result['full'][:80]}", flush=True)
            m = result.get("metrics", {})
            print(f"   Metrics: tokens={m.get('tokens')} output_tokens={m.get('output_tokens')} tps={m.get('tokens_per_sec')} reasoning={m.get('reasoning_tokens')}", flush=True)
            assert len(result.get("full","")) > 0
            print("   ✅ streaming agent OK", flush=True)

        # ===== 3. Возврат на Ollama =====
        print("\n3. ВОЗВРАТ НА OLLAMA", flush=True)
        print("=" * 60, flush=True)
        await backend_cfg({"name":"ollama","chat_model":"gemma4:e4b","base_url":"http://localhost:11434","api_key":"","embedding_model":""})
        await wait_for_frontend(page)
        await page.screenshot(path="/tmp/agent_final.png")
        print("   ✅ финал OK", flush=True)

        print(f"\n{'=' * 60}", flush=True)
        print("ВСЕ ТЕСТЫ ПРОЙДЕНЫ ✅", flush=True)
        print(f"{'=' * 60}", flush=True)
        await page.wait_for_timeout(5000)
        await browser.close()


asyncio.run(main())
