import asyncio
import httpx
from playwright.async_api import async_playwright

FRONTEND_URL = "http://localhost:5173"


async def warmup_model():
    print("   Прогрев модели (первый запрос может быть медленным)...")
    try:
        r = httpx.post("http://localhost:8000/api/chat", json={
            "messages": [{"role": "user", "content": "Привет"}],
            "mode": "chat",
            "stream": False,
        }, timeout=180)
        print(f"   Прогрев: {r.status_code}, {len(r.json().get('content', ''))} символов")
    except Exception as e:
        print(f"   Прогрев не удался: {e}")


async def main():
    await warmup_model()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--window-size=1280,720"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()

        page.on("console", lambda msg: print(f"  [console] {msg.text}"))
        page.on("pageerror", lambda err: print(f"  [pageerr] {err}"))

        print("=" * 50)
        print("1. ЗАГРУЗКА СТРАНИЦЫ")
        print("=" * 50)
        await page.goto(FRONTEND_URL, wait_until="load", timeout=15000)
        await page.wait_for_timeout(3000)
        await page.screenshot(path="/tmp/test_agent_01_loaded.png")
        print("   Скриншот: /tmp/test_agent_01_loaded.png")

        status_dot = page.locator(".status-dot").first
        dot_class = await status_dot.get_attribute("class")
        status_text = await page.locator(".status-text").text_content()
        print(f"   Статус: {'🟢' if 'online' in dot_class else '🔴'} {status_text}")

        provider_select = page.locator(".header-select").first
        current_provider = await provider_select.input_value()
        print(f"   Провайдер: {current_provider}")

        print("\n" + "=" * 50)
        print("2. ПЕРЕКЛЮЧЕНИЕ В РЕЖИМ АГЕНТ")
        print("=" * 50)

        agent_btn = page.locator(".mode-btn", has_text="Агент")
        await agent_btn.click()
        await page.wait_for_timeout(500)

        is_active = await agent_btn.get_attribute("class")
        print(f"   Кнопка Агент: {'🟢 active' if 'active' in (is_active or '') else '🔴'}")
        await page.screenshot(path="/tmp/test_agent_02_mode_agent.png")
        print("   Скриншот: /tmp/test_agent_02_mode_agent.png")

        print("\n" + "=" * 50)
        print("3. ОТПРАВКА ЗАПРОСА О ПОГОДЕ")
        print("=" * 50)

        textarea = page.locator(".input-row textarea")
        await textarea.fill("какая погода завтра в Пензе?")
        await page.wait_for_timeout(300)

        send_btn = page.locator(".send-btn")
        await send_btn.click()
        print("   Отправлено, ожидание потокового ответа...")

        print("\n" + "=" * 50)
        print("4. ОЖИДАНИЕ СТРИМИНГА С РАЗМЫШЛЕНИЯМИ")
        print("=" * 50)

        try:
            await page.wait_for_function(
                """() => {
                    const thinkingBlocks = document.querySelectorAll('.thinking-block');
                    if (thinkingBlocks.length > 0) return true;
                    const bubbles = document.querySelectorAll('.message.assistant .msg-bubble');
                    if (bubbles.length === 0) return false;
                    const text = bubbles[bubbles.length - 1].textContent;
                    return text.length > 20;
                }""",
                timeout=300000,
            )
            print("   Ответ получен!")

            has_thinking = await page.locator(".thinking-block").count()
            print(f"   Блок размышлений: {'✅ есть' if has_thinking else '❌ нет'}")

            await page.wait_for_timeout(2000)
            await page.screenshot(path="/tmp/test_agent_03_response.png")
            print("   Скриншот: /tmp/test_agent_03_response.png")

            response_text = await page.locator(".message.assistant .msg-bubble").last.text_content()
            print(f"   Ответ ({len(response_text)} символов):")
            print(f"   {response_text[:300]}...")

            if has_thinking:
                thinking_text = await page.locator(".thinking-content").last.text_content()
                print(f"\n   Размышления ({len(thinking_text)} символов):")
                print(f"   {thinking_text[:300]}...")

        except Exception as e:
            print(f"   Таймаут ожидания ответа: {e}")
            await page.screenshot(path="/tmp/test_agent_timeout.png")
            print("   Скриншот (таймаут): /tmp/test_agent_timeout.png")

            try:
                r = httpx.post("http://localhost:8000/api/chat", json={
                    "messages": [{"role": "user", "content": "какая погода завтра в Пензе?"}],
                    "mode": "agent",
                    "stream": False,
                }, timeout=180)
                data = r.json()
                print(f"\n   Backend (agent): content={data.get('content', '')[:200]}")
                print(f"   Backend thinking: {data.get('thinking', '')[:200]}")
                print(f"   Backend sources: {data.get('sources', [])}")
            except Exception as be:
                print(f"   Backend error: {be}")

        print("\n" + "=" * 50)
        print("ТЕСТ ЗАВЕРШЁН")
        print("=" * 50)

        await page.wait_for_timeout(5000)
        await browser.close()


asyncio.run(main())