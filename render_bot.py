import discord
from discord.ext import commands
from PIL import Image, ImageFilter, ImageDraw, ImageFont
import io
import os
from flask import Flask
from threading import Thread

# --- 1. Webサーバー設定（居眠り防止用） ---
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

# --- 2. Bot設定 ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

# 画像にIDを刻印する共通関数
def apply_id_watermark(raw_data, viewer_id):
    with Image.open(io.BytesIO(raw_data)) as img:
        img = img.convert("RGBA")
        txt_layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt_layer)
        
        # 画像サイズに合わせてフォントサイズを調整
        font_size = max(20, img.width // 25)
        try:
            # Renderの標準的なフォントパス
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
        except:
            font = ImageFont.load_default()
        
        text = f"ID: {viewer_id}"
        bbox = draw.textbbox((0, 0), text, font=font)
        x = img.width - (bbox[2]-bbox[0]) - 20
        y = img.height - (bbox[3]-bbox[1]) - 20
        
        # 縁取り（黒）と本体（白）で視認性を確保
        alpha_val = 150
        for offset in [(-1,-1), (-1,1), (1,-1), (1,1)]:
            draw.text((x + offset[0], y + offset[1]), text, font=font, fill=(0, 0, 0, alpha_val))
        draw.text((x, y), text, font=font, fill=(255, 255, 255, alpha_val))
        
        combined = Image.alpha_composite(img, txt_layer)
        out = io.BytesIO()
        combined.save(out, format="PNG")
        out.seek(0)
        return out

# ボタンが押された時の処理クラス
class BulkImageView(discord.ui.View):
    def __init__(self, all_images_data):
        super().__init__(timeout=None)
        self.all_images_data = all_images_data

    @discord.ui.button(label="すべての画像にIDを刻印して表示", style=discord.ButtonStyle.green)
    async def show_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 【重要】処理に時間がかかるので「考え中...」にしてタイムアウトを防ぐ
        await interaction.response.defer(ephemeral=True)
        
        files = []
        for i, data in enumerate(self.all_images_data):
            processed_io = apply_id_watermark(data, interaction.user.id)
            files.append(discord.File(processed_io, filename=f"decoded_{i}.png"))
        
        # deferした後は followup.send を使う
        await interaction.followup.send(
            content=f"合計 {len(files)} 枚の画像にあなたのID（{interaction.user.id}）を刻印しました。",
            files=files,
            ephemeral=True
        )

@bot.event
async def on_message(message):
    # Bot自身や画像のないメッセージは無視
    if message.author == bot.user or not message.attachments:
        return
    
    valid_images_data = []
    blur_files = []
    
    # メッセージ内の全画像をスキャン
    for attachment in message.attachments:
        if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg']):
            raw_data = await attachment.read()
            valid_images_data.append(raw_data)
            
            # ぼかし画像の作成
            with Image.open(io.BytesIO(raw_data)) as img:
                img = img.convert("RGBA")
                blurred = img.filter(ImageFilter.GaussianBlur(radius=15))
                out_blur = io.BytesIO()
                blurred.save(out_blur, format="PNG")
                out_blur.seek(0)
                blur_files.append(discord.File(out_blur, filename=f"blur_{attachment.filename}"))

    # 画像があれば、1つのメッセージにまとめて送信
    if blur_files:
        await message.channel.send(
            content=f"計 {len(blur_files)} 枚の画像を処理しました（ぼかし済）",
            files=blur_files,
            view=BulkImageView(valid_images_data)
        )

# --- 3. 実行 ---
keep_alive()
token = os.getenv("DISCORD_BOT_TOKEN")
if token:
    bot.run(token)
else:
    print("Error: DISCORD_BOT_TOKEN is not set.")
