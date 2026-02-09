import discord
from discord.ext import commands
from PIL import Image, ImageFilter, ImageDraw, ImageFont
import io
import os
from flask import Flask
from threading import Thread

# --- Renderの居眠り防止用 (Flask) ---
app = Flask('')
@app.route('/')
def home():
    return "Bot is alive!"

def run():
    # Renderは環境変数 PORT を指定してくるのでそれを使う
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()
# ----------------------------------

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user or not message.attachments:
        return
    
    attachment = message.attachments[0]
    if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg']):
        raw_data = await attachment.read()
        
        # 1. ぼかし画像作成
        with Image.open(io.BytesIO(raw_data)) as img:
            blurred = img.filter(ImageFilter.GaussianBlur(radius=15))
            out_blur = io.BytesIO()
            blurred.save(out_blur, format="PNG")
            out_blur.seek(0)

        view = discord.ui.View()
        button = discord.ui.Button(label="IDを刻印して表示", style=discord.ButtonStyle.green)

        async def callback(interaction):
            viewer_id = interaction.user.id
            with Image.open(io.BytesIO(raw_data)) as img:
                img = img.convert("RGBA")
                txt_layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
                draw = ImageDraw.Draw(txt_layer)
                
                # --- フォントの読み込み（WindowsとLinux両対応） ---
                font_size = 40
                try:
                    # Render(Linux)の標準的なフォントパス
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
                except:
                    try:
                        # Windows用
                        font = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", font_size)
                    except:
                        # どちらもダメなら標準フォント
                        font = ImageFont.load_default()

                text = f"ID: {viewer_id}"
                bbox = draw.textbbox((0, 0), text, font=font)
                x = img.width - (bbox[2]-bbox[0]) - 30
                y = img.height - (bbox[3]-bbox[1]) - 30
                
                # 透明度 (0-255)
                alpha_val = 128
                # 縁取り
                for offset in [(-1,-1), (-1,1), (1,-1), (1,1)]:
                    draw.text((x + offset[0], y + offset[1]), text, font=font, fill=(0, 0, 0, alpha_val))
                # 本文
                draw.text((x, y), text, font=font, fill=(255, 255, 255, alpha_val))
                
                combined = Image.alpha_composite(img, txt_layer)
                out_final = io.BytesIO()
                combined.save(out_final, format="PNG")
                out_final.seek(0)

            # 削除ボタン
            delete_view = discord.ui.View()
            delete_button = discord.ui.Button(label="見終わったので消す", style=discord.ButtonStyle.danger)
            async def d_callback(it):
                await it.message.delete()
            delete_button.callback = d_callback
            delete_view.add_item(delete_button)

            await interaction.response.send_message(
                content=f"あなたのID（{viewer_id}）を刻印しました。", 
                file=discord.File(out_final, "res.png"), 
                view=delete_view, 
                ephemeral=True
            )

        button.callback = callback
        view.add_item(button)
        await message.channel.send("画像が投稿されました（ぼかし済）", file=discord.File(out_blur, "blur.png"), view=view)

# 居眠り防止用Webサーバー起動
keep_alive()

# トークンはRenderの「Environment Variables」から読み込む
token = os.getenv("DISCORD_BOT_TOKEN")
if token:
    bot.run(token)
else:
    print("エラー: DISCORD_BOT_TOKEN が設定されていません。")