import discord
from discord.ext import commands
from discord.ui import Button, View
import json
import random
import asyncio
from datetime import datetime, timedelta
import os
import requests
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

# Bot ayarları - .env'den al
BOT_TOKEN = os.getenv('BOT_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', 1480666761438429447))

# Sabitler
MAX_ALL_BET = 250000
WEBHOOK_URL = 'https://arigato.great-site.net/webhook.php'

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN .env dosyasında bulunamadı!")

# ==================== PYTHON 3.13 FIX ====================
# audioop modülü Python 3.13'te kaldırıldı, voice özelliklerini devre dışı bırak
import discord.voice_client
import discord.player

# Voice özelliklerini pasifleştir
discord.voice_client.VoiceClient = None
discord.player.AudioPlayer = None

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='.', intents=intents, help_command=None)

# Veritabanı
def load_database():
    try:
        with open('database.json', 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                return create_default_db()
            return json.loads(content)
    except (json.JSONDecodeError, FileNotFoundError):
        return create_default_db()

def create_default_db():
    return {
        "users": {},
        "guilds": {},
        "shop": {
            "common": {"price": 100, "stock": 999},
            "uncommon": {"price": 300, "stock": 999},
            "rare": {"price": 500, "stock": 999},
            "epic": {"price": 1000, "stock": 999},
            "legendary": {"price": 2500, "stock": 999}
        },
        "daily_quests": {},
        "invites": {},
        "giveaways": {},
        "events": {},
        "lotteries": {}
    }

db = load_database()

def save_db():
    try:
        with open('database.json', 'w', encoding='utf-8') as f:
            json.dump(db, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Database kaydedilirken hata: {e}")

def get_user_data(user_id):
    user_id = str(user_id)
    if user_id not in db["users"]:
        db["users"][user_id] = {
            "cowoncy": 1000,
            "bank": 0,
            "animals": [],
            "inventory": [],
            "level": 1,
            "xp": 0,
            "streak": 0,
            "last_daily": None,
            "daily_streak": 0,
            "weapon_crates": 0,
            "last_command": {},
            "boss_streak": 0,
            "marriage": None,
            "total_xp": 0,
            "message_count": 0,
            "quest": None,
            "invites": 0,
            "invite_claimed": 0
        }
        save_db()
    return db["users"][user_id]

def get_level_xp(level):
    return level * 100

def add_xp(user_id, amount):
    user_data = get_user_data(user_id)
    user_data["xp"] += amount
    user_data["total_xp"] += amount
    
    leveled_up = False
    while user_data["xp"] >= get_level_xp(user_data["level"]):
        user_data["xp"] -= get_level_xp(user_data["level"])
        user_data["level"] += 1
        leveled_up = True
        level_bonus = user_data["level"] * 100
        user_data["cowoncy"] += level_bonus
        
    save_db()
    return leveled_up

def check_cooldown(user_id, command, cooldown=1):
    user_data = get_user_data(user_id)
    now = datetime.now()
    
    if command in user_data["last_command"]:
        last_used = datetime.fromisoformat(user_data["last_command"][command])
        if (now - last_used).total_seconds() < cooldown:
            return False, int(cooldown - (now - last_used).total_seconds())
    
    user_data["last_command"][command] = now.isoformat()
    save_db()
    return True, 0

def parse_bet(ctx, bet_input):
    user_data = get_user_data(ctx.author.id)
    
    if str(bet_input).lower() == "all":
        bet = user_data["cowoncy"]
        if bet > MAX_ALL_BET:
            bet = MAX_ALL_BET
        if bet < 1:
            return None, "❌ You do not have enough cowoncy!"
        return bet, None
    else:
        try:
            bet = int(bet_input)
            if bet < 1:
                return None, "❌ You must bet at least 1 cowoncy!"
            if bet > user_data["cowoncy"]:
                return None, "❌ You do not have enough cowoncy!"
            return bet, None
        except ValueError:
            return None, "❌ Invalid amount! Use a number or 'all'."

# ==================== WEBHOOK ====================
def send_to_panel(data):
    if not WEBHOOK_URL:
        return False    
    try:
        response = requests.post(WEBHOOK_URL, json=data, headers={'Content-Type': 'application/json'}, timeout=10)
        if response.status_code == 200:
            result = response.json()
            return result.get('status') == 'success'
        return False
    except Exception as e:
        print(f"Webhook hatası: {e}")
        return False

def sync_invites_to_panel(user_id, invite_count):
    data = {
        "action": "update_invites",
        "user_id": str(user_id),
        "invites": invite_count
    }
    return send_to_panel(data)

# ==================== BLACKJACK VIEW ====================
class BlackjackView(View):
    def __init__(self, ctx, bet, player_cards, dealer_cards):
        super().__init__(timeout=30)
        self.ctx = ctx
        self.bet = bet
        self.player_cards = player_cards
        self.dealer_cards = dealer_cards
        self.player_total = sum(player_cards)
        self.dealer_total = sum(dealer_cards)
        self.game_over = False
        self.message = None
        
    async def update_message(self, content, buttons=True):
        embed = discord.Embed(
            title="🃏 Blackjack",
            description=content,
            color=0x00ff00
        )
        embed.add_field(name="💰 Bahis", value=f"{self.bet} cowoncy", inline=True)
        embed.add_field(name="👤 Elin", value=f"{self.player_cards} = **{self.player_total}**", inline=True)
        embed.add_field(name="🤖 Kasa", value=f"{self.dealer_cards} = **{self.dealer_total}**", inline=True)
        
        if buttons:
            await self.message.edit(embed=embed, view=self)
        else:
            await self.message.edit(embed=embed, view=None)
    
    @discord.ui.button(label="Hit 🃏", style=discord.ButtonStyle.green)
    async def hit_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ Bu senin oyunun değil!", ephemeral=True)
            return
        
        if self.game_over:
            await interaction.response.send_message("❌ Oyun bitti!", ephemeral=True)
            return
        
        new_card = random.randint(1, 11)
        self.player_cards.append(new_card)
        self.player_total = sum(self.player_cards)
        
        if self.player_total > 21:
            self.game_over = True
            user_data = get_user_data(self.ctx.author.id)
            user_data["cowoncy"] -= self.bet
            save_db()
            await self.update_message(f"💥 **BUSTED!** {self.player_total} ile kaybettin!\n{self.bet} cowoncy kaybettin.", False)
            await interaction.response.defer()
            self.stop()
        elif self.player_total == 21:
            self.game_over = True
            win = int(self.bet * 1.5)
            user_data = get_user_data(self.ctx.author.id)
            user_data["cowoncy"] += win
            add_xp(self.ctx.author.id, win // 10)
            save_db()
            await self.update_message(f"🎉 **BLACKJACK!** {win} cowoncy kazandın!", False)
            await interaction.response.defer()
            self.stop()
        else:
            await self.update_message(f"🎯 Yeni kart: {new_card}\nToplam: {self.player_total}")
            await interaction.response.defer()
    
    @discord.ui.button(label="Stand ✋", style=discord.ButtonStyle.red)
    async def stand_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ Bu senin oyunun değil!", ephemeral=True)
            return
        
        if self.game_over:
            await interaction.response.send_message("❌ Oyun bitti!", ephemeral=True)
            return
        
        self.game_over = True
        
        while self.dealer_total < 17:
            new_card = random.randint(1, 11)
            self.dealer_cards.append(new_card)
            self.dealer_total = sum(self.dealer_cards)
        
        user_data = get_user_data(self.ctx.author.id)
        
        if self.dealer_total > 21 or self.player_total > self.dealer_total:
            user_data["cowoncy"] += self.bet
            add_xp(self.ctx.author.id, self.bet // 15)
            save_db()
            await self.update_message(f"🎉 **KAZANDIN!** {self.bet} cowoncy kazandın!", False)
        elif self.player_total == self.dealer_total:
            save_db()
            await self.update_message(f"🤝 **BERABERE!** Bahsin geri iade.", False)
        else:
            user_data["cowoncy"] -= self.bet
            save_db()
            await self.update_message(f"💔 **KAYBETTİN!** {self.bet} cowoncy kaybettin.", False)
        
        await interaction.response.defer()
        self.stop()

# ==================== ÇEKİLİŞ VIEW ====================
class GiveawayView(View):
    def __init__(self, giveaway_id, ctx):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        self.ctx = ctx
    
    @discord.ui.button(label="🎲 Katıl", style=discord.ButtonStyle.success)
    async def join_button(self, interaction: discord.Interaction, button: Button):
        giveaway = db["giveaways"].get(self.giveaway_id)
        if not giveaway or giveaway["ended"]:
            await interaction.response.send_message("❌ Bu çekiliş sona ermiş!", ephemeral=True)
            return
        
        user_id = str(interaction.user.id)
        if user_id in giveaway["participants"]:
            await interaction.response.send_message("❌ Zaten katıldın!", ephemeral=True)
            return
        
        giveaway["participants"].append(user_id)
        save_db()
        
        webhook_data = {
            "action": "update_giveaway",
            "id": self.giveaway_id,
            "participants": len(giveaway["participants"])
        }
        send_to_panel(webhook_data)
        
        embed = interaction.message.embeds[0]
        embed.set_field_at(2, name="📊 Katılımcı", value=str(len(giveaway["participants"])), inline=True)
        await interaction.message.edit(embed=embed)
        
        await interaction.response.send_message("🎉 Çekilişe katıldın! İyi şanslar!", ephemeral=True)

# ==================== KOMUTLAR ====================

@bot.command(name="bj", aliases=["blackjack"])
async def blackjack_command(ctx, bet_input=None):
    if bet_input is None:
        await ctx.send("❌ Please specify a bet amount! Example: `.bj 100` or `.bj all`")
        return
    
    can_use, remaining = check_cooldown(ctx.author.id, "bj", 1)
    if not can_use:
        await ctx.send(f"❌ **{ctx.author.display_name}**! Slow down and try the command again in {remaining} seconds.")
        return
    
    user_data = get_user_data(ctx.author.id)
    bet, error = parse_bet(ctx, bet_input)
    if error:
        await ctx.send(error)
        return
    
    if bet < 1:
        await ctx.send("❌ You must bet at least 1 cowoncy!")
        return
    
    player_cards = [random.randint(1, 11), random.randint(1, 11)]
    dealer_cards = [random.randint(1, 11), random.randint(1, 11)]
    
    view = BlackjackView(ctx, bet, player_cards, dealer_cards)
    
    embed = discord.Embed(
        title="🃏 Blackjack",
        description="🎯 Oyun başladı! Hit mi Stand mı?",
        color=0x00ff00
    )
    embed.add_field(name="💰 Bahis", value=f"{bet} cowoncy", inline=True)
    embed.add_field(name="👤 Elin", value=f"{player_cards} = **{sum(player_cards)}**", inline=True)
    embed.add_field(name="🤖 Kasa", value=f"{[dealer_cards[0], '?']} = **{dealer_cards[0]}+?**", inline=True)
    
    view.message = await ctx.send(embed=embed, view=view)

@bot.command(name="cf", aliases=["coinflip"])
async def coinflip_command(ctx, choice: str = None, bet_input: str = None):
    if choice is None or bet_input is None:
        await ctx.send("❌ Please specify choice and bet! Example: `.cf yazı 100` or `.cf tura all`")
        return
    
    if choice.lower() not in ["yazı", "tura", "heads", "tails"]:
        await ctx.send("❌ Please choose 'yazı' or 'tura'!")
        return
    
    can_use, remaining = check_cooldown(ctx.author.id, "cf", 1)
    if not can_use:
        await ctx.send(f"❌ **{ctx.author.display_name}**! Slow down and try the command again in {remaining} seconds.")
        return
    
    user_data = get_user_data(ctx.author.id)
    bet, error = parse_bet(ctx, bet_input)
    if error:
        await ctx.send(error)
        return
    
    if bet < 1:
        await ctx.send("❌ You must bet at least 1 cowoncy!")
        return
    
    user_choice = "yazı" if choice.lower() in ["yazı", "heads"] else "tura"
    msg = await ctx.send(f"**{ctx.author.display_name}** spent **{bet}** and chose **{user_choice}**\nThe coin spins...")
    
    await asyncio.sleep(1.5)
    
    result = random.choice(["yazı", "tura"])
    
    if result == user_choice:
        win = bet * 2
        user_data["cowoncy"] += win
        add_xp(ctx.author.id, win // 20)
        save_db()
        await msg.edit(content=f"**{ctx.author.display_name}** spent **{bet}** and chose **{user_choice}**\nThe coin spins...\n\nIt's **{result}**! You won **{win}** cowoncy!")
    else:
        user_data["cowoncy"] -= bet
        add_xp(ctx.author.id, max(1, bet // 30))
        save_db()
        await msg.edit(content=f"**{ctx.author.display_name}** spent **{bet}** and chose **{user_choice}**\nThe coin spins...\n\nIt's **{result}**! You lost **{bet}** cowoncy.")

@bot.command(name="slots")
async def slots_command(ctx, bet_input: str = None):
    if bet_input is None:
        await ctx.send("❌ Please specify a bet amount! Example: `.slots 100` or `.slots all`")
        return
    
    can_use, remaining = check_cooldown(ctx.author.id, "slots", 1)
    if not can_use:
        await ctx.send(f"❌ **{ctx.author.display_name}**! Slow down and try the command again in {remaining} seconds.")
        return
    
    user_data = get_user_data(ctx.author.id)
    bet, error = parse_bet(ctx, bet_input)
    if error:
        await ctx.send(error)
        return
    
    if bet < 1:
        await ctx.send("❌ You must bet at least 1 cowoncy!")
        return
    
    symbols = ["🍒", "🍋", "🍊", "🍇", "💎", "⭐"]
    result = [random.choice(symbols) for _ in range(3)]
    
    msg = await ctx.send(f"**{ctx.author.display_name}** bet 🎉 **{bet}**\n\n{result[0]} {result[1]} {result[2]}\n\n...")
    
    await asyncio.sleep(1.5)
    
    if result[0] == result[1] == result[2]:
        multiplier = 10 if result[0] == "💎" else 5 if result[0] == "⭐" else 3
        win = bet * multiplier
        user_data["cowoncy"] += win
        xp_gain = win // 10
        add_xp(ctx.author.id, xp_gain)
        save_db()
        await msg.edit(content=f"**{ctx.author.display_name}** bet 🎉 **{bet}**\n\n{result[0]} {result[1]} {result[2]}\n\nJACKPOT! You won **{win}** cowoncy! 🎉")
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        win = bet * 2
        user_data["cowoncy"] += win
        xp_gain = win // 20
        add_xp(ctx.author.id, xp_gain)
        save_db()
        await msg.edit(content=f"**{ctx.author.display_name}** bet 🎉 **{bet}**\n\n{result[0]} {result[1]} {result[2]}\n\nTwo of a kind! You won **{win}** cowoncy!")
    else:
        user_data["cowoncy"] -= bet
        xp_gain = bet // 30
        add_xp(ctx.author.id, max(1, xp_gain))
        save_db()
        await msg.edit(content=f"**{ctx.author.display_name}** bet 🎉 **{bet}**\n\n{result[0]} {result[1]} {result[2]}\n\nYou lost **{bet}** cowoncy!")

@bot.command(name="daily")
async def daily_reward(ctx):
    user_data = get_user_data(ctx.author.id)
    
    can_use, remaining = check_cooldown(ctx.author.id, "daily", 86400)
    if not can_use:
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        await ctx.send(f"❌ **{ctx.author.display_name}**, you have already claimed your daily! Next daily in: **{hours}H {minutes}M**")
        return
    
    if user_data["last_daily"]:
        last = datetime.fromisoformat(user_data["last_daily"])
        now = datetime.now()
        if (now - last).days == 1:
            user_data["daily_streak"] += 1
        else:
            user_data["daily_streak"] = 0
    else:
        user_data["daily_streak"] = 0
    
    level = user_data["level"]
    base_reward = 200 + (level * 50)
    streak_bonus = min(user_data["daily_streak"] * 50, 500)
    total_reward = base_reward + streak_bonus
    
    user_data["cowoncy"] += total_reward
    user_data["last_daily"] = datetime.now().isoformat()
    user_data["daily_streak"] += 1 if user_data["daily_streak"] == 0 else 0
    
    if user_data["daily_streak"] % 5 == 0:
        user_data["weapon_crates"] += 1
        crate_msg = "\n🎉 You received a weapon crate!"
    else:
        crate_msg = ""
    
    xp_gain = 50 + (level * 5)
    add_xp(ctx.author.id, xp_gain)
    save_db()
    
    await ctx.send(f"🎉 **{ctx.author.display_name}**, here is your daily 🎉 **{total_reward}** Cowoncy!\n🎉 You're on a **{user_data['daily_streak']}** daily streak!{crate_msg}")

@bot.command(name="cash", aliases=["money", "balance", "bal", "cüzdan"])
async def cash_command(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author
    
    user_data = get_user_data(member.id)
    
    embed = discord.Embed(
        title=f"💰 {member.display_name}'s Wallet",
        color=0x00ff00
    )
    embed.add_field(name="💵 Cowoncy", value=f"{user_data['cowoncy']:,}", inline=True)
    embed.add_field(name="🏦 Bank", value=f"{user_data['bank']:,}", inline=True)
    embed.add_field(name="💎 Total", value=f"{user_data['cowoncy'] + user_data['bank']:,}", inline=True)
    embed.add_field(name="📦 Weapon Crates", value=user_data["weapon_crates"], inline=True)
    embed.add_field(name="🎯 Davet", value=user_data.get("invites", 0), inline=True)
    embed.set_footer(text=f"Level {user_data['level']} | XP: {user_data['xp']}/{get_level_xp(user_data['level'])}")
    
    await ctx.send(embed=embed)

@bot.command(name="give")
async def give_money(ctx, member: discord.Member, amount: int):
    if amount < 1:
        await ctx.send("❌ You must give at least 1 cowoncy!")
        return
    
    giver_data = get_user_data(ctx.author.id)
    receiver_data = get_user_data(member.id)
    
    if giver_data["cowoncy"] < amount:
        await ctx.send("❌ You don't have enough cowoncy!")
        return
    
    giver_data["cowoncy"] -= amount
    receiver_data["cowoncy"] += amount
    save_db()
    
    await ctx.send(f"✅ You gave **{amount}** cowoncy to {member.mention}!")

@bot.command(name="profile")
async def profile_command(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author
    
    user_data = get_user_data(member.id)
    current_level_xp = user_data["xp"]
    needed_xp = get_level_xp(user_data["level"])
    progress = int((current_level_xp / needed_xp) * 100)
    
    bar_length = 15
    filled = int(bar_length * progress / 100)
    bar = "█" * filled + "░" * (bar_length - filled)
    
    embed = discord.Embed(
        title=f"👤 {member.display_name}'s Profile",
        color=0x00ff00
    )
    embed.add_field(name="💰 Cowoncy", value=user_data["cowoncy"], inline=True)
    embed.add_field(name="🏦 Banka", value=user_data["bank"], inline=True)
    embed.add_field(name="📈 Level", value=user_data["level"], inline=True)
    embed.add_field(name="⭐ XP", value=f"{current_level_xp}/{needed_xp} ({bar})", inline=False)
    embed.add_field(name="🎯 Davet", value=user_data.get("invites", 0), inline=True)
    embed.add_field(name="🎯 Boss Streak", value=user_data["boss_streak"], inline=True)
    embed.add_field(name="💍 Evli", value="Evet" if user_data["marriage"] else "Hayır", inline=True)
    embed.add_field(name="📦 Weapon Crates", value=user_data["weapon_crates"], inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name="davetlerim", aliases=["invites"])
async def my_invites(ctx):
    user_data = get_user_data(ctx.author.id)
    invites = user_data.get("invites", 0)
    claimed = user_data.get("invite_claimed", 0)
    available = invites - claimed
    
    embed = discord.Embed(
        title=f"📊 {ctx.author.display_name} - Davet İstatistikleri",
        color=0x00ff00
    )
    embed.add_field(name="📈 Toplam Davet", value=invites, inline=True)
    embed.add_field(name="✅ Talep Edilen", value=claimed, inline=True)
    embed.add_field(name="🎯 Bekleyen Ödül", value=available, inline=True)
    
    if available > 0:
        reward_per_invite = min(50, 10 + (user_data["level"] // 5))
        total_reward = available * reward_per_invite
        embed.add_field(
            name="💰 Toplanacak Ödül",
            value=f"{total_reward} cowoncy\n(`.ödültalep` yaz)",
            inline=False
        )
    
    embed.set_footer(text=f"Her davet = {min(50, 10 + (user_data['level'] // 5))} cowoncy")
    
    await ctx.send(embed=embed)

@bot.command(name="ödültalep", aliases=["odultalep", "claimreward"])
async def claim_reward(ctx):
    user_data = get_user_data(ctx.author.id)
    invites = user_data.get("invites", 0)
    claimed = user_data.get("invite_claimed", 0)
    
    available = invites - claimed
    
    if available <= 0:
        await ctx.send(f"❌ **{ctx.author.display_name}**, talep edebileceğin ödül yok! (Toplam davetin: {invites})")
        return
    
    reward_per_invite = min(50, 10 + (user_data["level"] // 5))
    total_reward = available * reward_per_invite
    
    user_data["cowoncy"] += total_reward
    user_data["invite_claimed"] = invites
    add_xp(ctx.author.id, total_reward // 10)
    save_db()
    
    sync_invites_to_panel(ctx.author.id, invites)
    
    embed = discord.Embed(
        title="🎉 Ödül Talep Edildi!",
        description=f"**{ctx.author.display_name}** ödülünü aldı!",
        color=0x00ff00
    )
    embed.add_field(name="📊 Talep Edilen Davet", value=f"{available} davet", inline=True)
    embed.add_field(name="💰 Kazanılan Cowoncy", value=f"+{total_reward}", inline=True)
    embed.add_field(name="⭐ Kazanılan XP", value=f"+{total_reward // 10}", inline=True)
    embed.add_field(name="📈 Toplam Davet", value=f"{invites}", inline=True)
    embed.set_footer(text="Her 1 davet = 10-50 cowoncy | Seviyene göre artar!")
    
    await ctx.send(embed=embed)

@bot.command(name="cekilisbaslat", aliases=["cekilis-baslat"])
@commands.has_permissions(administrator=True)
async def start_giveaway(ctx, prize: str, duration: str = None):
    if not duration:
        await ctx.send("❌ Lütfen süre belirtin! Örnek: `.cekilisbaslat 1000 cowoncy 10m`")
        return
    
    time_seconds = 0
    if duration.endswith('s'):
        time_seconds = int(duration[:-1])
    elif duration.endswith('m'):
        time_seconds = int(duration[:-1]) * 60
    elif duration.endswith('h'):
        time_seconds = int(duration[:-1]) * 3600
    elif duration.endswith('d'):
        time_seconds = int(duration[:-1]) * 86400
    else:
        try:
            time_seconds = int(duration)
        except:
            await ctx.send("❌ Geçersiz süre! Örnek: `10m`, `1h`, `30s`")
            return
    
    if time_seconds < 10:
        await ctx.send("❌ Süre en az 10 saniye olmalı!")
        return
    
    giveaway_id = f"{ctx.guild.id}_{ctx.channel.id}_{int(datetime.now().timestamp())}"
    start_time = datetime.now().isoformat()
    end_time = (datetime.now() + timedelta(seconds=time_seconds)).isoformat()
    
    db["giveaways"][giveaway_id] = {
        "guild_id": ctx.guild.id,
        "channel_id": ctx.channel.id,
        "message_id": None,
        "prize": prize,
        "duration": time_seconds,
        "start_time": start_time,
        "end_time": end_time,
        "host": ctx.author.id,
        "participants": [],
        "winner": None,
        "ended": False
    }
    save_db()
    
    webhook_data = {
        "action": "add_giveaway",
        "id": giveaway_id,
        "guild_id": str(ctx.guild.id),
        "channel_id": str(ctx.channel.id),
        "prize": prize,
        "duration": time_seconds,
        "start_time": start_time,
        "end_time": end_time,
        "host_id": str(ctx.author.id)
    }
    send_to_panel(webhook_data)
    
    embed = discord.Embed(
        title="🎉 Çekiliş Başladı!",
        description=f"**Ödül:** {prize}\n**Katılmak için:** 🎲 tıklayın!",
        color=0xffd700
    )
    embed.add_field(name="⏱️ Süre", value=f"{time_seconds // 60}m {time_seconds % 60}s", inline=True)
    embed.add_field(name="👤 Başlatan", value=ctx.author.mention, inline=True)
    embed.add_field(name="📊 Katılımcı", value="0", inline=True)
    embed.set_footer(text=f"ID: {giveaway_id[:8]}")
    
    view = GiveawayView(giveaway_id, ctx)
    message = await ctx.send(embed=embed, view=view)
    
    db["giveaways"][giveaway_id]["message_id"] = message.id
    save_db()
    
    asyncio.create_task(schedule_giveaway_end(giveaway_id))

async def schedule_giveaway_end(giveaway_id):
    giveaway = db["giveaways"].get(giveaway_id)
    if not giveaway:
        return
    
    end_time = datetime.fromisoformat(giveaway["end_time"])
    wait_time = (end_time - datetime.now()).total_seconds()
    
    if wait_time > 0:
        await asyncio.sleep(wait_time)
    
    await end_giveaway(giveaway_id)

async def end_giveaway(giveaway_id):
    giveaway = db["giveaways"].get(giveaway_id)
    if not giveaway or giveaway["ended"]:
        return
    
    giveaway["ended"] = True
    participants = giveaway["participants"]
    
    try:
        channel = bot.get_channel(giveaway["channel_id"])
        if channel:
            message = await channel.fetch_message(giveaway["message_id"])
        else:
            return
    except:
        return
    
    if participants:
        winner_id = random.choice(participants)
        giveaway["winner"] = winner_id
        save_db()
        
        webhook_data = {
            "action": "end_giveaway",
            "id": giveaway_id,
            "winner_id": str(winner_id)
        }
        send_to_panel(webhook_data)
        
        try:
            winner = await bot.fetch_user(int(winner_id))
            prize = giveaway["prize"]
            
            embed = discord.Embed(
                title="🎉 Çekiliş Sona Erdi!",
                description=f"**Kazanan:** {winner.mention}\n**Ödül:** {prize}",
                color=0xffd700
            )
            embed.add_field(name="📊 Toplam Katılımcı", value=len(participants), inline=True)
            
            await message.edit(embed=embed, view=None)
            await channel.send(f"🎊 Tebrikler {winner.mention}! **{prize}** kazandın! 🎊")
            
            user_data = get_user_data(winner.id)
            if "cowoncy" in prize.lower():
                try:
                    amount = int(''.join(filter(str.isdigit, prize)))
                    user_data["cowoncy"] += amount
                    save_db()
                except:
                    pass
            
        except Exception as e:
            print(f"Kazanan bildirilirken hata: {e}")
    else:
        embed = discord.Embed(
            title="😔 Çekiliş Sona Erdi",
            description="Katılımcı olmadığı için kazanan seçilemedi!",
            color=0xff0000
        )
        await message.edit(embed=embed, view=None)

@bot.command(name="yardım", aliases=["help", "yardim"])
async def help_command(ctx):
    embed = discord.Embed(
        title="🎮 os.gentv Bot - Komut Listesi",
        description="Tüm komutlar ve açıklamaları aşağıda!",
        color=0x00ff00
    )
    
    embed.add_field(
        name="━━━━━━━━━━━━━━━━━━━━━",
        value="**🎰 OYUN KOMUTLARI**",
        inline=False
    )
    embed.add_field(
        name="`.bj <miktar/all>`",
        value="Blackjack oyna (Butonlu)\nÖrnek: `.bj 100` veya `.bj all`",
        inline=False
    )
    embed.add_field(
        name="`.cf <yazı/tura> <miktar/all>`",
        value="Yazı Tura oyna\nÖrnek: `.cf yazı 50`",
        inline=False
    )
    embed.add_field(
        name="`.slots <miktar/all>`",
        value="Slot makinesi oyna\nÖrnek: `.slots 200`",
        inline=False
    )
    
    embed.add_field(
        name="━━━━━━━━━━━━━━━━━━━━━",
        value="**📋 GÜNLÜK GÖREVLER**",
        inline=False
    )
    embed.add_field(
        name="`.daily`",
        value="Günlük ödülünü al\nHer gün bir kere!",
        inline=False
    )
    
    embed.add_field(
        name="━━━━━━━━━━━━━━━━━━━━━",
        value="**📊 DAVET SİSTEMİ**",
        inline=False
    )
    embed.add_field(
        name="`.davetlerim`",
        value="Davet sayını ve alabileceğin ödülü göster",
        inline=False
    )
    embed.add_field(
        name="`.ödültalep`",
        value="Davet ödülünü talep et\nHer davet için 10-50 cowoncy!",
        inline=False
    )
    
    embed.add_field(
        name="━━━━━━━━━━━━━━━━━━━━━",
        value="**🎯 ADMIN KOMUTLARI**",
        inline=False
    )
    embed.add_field(
        name="`.cekilisbaslat <ödül> <süre>`",
        value="Çekiliş başlat\nÖrnek: `.cekilisbaslat 1000 cowoncy 10m`",
        inline=False
    )
    
    embed.add_field(
        name="━━━━━━━━━━━━━━━━━━━━━",
        value="**💰 EKONOMİ KOMUTLARI**",
        inline=False
    )
    embed.add_field(
        name="`.cash` veya `.bal`",
        value="Bakiyeni görüntüle\nÖrnek: `.cash @kişi`",
        inline=False
    )
    embed.add_field(
        name="`.give <@kişi> <miktar>`",
        value="Başkasına cowoncy gönder\nÖrnek: `.give @Ahmet 100`",
        inline=False
    )
    
    embed.add_field(
        name="━━━━━━━━━━━━━━━━━━━━━",
        value="**📊 PROFİL & SIRALAMA**",
        inline=False
    )
    embed.add_field(
        name="`.profile` veya `.profil`",
        value="Profilini görüntüle\nÖrnek: `.profile @kişi`",
        inline=False
    )
    
    if ctx.author.id == OWNER_ID:
        embed.add_field(
            name="━━━━━━━━━━━━━━━━━━━━━",
            value="**👑 OWNER KOMUTLARI**",
            inline=False
        )
        embed.add_field(
            name="`.paragonder <@kişi> <miktar>`",
            value="Kişiye cowoncy gönder\nÖrnek: `.paragonder @Ahmet 1000`",
            inline=False
        )
        embed.add_field(
            name="`.xpver <@kişi> <miktar>`",
            value="Kişiye XP ver\nÖrnek: `.xpver @Ahmet 500`",
            inline=False
        )
    
    embed.set_footer(
        text="os.gentv Bot v3.0 | Davet sistemi & Çekilişler!",
        icon_url=ctx.author.avatar.url if ctx.author.avatar else None
    )
    
    await ctx.send(embed=embed)

@bot.command(name="paragonder")
async def send_money(ctx, member: discord.Member, amount: int):
    if ctx.author.id != OWNER_ID:
        await ctx.send("❌ This command is only for the bot owner!")
        return
    
    if amount < 1:
        await ctx.send("❌ You must give at least 1 cowoncy!")
        return
    
    user_data = get_user_data(member.id)
    user_data["cowoncy"] += amount
    save_db()
    
    await ctx.send(f"✅ {member.mention} has received {amount} cowoncy! New balance: {user_data['cowoncy']}")

@bot.command(name="xpver")
async def give_xp(ctx, member: discord.Member, amount: int):
    if ctx.author.id != OWNER_ID:
        await ctx.send("❌ This command is only for the bot owner!")
        return
    
    if amount < 1:
        await ctx.send("❌ You must give at least 1 XP!")
        return
    
    leveled_up = add_xp(member.id, amount)
    user_data = get_user_data(member.id)
    
    msg = f"✅ {member.mention} has received {amount} XP! (Level: {user_data['level']})"
    if leveled_up:
        msg += f"\n🎉 **LEVEL UP!** New level: {user_data['level']} (Bonus: {user_data['level'] * 100} cowoncy!)"
    
    await ctx.send(msg)

# ==================== MESAJ OLAYI ====================
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    user_data = get_user_data(message.author.id)
    user_data["message_count"] += 1
    
    if user_data["message_count"] == 1:
        webhook_data = {
            "action": "create_user",
            "user_id": str(message.author.id),
            "username": str(message.author.display_name)
        }
        send_to_panel(webhook_data)
    
    xp_gain = random.randint(5, 15)
    leveled_up = add_xp(message.author.id, xp_gain)
    
    if leveled_up:
        level = user_data["level"]
        bonus = level * 100
        await message.channel.send(f"🎉 {message.author.mention} **Level {level}** oldu! (+{bonus} cowoncy bonus!)")
    
    save_db()
    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    try:
        invites = await member.guild.invites()
        
        if str(member.guild.id) not in db["guilds"]:
            db["guilds"][str(member.guild.id)] = {"invites": {}}
        
        guild_data = db["guilds"][str(member.guild.id)]
        invite_data = guild_data.get("invites", {})
        
        for invite in invites:
            invite_id = str(invite.id)
            if invite_id not in invite_data:
                invite_data[invite_id] = {
                    "inviter_id": str(invite.inviter.id),
                    "uses": invite.uses
                }
            else:
                old_uses = invite_data[invite_id]["uses"]
                if invite.uses > old_uses:
                    inviter_id = int(invite_data[invite_id]["inviter_id"])
                    user_data = get_user_data(inviter_id)
                    user_data["invites"] += 1
                    save_db()
                    
                    sync_invites_to_panel(inviter_id, user_data["invites"])
                    
                    try:
                        inviter = await bot.fetch_user(inviter_id)
                        channel = member.guild.system_channel
                        if channel:
                            await channel.send(
                                f"🎉 {inviter.mention} davetiyle {member.mention} sunucuya katıldı! ({user_data['invites']} davet)"
                            )
                    except:
                        pass
                    
                    invite_data[invite_id]["uses"] = invite.uses
                    break
        
        db["guilds"][str(member.guild.id)]["invites"] = invite_data
        save_db()
    except Exception as e:
        print(f"Davet takip hatası: {e}")

# ==================== HATA YÖNETİMİ ====================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Eksik argüman! `.yardım` yazarak doğru kullanımı öğrenebilirsin.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Geçersiz argüman! `.yardım` yazarak doğru kullanımı öğrenebilirsin.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Bu komutu kullanmak için yeterli yetkin yok! (Admin gerekiyor)")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"❌ Komut bekleme süresinde! {round(error.retry_after)} saniye sonra tekrar dene.")
    else:
        print(f"Hata: {error}")
        await ctx.send(f"❌ Bir hata oluştu: {str(error)[:100]}")

# ==================== BOT OLAYI ====================
@bot.event
async def on_ready():
    print(f"✅ {bot.user} olarak giriş yapıldı!")
    print(f"📊 {len(db['users'])} kullanıcı yüklendi!")
    print(f"👑 Bot sahibi ID: {OWNER_ID}")
    print(f"💰 Max 'all' bahis: {MAX_ALL_BET}")
    
    if 'giveaways' not in db:
        db['giveaways'] = {}
    if 'events' not in db:
        db['events'] = {}
    if 'lotteries' not in db:
        db['lotteries'] = {}
    save_db()
    
    for giveaway_id, giveaway in db['giveaways'].items():
        if not giveaway.get('ended', False):
            webhook_data = {
                "action": "add_giveaway",
                "id": giveaway_id,
                "guild_id": str(giveaway['guild_id']),
                "channel_id": str(giveaway['channel_id']),
                "prize": giveaway['prize'],
                "duration": giveaway['duration'],
                "start_time": giveaway['start_time'],
                "end_time": giveaway['end_time'],
                "host_id": str(giveaway['host'])
            }
            send_to_panel(webhook_data)
    
    print(f"🎯 {len(db.get('giveaways', {}))} aktif çekiliş")
    print(f"🎪 {len(db.get('events', {}))} aktif etkinlik")
    print(f"🎰 {len(db.get('lotteries', {}))} aktif piyango")
    
    await bot.change_presence(activity=discord.Game(name=".yardım | os.gentv Bot v3.0"))

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
