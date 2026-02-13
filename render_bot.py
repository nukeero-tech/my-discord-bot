import discord
from discord.ext import commands
from PIL import Image, ImageFilter, ImageDraw, ImageFont
import io
import os
import asyncio
from flask import Flask
from threading import Thread
from concurrent.futures import ThreadPoolExecutor

# --- 1. Webサーバー設定 ---
app = Flask('')
@app.route('/')
def home(): return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

def keep_alive():
    Thread(target=run).start()

# 作業員を1人に絞る（同時に何個も処理させてメモリパンクするのを防ぐ）
executor = ThreadPoolExecutor(max_workers=1)

# --- 2. Bot設定 ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# 同期的な画像処理
def make_image_sync(raw_data, viewer_id=None):
    with Image.open(io.BytesIO(raw_data)) as img:
        img = img.convert("RGBA")
        if viewer_id:
            # 刻印処理（ボタン押下時）
            txt = Image.new("RGBA", img.size, (255, 255, 255, 0))
            d = ImageDraw.Draw(txt)
            fs = max(20, img.width // 25)
            try: font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", fs)
            except: font = ImageFont.load_default()
            text = f"ID: {viewer_id}"
            bbox = d.textbbox((0, 0), text, font=font)
            x, y = img.width - (bbox[2]-bbox[0]) - 20, img.height - (bbox[3]-bbox[1]) - 20
            for o in [(-1,-1), (-1,1), (1,-1), (1,1)]:
                d.text((x + o[0], y + o[1]), text, font=font, fill=(0, 0, 0, 150))
            d.text((x, y), text, font=font, fill=(255, 255, 255, 150))
            img = Image.alpha_composite(img, txt)
        else:
            # ぼかし（初期表示時）：さらに軽量化のため半径を少し下げる
            img = img.filter(ImageFilter.GaussianBlur(radius=10))
        
        out = io.BytesIO()
        img.save(out, format="PNG")
        out.seek(0)
        return out

class BulkImageView(discord.ui.View):
    def __init__(self, images):
        super().__init__(timeout=None)
        self.images = images

    @discord.ui.button(label="IDを刻印して表示", style=discord.ButtonStyle.green)
    async def show_all(self, interaction, button):
        # 1. 最初に最優先でこれだけやる！
        try:
            await interaction.response.defer(ephemeral=True)
        except: return # 3秒間に合わなかったら諦める

        loop = asyncio.get_event_loop()
        files = []
        for i, data in enumerate(self.images):
            # 重い処理はexecutorに投げて、Botの心臓を止めない
            p = await loop.run_in_executor(executor, make_image_sync, data, interaction.user.id)
            files.append(discord.File(p, filename=f"res_{i}.png"))
        
        await interaction.followup.send(files=files, ephemeral=True)

@bot.event
async def on_message(message):
    if message.author == bot.user or not message.attachments: return
    
    raw_imgs = []
    blur_files = []
    loop = asyncio.get_event_loop()

    for att in message.attachments:
        if any(att.filename.lower().endswith(e) for e in ['.png', '.jpg', '.jpeg']):
            data = await att.read()
            raw_imgs.append(data)
            # ぼかし処理
            b = await loop.run_in_executor(executor, make_image_sync, data)
            blur_files.append(discord.File(b, filename=f"blur_{att.filename}"))

    if blur_files:
        await message.channel.send(content="処理完了", files=blur_files, view=BulkImageView(raw_imgs))

# --- 実行 ---
keep_alive()
token = os.getenv("DISCORD_BOT_TOKEN")
if token: bot.run(token)

