import discord
from discord.ext import commands
from PIL import Image, ImageFilter, ImageDraw, ImageFont
import io, os, asyncio
from flask import Flask
from threading import Thread
from concurrent.futures import ThreadPoolExecutor

# --- Webサーバー (Render居眠り防止) ---
app = Flask('')
@app.route('/')
def home(): return "OK"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
Thread(target=run).start()

# 作業員を1人に絞り、無料プランのCPUを使い切らないように調整
executor = ThreadPoolExecutor(max_workers=1)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- 画像処理（ID刻印） ---
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
        
        # 視認性向上のための縁取り
        for o in [(-1,-1), (-1,1), (1,-1), (1,1)]:
            d.text((x + o[0], y + o[1]), msg, font=font, fill=(0, 0, 0, 150))
        d.text((x, y), msg, font=font, fill=(255, 255, 255, 150))
        
        img = Image.alpha_composite(img, txt)
        out = io.BytesIO()
        img.save(out, format="PNG")
        out.seek(0)
        return out

class BulkView(discord.ui.View):
    def __init__(self, storage_channel_id, storage_message_id):
        super().__init__(timeout=None)
        self.channel_id = storage_channel_id
        self.message_id = storage_message_id

    @discord.ui.button(label="IDを刻印して表示", style=discord.ButtonStyle.green)
    async def show(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1. 3秒ルール回避（最優先）
        await interaction.response.defer(ephemeral=True)

        try:
            # 2. 別チャンネルのメッセージを再取得
            channel = bot.get_channel(self.channel_id)
            if not channel:
                channel = await bot.fetch_channel(self.channel_id)
            message = await channel.fetch_message(self.message_id)
            
            files = []
            loop = asyncio.get_running_loop()
            
            # 3. 添付ファイルを順番にダウンロードして加工
            for i, att in enumerate(message.attachments):
                if any(att.filename.lower().endswith(e) for e in ['.png', '.jpg', '.jpeg']):
                    data = await att.read()
                    processed = await loop.run_in_executor(executor, apply_watermark_sync, data, interaction.user.id)
                    files.append(discord.File(processed, filename=f"image_{i}.png"))
            
            if files:
                await interaction.followup.send(files=files, ephemeral=True)
            else:
                await interaction.followup.send("画像が見つかりませんでした。", ephemeral=True)
        
        except Exception as e:
            print(f"Error fetching from storage: {e}")
            await interaction.followup.send("データの取得に失敗しました。時間切れの可能性があります。", ephemeral=True)

@bot.event
async def on_message(message):
    if message.author == bot.user or not message.attachments: return

    # 画像があるか確認
    valid_atts = [a for a in message.attachments if any(a.filename.lower().endswith(e) for e in ['.png', '.jpg', '.jpeg'])]
    if not valid_atts: return

    # --- ストレージ用設定 ---
    # ここに「保存先」のチャンネルIDを入れてください
    STORAGE_CHANNEL_ID = 1471856587915268096  # ←書き換えてください！
    
    storage_channel = bot.get_channel(STORAGE_CHANNEL_ID)
    if storage_channel:
        # 1. 保存用チャンネルに画像を転送（バックアップ）
        files = [await a.to_file() for a in valid_atts]
        stored_msg = await storage_channel.send(f"User: {message.author.id}", files=files)
        
        # 2. 元のチャンネルに「ボタンだけ」送る
        # メモリには「チャンネルIDとメッセージID」という数字だけを渡すので超軽量！
        await message.channel.send(
            content=f"{len(valid_atts)} 枚の画像を保管しました。ボタンから刻印版を確認できます。",
            view=BulkView(STORAGE_CHANNEL_ID, stored_msg.id)
        )

bot.run(os.getenv("DISCORD_BOT_TOKEN"))
