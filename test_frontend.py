import asyncio
from playwright.async_api import async_playwright

FRONTEND_URL = "http://localhost:5173"
BACKEND_URL = "http://localhost:8000"

async def main():
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

        print("1. Opening page...")
        await page.goto(FRONTEND_URL, wait_until="load", timeout=15000)
        await page.wait_for_timeout(3000)
        await page.screenshot(path="/tmp/test_01_loaded.png")
        print("   Screenshot: /tmp/test_01_loaded.png")

        status_dot = page.locator(".status-dot").first
        dot_class = await status_dot.get_attribute("class")
        print(f"   Status dot class: {dot_class}")

        status_text = await page.locator(".status-text").text_content()
        print(f"   Status text: {status_text}")

        provider_select = page.locator(".header-select").first
        current_provider = await provider_select.input_value()
        print(f"   Selected provider: {current_provider}")

        provider_options = await provider_select.locator("option").all_text_contents()
        print(f"   Available providers: {provider_options}")

        model_select = page.locator(".header-select").nth(1)
        model_exists = await model_select.count()
        if model_exists:
            current_model = await model_select.input_value()
            model_options = await model_select.locator("option").all_text_contents()
            print(f"   Selected model: {current_model}")
            print(f"   Available models: {model_options}")
        else:
            print("   No model selector found")

        print("\n2. Switching to OpenAI provider...")
        await provider_select.select_option("openai")
        await page.wait_for_timeout(3000)
        await page.screenshot(path="/tmp/test_02_switched_openai.png")
        print("   Screenshot: /tmp/test_02_switched_openai.png")

        dot_class = await status_dot.get_attribute("class")
        status_text = await page.locator(".status-text").text_content()
        print(f"   Status dot: {dot_class}")
        print(f"   Status text: {status_text}")

        model_select = page.locator(".header-select").nth(1)
        model_exists = await model_select.count()
        if model_exists:
            model_options = await model_select.locator("option").all_text_contents()
            print(f"   Available models after switch: {model_options}")
        else:
            print("   No model selector after switch")

        print("\n3. Switching back to Ollama...")
        await provider_select.select_option("ollama")
        await page.wait_for_timeout(3000)
        await page.screenshot(path="/tmp/test_03_back_ollama.png")
        print("   Screenshot: /tmp/test_03_back_ollama.png")

        dot_class = await status_dot.get_attribute("class")
        print(f"   Status dot: {dot_class}")

        model_select = page.locator(".header-select").nth(1)
        model_exists = await model_select.count()
        if model_exists:
            model_options = await model_select.locator("option").all_text_contents()
            model_select_inner = model_select
            if len(model_options) > 1:
                await model_select_inner.select_option(model_options[1])
                print(f"   Selected model: {model_options[1]}")
                await page.wait_for_timeout(1000)

        status_text = await page.locator(".status-text").text_content()
        print(f"   Final status: {status_text}")

        print("\n4. Sending chat message...")
        textarea = page.locator(".input-row textarea")
        await textarea.fill("Привет! Расскажи коротко о себе. Ответь на русском.")
        await page.wait_for_timeout(500)

        send_btn = page.locator(".send-btn")
        await send_btn.click()

        print("   Waiting for streaming response...")
        try:
            await page.wait_for_function(
                "() => document.querySelectorAll('.message.assistant').length > 0",
                timeout=30000
            )
            await page.wait_for_timeout(5000)
            await page.screenshot(path="/tmp/test_04_response.png")
            print("   Screenshot: /tmp/test_04_response.png")

            response_text = await page.locator(".message.assistant .msg-bubble").last.text_content()
            print(f"   Response preview: {response_text[:200]}...")
        except Exception as e:
            print(f"   Timeout waiting for response: {e}")
            await page.screenshot(path="/tmp/test_04_timeout.png")
            print("   Screenshot (timeout): /tmp/test_04_timeout.png")

        print("\n5. Checking final page state...")
        final_dot = await status_dot.get_attribute("class")
        print(f"   Final status dot: {final_dot}")
        final_status = await page.locator(".status-text").text_content()
        print(f"   Final status: {final_status}")

        await page.wait_for_timeout(3000)
        print("\nDone! Keeping browser open for 10s...")
        await page.wait_for_timeout(10000)

        await browser.close()

asyncio.run(main())
