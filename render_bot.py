import discord
from discord.ext import commands
from PIL import Image, ImageFilter, ImageDraw, ImageFont
import io, os, asyncio
from flask import Flask
from threading import Thread
from concurrent.futures import ThreadPoolExecutor

# --- Webサーバー (居眠り防止) ---
app = Flask('')
@app.route('/')
def home(): return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

Thread(target=run).start()

# 処理の並列数を2に設定
executor = ThreadPoolExecutor(max_workers=2)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- 画像加工（刻印）の裏方処理 ---
def apply_watermark_sync(data, vid):
    with Image.open(io.BytesIO(data)) as img:
        img = img.convert("RGBA")
        txt = Image.new("RGBA", img.size, (255, 255, 255, 0))
        d = ImageDraw.Draw(txt)
        fs = max(20, img.width // 25)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", fs)
        except:
            font = ImageFont.load_default()
        
        msg = f"ID: {vid}"
        bbox = d.textbbox((0, 0), msg, font=font)
        x, y = img.width - (bbox[2]-bbox[0]) - 20, img.height - (bbox[3]-bbox[1]) - 20
        
        for o in [(-1,-1), (-1,1), (1,-1), (1,1)]:
            d.text((x + o[0], y + o[1]), msg, font=font, fill=(0, 0, 0, 150))
        d.text((x, y), msg, font=font, fill=(255, 255, 255, 150))
        
        img = Image.alpha_composite(img, txt)
        out = io.BytesIO()
        img.save(out, format="PNG")
        out.seek(0)
        return out

# --- ボタンが押された時の動作 ---
class BulkView(discord.ui.View):
    def __init__(self, all_urls):
        super().__init__(timeout=None)
        self.all_urls = all_urls

    @discord.ui.button(label="すべての画像にIDを刻印して表示", style=discord.ButtonStyle.green)
    async def show(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ボタンを押した瞬間に、その人だけに「読み込み中」と出す（3秒ルール対策）
        await interaction.response.send_message(f"⌛ 合計 {len(self.all_urls)} 枚を処理しています。しばらくお待ちください...", ephemeral=True)

        loop = asyncio.get_running_loop()
        processed_files = []
        
        try:
            for i, url in enumerate(self.all_urls):
                # Discordから画像を再取得
                async with bot.http._HTTPClient__session.get(url) as resp:
                    if resp.status != 200: continue
                    img_data = await resp.read()
                
                # 刻印処理を順番に実行
                output = await loop.run_in_executor(executor, apply_watermark_sync, img_data, interaction.user.id)
                processed_files.append(discord.File(output, filename=f"image_{i}.png"))
            
            if processed_files:
                # 終わったら、最初の「読み込み中」というメッセージを画像付きに更新する
                await interaction.edit_original_response(content="✅ 処理が完了しました。", attachments=processed_files)
            else:
                await interaction.edit_original_response(content="❌ 画像の取得に失敗しました。")
        
        except Exception as e:
            print(f"Error in show_all: {e}")
            await interaction.edit_original_response(content="⚠️ 処理中にエラーが発生しました。")

# --- メッセージを受け取った時の動作 ---
@bot.event
async def on_message(message):
    if message.author == bot.user or not message.attachments:
        return

    # 画像アタッチメントをすべてリスト化
    valid_attachments = [a for a in message.attachments if any(a.filename.lower().endswith(e) for e in ['.png', '.jpg', '.jpeg'])]
    if not valid_attachments:
        return

    # 全画像のURLを保持
    all_urls = [a.url for a in valid_attachments]
    
    # 【プレビュー作成】最初の1枚目だけを「ぼかし」て表示
    first_att = valid_attachments[0]
    first_data = await first_att.read()
    
    with Image.open(io.BytesIO(first_data)) as img:
        # ぼかし処理
        img = img.convert("RGBA").filter(ImageFilter.GaussianBlur(radius=10))
        out_blur = io.BytesIO()
        img.save(out_blur, format="PNG")
        out_blur.seek(0)
        preview_file = discord.File(out_blur, filename=f"preview_{first_att.filename}")

    # メインチャンネルには「1枚目のぼかし」と「全枚数URLを持ったボタン」を送る
    await message.channel.send(
        content=f"計 {len(all_urls)} 枚の画像を確認しました。",
        file=preview_file,
        view=BulkView(all_urls)
    )

bot.run(os.getenv("DISCORD_BOT_TOKEN"))

