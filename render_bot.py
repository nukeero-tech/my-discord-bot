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

# 作業員を1人に制限
executor = ThreadPoolExecutor(max_workers=1)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- 画像処理（ID刻印・同期処理） ---
def process_img_sync(data, vid=None):
    with Image.open(io.BytesIO(data)) as img:
        img = img.convert("RGBA")
        if vid:
            # 刻印モード
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
            # ぼかしモード
            img = img.filter(ImageFilter.GaussianBlur(radius=10))
        
        out = io.BytesIO()
        img.save(out, format="PNG")
        out.seek(0)
        return out

class BulkView(discord.ui.View):
    def __init__(self, original_msg_id, channel_id):
        super().__init__(timeout=None)
        self.msg_id = original_msg_id
        self.channel_id = channel_id

    @discord.ui.button(label="IDを刻印して表示", style=discord.ButtonStyle.green)
    async def show(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            # 元の画像があるメッセージを再取得
            channel = bot.get_channel(self.channel_id)
            message = await channel.fetch_message(self.msg_id)
            
            files = []
            loop = asyncio.get_running_loop()
            for i, att in enumerate(message.attachments):
                # ぼかしではない「元画像」が添付されているメッセージから読み取る
                if "blur_" not in att.filename:
                    data = await att.read()
                    processed = await loop.run_in_executor(executor, process_img_sync, data, interaction.user.id)
                    files.append(discord.File(processed, filename=f"decoded_{i}.png"))
            
            await interaction.followup.send(files=files, ephemeral=True)
        except Exception as e:
            await interaction.followup.send("エラー：元の画像が見つかりませんでした。", ephemeral=True)

@bot.event
async def on_message(message):
    if message.author == bot.user or not message.attachments: return

    # --- 設定 ---
    STORAGE_CHANNEL_ID = 1471824733652910101  # ←表示させたい別チャンネルのID

    # 画像アタッチメントのみ抽出
    valid_atts = [a for a in message.attachments if any(a.filename.lower().endswith(e) for e in ['.png', '.jpg', '.jpeg'])]
    if not valid_atts: return

    storage_channel = bot.get_channel(STORAGE_CHANNEL_ID)
    if not storage_channel:
        storage_channel = await bot.fetch_channel(STORAGE_CHANNEL_ID)

    # 1. まず元画像を保管チャンネルに転送（これは隠しログ用）
    orig_files = [await a.to_file() for a in valid_atts]
    stored_msg = await storage_channel.send(f"送信者: {message.author} (ID: {message.author.id}) の元画像", files=orig_files)

    # 2. ぼかし画像を作成
    loop = asyncio.get_running_loop()
    blur_files = []
    for att in valid_atts:
        data = await att.read()
        b_data = await loop.run_in_executor(executor, process_img_sync, data)
        blur_files.append(discord.File(b_data, filename=f"blur_{att.filename}"))

    # 3. 保管チャンネルに「ぼかし画像」と「ボタン」を出す
    await storage_channel.send(
        content=f"【新規依頼】送信者: {message.author.mention} が画像を投稿しました。",
        files=blur_files,
        view=BulkView(stored_msg.id, STORAGE_CHANNEL_ID)
    )

    # メインチャンネル側には受付完了だけ出す（スッキリ！）
    await message.channel.send(f"✅ 画像を受付。{storage_channel.mention} を確認してください。", delete_after=10)

bot.run(os.getenv("DISCORD_BOT_TOKEN"))
