import discord
from discord.ext import commands
from PIL import Image, ImageFilter, ImageDraw, ImageFont
import io
import os
from flask import Flask
from threading import Thread

# --- 1. Render居眠り防止用のWebサーバー設定 ---
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

# --- 2. Botの基本設定 ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.event
async def on_message(message):
    # Bot自身の発言、または添付ファイルがないメッセージは無視
    if message.author == bot.user or not message.attachments:
        return
    
    # 全添付ファイルをループ処理
    for attachment in message.attachments:
        if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg']):
            raw_data = await attachment.read()
            
            # --- ぼかし画像作成 (PNG維持) ---
            with Image.open(io.BytesIO(raw_data)) as img:
                img = img.convert("RGBA") # PNGの透明度を扱えるように変換
                blurred = img.filter(ImageFilter.GaussianBlur(radius=15))
                out_blur = io.BytesIO()
                blurred.save(out_blur, format="PNG")
                out_blur.seek(0)

            # --- ボタンと刻印処理のクラス ---
            class ImageView(discord.ui.View):
                def __init__(self, original_data):
                    super().__init__(timeout=None)
                    self.original_data = original_data

                @discord.ui.button(label="IDを刻印して表示", style=discord.ButtonStyle.green)
                async def show_image(self, interaction: discord.Interaction, button: discord.ui.Button):
                    viewer_id = interaction.user.id
                    
                    with Image.open(io.BytesIO(self.original_data)) as img:
                        img = img.convert("RGBA")
                        txt_layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
                        draw = ImageDraw.Draw(txt_layer)
                        
                        # 画像サイズに合わせたフォントサイズ調整
                        font_size = max(20, img.width // 25)
                        try:
                            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
                        except:
                            font = ImageFont.load_default()

                        text = f"ID: {viewer_id}"
                        bbox = draw.textbbox((0, 0), text, font=font)
                        x = img.width - (bbox[2]-bbox[0]) - 20
                        y = img.height - (bbox[3]-bbox[1]) - 20
                        
                        # ID刻印（半透明）
                        alpha_val = 150
                        # 縁取り
                        for offset in [(-1,-1), (-1,1), (1,-1), (1,1)]:
                            draw.text((x + offset[0], y + offset[1]), text, font=font, fill=(0, 0, 0, alpha_val))
                        # 本体
                        draw.text((x, y), text, font=font, fill=(255, 255, 255, alpha_val))
                        
                        combined = Image.alpha_composite(img, txt_layer)
                        out_final = io.BytesIO()
                        combined.save(out_final, format="PNG")
                        out_final.seek(0)

                    await interaction.response.send_message(
                        content=f"あなたのID（{viewer_id}）を刻印しました。", 
                        file=discord.File(out_final, "decoded.png"), 
                        ephemeral=True
                    )

            # 1枚ごとにメッセージを送信
            await message.channel.send(
                content=f"画像「{attachment.filename}」を処理しました"
                    )
