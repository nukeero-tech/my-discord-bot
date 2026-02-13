import discord
from discord.ext import commands
from PIL import Image, ImageFilter, ImageDraw, ImageFont
import io
import os
import asyncio
from flask import Flask
from threading import Thread
from concurrent.futures import ThreadPoolExecutor

# --- Webサーバー ---
app = Flask('')
@app.route('/')
def home(): return "OK"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
Thread(target=run).start()

# CPU負荷を抑えるために作業員を1人に固定
executor = ThreadPoolExecutor(max_workers=1)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# 重い画像処理を完全に分離
def process_sync(data, vid=None):
    with Image.open(io.BytesIO(data)) as img:
        img = img.convert("RGBA")
        if vid:
            # ID刻印
            txt = Image.new("RGBA", img.size, (255, 255, 255, 0))
            d = ImageDraw.Draw(txt)
            fs = max(20, img.width // 25)
            try: font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", fs)
            except: font = ImageFont.load_default()
            msg = f"ID: {vid}"
            bbox = d.textbbox((0, 0), msg, font=font)
            x, y = img.width - (bbox[2]-bbox[0]) - 20, img.height - (bbox[3]-bbox[1]) - 20
            for o in [(-1,-1), (-1,1), (1,-1), (1,1)]:
                d.text((x + o[0], y + o[1]), msg, font=font, fill=(0, 0, 0, 150))
            d.text((x, y), msg, font=font, fill=(255, 255, 255, 150))
            img = Image.alpha_composite(img, txt)
        else:
            # ぼかし（軽量化のため半径を5に）
            img = img.filter(ImageFilter.GaussianBlur(radius=5))
        
        out = io.BytesIO()
        img.save(out, format="PNG")
        out.seek(0)
        return out

class BulkView(discord.ui.View):
    def __init__(self, imgs):
        super().__init__(timeout=None)
        self.imgs = imgs

    @discord.ui.button(label="IDを刻印して表示", style=discord.ButtonStyle.green)
    async def show(self, interaction, button):
        # 何よりも先に、0.1秒でも早くこれを実行する
        try:
            await interaction.response.defer(ephemeral=True)
        except:
            return 

        loop = asyncio.get_event_loop()
        files = []
        for i, d in enumerate(self.imgs):
            # 1枚ずつ順番に、CPUが空くのを待って処理
            p = await loop.run_in_executor(executor, process_sync, d, interaction.user.id)
            files.append(discord.File(p, filename=f"res_{i}.png"))
        
        await interaction.followup.send(files=files, ephemeral=True)

@bot.event
async def on_message(message):
    if message.author == bot.user or not message.attachments: return
    
    # 画像が含まれているかだけチェック
    attachments = [a for a in message.attachments if any(a.filename.lower().endswith(e) for e in ['.png', '.jpg', '.jpeg'])]
    if not attachments: return

    # 【新戦略】まず「処理中...」とメッセージだけ先に送って、ボタンを有効化する
    sent_msg = await message.channel.send("画像を読み込み中... 少々お待ちください。")
    
    raw_imgs = []
    blur_files = []
    loop = asyncio.get_event_loop()

    for att in attachments:
        data = await att.read()
        raw_imgs.append(data)
        # ぼかし処理を実行（1列に並んで）
        b = await loop.run_in_executor(executor, process_sync, data)
        blur_files.append(discord.File(b, filename=f"blur_{att.filename}"))

    # ぼかしが終わったら、元の「読み込み中」メッセージを書き換える
    await sent_msg.edit(content=f"{len(blur_files)} 枚の処理が完了しました。", attachments=blur_files, view=BulkView(raw_imgs))

bot.run(os.getenv("DISCORD_BOT_TOKEN"))
