import asyncio
import os
import shutil
from pathlib import Path
from playwright.async_api import async_playwright

FRONTEND_URL = "https://financial-research-studio-frontend-1055095577935.us-east1.run.app"
RECORD_DIR = Path("/config/Desktop/Session1/financial-research-studio/demo_recordings")

async def record_demo():
    if RECORD_DIR.exists():
        shutil.rmtree(RECORD_DIR)
    RECORD_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        print("Launching Chromium browser...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            record_video_dir=str(RECORD_DIR),
            record_video_size={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        print(f"Navigating to {FRONTEND_URL}...")
        await page.goto(FRONTEND_URL, wait_until="networkidle")
        await asyncio.sleep(3)

        # Prompt 1: Core feature - Compare company financials with currency conversion & A2UI cards
        prompt1 = "Compare ROE and Net Margin for JPMC and GS"
        print(f"Typing Prompt 1: '{prompt1}'...")
        await page.fill("#input", prompt1)
        await asyncio.sleep(1)
        await page.click("#form button.send-btn")

        print("Waiting for response to Prompt 1...")
        # Wait until send button is enabled again (indicating response finished)
        await page.wait_for_function("!document.querySelector('#form button.send-btn').disabled", timeout=60000)
        await asyncio.sleep(5)

        # Prompt 2: Richer prompt - Generate AI financial infographic tool call
        prompt2 = "Generate an AI financial infographic image summarizing JPMC Q4 performance"
        print(f"Typing Prompt 2: '{prompt2}'...")
        await page.fill("#input", prompt2)
        await asyncio.sleep(1)
        await page.click("#form button.send-btn")

        print("Waiting for response to Prompt 2...")
        await page.wait_for_function("!document.querySelector('#form button.send-btn').disabled", timeout=90000)
        await asyncio.sleep(8)

        video_path = await page.video.path()
        print(f"Recorded video saved to raw Playwright path: {video_path}")

        await context.close()
        await browser.close()

        # Export video to demo_agent.webm and artifact folder
        target_webm = Path("/config/Desktop/Session1/financial-research-studio/demo_agent.webm")
        if os.path.exists(video_path):
            shutil.copy(video_path, target_webm)
            print(f"Successfully exported demo recording to: {target_webm}")

            # Convert to mp4 using ffmpeg if available
            target_mp4 = Path("/config/Desktop/Session1/financial-research-studio/demo_agent.mp4")
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-i", str(target_webm), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(target_mp4)
                )
                await proc.wait()
                if target_mp4.exists():
                    print(f"Successfully converted to MP4: {target_mp4}")
            except Exception as e:
                print(f"FFmpeg conversion skipped/failed: {e}")

            return target_webm

if __name__ == "__main__":
    asyncio.run(record_demo())
