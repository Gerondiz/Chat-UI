import asyncio
from playwright.async_api import async_playwright

FRONTEND = "http://localhost:5173"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--window-size=1280,720"])
        page = await browser.new_page(viewport={"width": 1280, "height": 720})

        page.on("console", lambda msg: print(f"  [LOG] {msg.text}"))
        page.on("pageerror", lambda err: print(f"  [ERR] {err}"))

        # 1. Open page
        print("=" * 50)
        print("1. ЗАГРУЗКА СТРАНИЦЫ")
        print("=" * 50)
        await page.goto(FRONTEND, wait_until="load", timeout=15000)
        await asyncio.sleep(4)

        dot = page.locator(".status-dot").first
        cls = await dot.get_attribute("class")
        status = await page.locator(".status-text").text_content()
        print(f"   Статус: {'🟢' if 'online' in cls else '🔴'} {status}")
        await page.screenshot(path="/tmp/test_01_loaded.png")

        # 2. Check provider and model
        print("\n" + "=" * 50)
        print("2. ПРОВАЙДЕР И МОДЕЛЬ")
        print("=" * 50)
        prov = page.locator(".header-select").first
        val = await prov.input_value()
        print(f"   Выбран провайдер: {val}")
        opts = await prov.locator("option").all_text_contents()
        print(f"   Доступные провайдеры: {opts}")

        models = page.locator(".header-select").nth(1)
        if await models.count():
            mval = await models.input_value()
            mopts = await models.locator("option").all_text_contents()
            print(f"   Выбрана модель: {mval}")
            print(f"   Доступные модели: {mopts}")

        # 3. Switch model
        print("\n" + "=" * 50)
        print("3. ПЕРЕКЛЮЧЕНИЕ МОДЕЛИ")
        print("=" * 50)
        if await models.count():
            mopts = await models.locator("option").all_text_contents()
            if len(mopts) > 1:
                target = mopts[1]
                await models.select_option(target)
                await asyncio.sleep(2)
                print(f"   Переключено на: {target}")
                cls = await dot.get_attribute("class")
                status = await page.locator(".status-text").text_content()
                print(f"   Статус: {'🟢' if 'online' in cls else '🔴'} {status}")
                await page.screenshot(path="/tmp/test_03_switch_model.png")
                # Switch back
                await models.select_option(mopts[0])
                await asyncio.sleep(1)

        # 4. Switch provider to OpenAI
        print("\n" + "=" * 50)
        print("4. ПЕРЕКЛЮЧЕНИЕ ПРОВАЙДЕРА НА LMSTUDIO")
        print("=" * 50)
        await prov.select_option("openai")
        await asyncio.sleep(3)
        cls = await dot.get_attribute("class")
        status = await page.locator(".status-text").text_content()
        print(f"   Статус: {'🟢' if 'online' in cls else '🔴'} {status}")
        await page.screenshot(path="/tmp/test_04_openai.png")
        models2 = page.locator(".header-select").nth(1)
        if await models2.count():
            mopts = await models2.locator("option").all_text_contents()
            print(f"   Модели LMStudio: {mopts}")

        # 5. Switch back to Ollama
        print("\n" + "=" * 50)
        print("5. ВОЗВРАТ НА OLLAMA")
        print("=" * 50)
        await prov.select_option("ollama")
        await asyncio.sleep(3)
        cls = await dot.get_attribute("class")
        status = await page.locator(".status-text").text_content()
        print(f"   Статус: {'🟢' if 'online' in cls else '🔴'} {status}")
        await page.screenshot(path="/tmp/test_05_ollama_back.png")

        # 6. Send message and get streaming response
        print("\n" + "=" * 50)
        print("6. ОТПРАВКА СООБЩЕНИЯ И СТРИМИНГ")
        print("=" * 50)
        textarea = page.locator(".input-row textarea")
        await textarea.fill("Привет! Ответь на русском одним предложением о себе.")
        await page.wait_for_timeout(500)

        send = page.locator(".send-btn")
        await send.click()
        print("   Отправлено, ждём ответ...")

        try:
            await page.wait_for_function(
                """() => {
                    const msgs = document.querySelectorAll('.message.assistant .msg-bubble');
                    if (msgs.length === 0) return false;
                    const text = msgs[msgs.length - 1].textContent;
                    return text.length > 20;
                }""",
                timeout=60000,
            )
            resp = await page.locator(".message.assistant .msg-bubble").last.text_content()
            print(f"   Получен ответ ({len(resp)} символов):")
            print(f"   {resp[:150]}...")
            await page.screenshot(path="/tmp/test_06_response.png")
        except Exception as e:
            print(f"   Таймаут ожидания ответа: {e}")
            await page.screenshot(path="/tmp/test_06_timeout.png")
            # Try non-streaming as fallback
            print("   Пробуем нестриминг...")
            import httpx
            r = httpx.post("http://localhost:8000/api/chat", json={
                "messages": [{"role": "user", "content": "Привет одним словом"}],
                "stream": False,
            }, timeout=30)
            print(f"   Backend говорит: {r.json()['content'][:100]}")

        print("\n" + "=" * 50)
        print("ТЕСТ ЗАВЕРШЁН")
        print("=" * 50)
        await page.wait_for_timeout(5000)
        await browser.close()


asyncio.run(main())
