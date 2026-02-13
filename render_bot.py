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
def home():
    return "Bot is alive!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# 画像処理用の別枠を準備
executor = ThreadPoolExecutor(max_workers=3)

# --- 2. Bot設定 ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

# 画像処理（重い処理）を関数化
def process_image_sync(raw_data, viewer_id=None):
    with Image.open(io.BytesIO(raw_data)) as img:
        img = img.convert("RGBA")
        if viewer_id:
            # ID刻印モード
            txt_layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(txt_layer)
            font_size = max(20, img.width // 25)
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
            except:
                font = ImageFont.load_default()
            text = f"ID: {viewer_id}"
            bbox = draw.textbbox((0, 0), text, font=font)
            x, y = img.width - (bbox[2]-bbox[0]) - 20, img.height - (bbox[3]-bbox[1]) - 20
            alpha = 150
            for offset in [(-1,-1), (-1,1), (1,-1), (1,1)]:
                draw.text((x + offset[0], y + offset[1]), text, font=font, fill=(0, 0, 0, alpha))
            draw.text((x, y), text, font=font, fill=(255, 255, 255, alpha))
            img = Image.alpha_composite(img, txt_layer)
        else:
            # ぼかしモード
            img = img.filter(ImageFilter.GaussianBlur(radius=15))
        
        out = io.BytesIO()
        img.save(out, format="PNG")
        out.seek(0)
        return out

class BulkImageView(discord.ui.View):
    def __init__(self, all_images_data):
        super().__init__(timeout=None)
        self.all_images_data = all_images_data

    @discord.ui.button(label="すべての画像にIDを刻印して表示", style=discord.ButtonStyle.green)
    async def show_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 3秒ルールを回避
        await interaction.response.defer(ephemeral=True)
        
        loop = asyncio.get_event_loop()
        files = []
        # 画像1枚ずつ別スレッドで処理して目詰まりを防ぐ
        for i, data in enumerate(self.all_images_data):
            processed_io = await loop.run_in_executor(executor, process_image_sync, data, interaction.user.id)
            files.append(discord.File(processed_io, filename=f"decoded_{i}.png"))
        
        await interaction.followup.send(
            content=f"合計 {len(files)} 枚にID（{interaction.user.id}）を刻印しました。",
            files=files,
            ephemeral=True
        )

@bot.event
async def on_message(message):
    if message.author == bot.user or not message.attachments:
        return
    
    valid_images_data = []
    blur_files = []
    loop = asyncio.get_event_loop()
    
    for attachment in message.attachments:
        if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg']):
            raw_data = await attachment.read()
            valid_images_data.append(raw_data)
            
            # ぼかし処理を別スレッドで実行
            out_blur = await loop.run_in_executor(executor, process_image_sync, raw_data)
            blur_files.append(discord.File(out_blur, filename=f"blur_{attachment.filename}"))

    if blur_files:
        await message.channel.send(
            content=f"計 {len(blur_files)} 枚を処理しました（ぼかし済）",
            files=blur_files,
            view=BulkImageView(valid_images_data)
        )

# --- 実行 ---
keep_alive()
token = os.getenv("DISCORD_BOT_TOKEN")
if token:
    bot.run(token)
else:
    print("Error: DISCORD_BOT_TOKEN is not set.")
