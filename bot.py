import discord
from discord.ext import commands
from discord.ui import Button, View
import json
import random
import asyncio
from datetime import datetime, timedelta
import math
import os

# Bot ayarları
BOT_TOKEN = os.getenv('BOT_TOKEN', 'SENIN_BOT_TOKENIN')
OWNER_ID = int(os.getenv('OWNER_ID', 123456789))
MAX_ALL_BET = 250000

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
        }
    }

db = load_database()

def save_db():
    try:
        with open('database.json', 'w', encoding='utf-8') as f:
            json.dump(db, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Database kaydedilirken hata: {e}")

def get_user_data(user_id):
    if str(user_id) not in db["users"]:
        db["users"][str(user_id)] = {
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
            "message_count": 0
        }
        save_db()
    return db["users"][str(user_id)]

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

# ==================== BLACKJACK BUTONLU ====================
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

# ==================== MINES BUTONLU ====================
class MinesView(View):
    def __init__(self, ctx, bet, mine_count=3):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.bet = bet
        self.mine_count = mine_count
        self.grid = ["⬛"] * 25
        self.mine_positions = random.sample(range(25), mine_count)
        self.revealed = set()
        self.game_over = False
        self.multiplier = 1.0
        self.message = None
        
        for i in range(25):
            row = i // 5
            col = i % 5
            button = Button(label="⬛", style=discord.ButtonStyle.secondary, row=row, custom_id=str(i))
            button.callback = self.create_callback(i)
            self.add_item(button)
    
    def create_callback(self, index):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.ctx.author.id:
                await interaction.response.send_message("❌ Bu senin oyunun değil!", ephemeral=True)
                return
            
            if self.game_over:
                await interaction.response.send_message("❌ Oyun bitti!", ephemeral=True)
                return
            
            if index in self.revealed:
                await interaction.response.send_message("❌ Bu kare zaten açıldı!", ephemeral=True)
                return
            
            if index in self.mine_positions:
                self.game_over = True
                user_data = get_user_data(self.ctx.author.id)
                user_data["cowoncy"] -= self.bet
                save_db()
                
                for i, item in enumerate(self.children):
                    if int(item.custom_id) in self.mine_positions:
                        item.label = "💣"
                        item.style = discord.ButtonStyle.danger
                    elif int(item.custom_id) in self.revealed:
                        item.label = "🟩"
                        item.style = discord.ButtonStyle.success
                    item.disabled = True
                
                await interaction.response.edit_message(
                    content=f"💥 **MAYINA BASTIN!** {self.bet} cowoncy kaybettin!",
                    view=self
                )
                self.stop()
                return
            
            self.revealed.add(index)
            self.multiplier += 0.4
            
            for item in self.children:
                if int(item.custom_id) == index:
                    item.label = "🟩"
                    item.style = discord.ButtonStyle.success
                    item.disabled = True
            
            win = int(self.bet * self.multiplier)
            
            await interaction.response.edit_message(
                content=f"🎯 **Güvenli!** Çarpan: {self.multiplier:.1f}x (Kazanç: {win} cowoncy)\nDevam et veya Cash Out yap!",
                view=self
            )
        
        return callback
    
    @discord.ui.button(label="💰 Cash Out", style=discord.ButtonStyle.green, row=5)
    async def cashout_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ Bu senin oyunun değil!", ephemeral=True)
            return
        
        if self.game_over:
            await interaction.response.send_message("❌ Oyun bitti!", ephemeral=True)
            return
        
        self.game_over = True
        win = int(self.bet * self.multiplier)
        user_data = get_user_data(self.ctx.author.id)
        user_data["cowoncy"] += win
        add_xp(self.ctx.author.id, win // 20)
        save_db()
        
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(
            content=f"🎉 **CASH OUT!** {win} cowoncy kazandın! (Çarpan: {self.multiplier:.1f}x)",
            view=self
        )
        self.stop()

# ==================== KOMUTLAR ====================

# ===== BLACKJACK =====
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

# ===== MINES =====
@bot.command(name="mines")
async def mines_command(ctx, bet_input=None, mine_count: int = 3):
    if bet_input is None:
        await ctx.send("❌ Please specify a bet amount! Example: `.mines 1000 3` or `.mines all`")
        return
    
    can_use, remaining = check_cooldown(ctx.author.id, "mines", 1)
    if not can_use:
        await ctx.send(f"❌ **{ctx.author.display_name}**! Slow down and try the command again in {remaining} seconds.")
        return
    
    if mine_count < 1 or mine_count > 5:
        await ctx.send("❌ Mayın sayısı 1-5 arası olmalı!")
        return
    
    user_data = get_user_data(ctx.author.id)
    bet, error = parse_bet(ctx, bet_input)
    if error:
        await ctx.send(error)
        return
    
    if bet < 1:
        await ctx.send("❌ You must bet at least 1 cowoncy!")
        return
    
    view = MinesView(ctx, bet, mine_count)
    
    embed = discord.Embed(
        title="💣 Mayın Tarlası",
        description=f"**{ctx.author.display_name}** started a mines game.\n\nBet: **{bet}**\nMines: **{mine_count}**\nCash Out: 0 (0.00x)\nNext: 1 (1.40x)",
        color=0xff0000
    )
    
    view.message = await ctx.send(embed=embed, view=view)

# ===== COINFLIP =====
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

# ===== SLOTS =====
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

# ===== LOTTERY =====
@bot.command(name="lottery")
async def lottery_command(ctx, bet_input: str = None):
    if bet_input is None:
        await ctx.send("❌ Please specify a bet amount! Example: `.lottery 100` or `.lottery all`")
        return
    
    can_use, remaining = check_cooldown(ctx.author.id, "lottery", 1)
    if not can_use:
        await ctx.send(f"❌ **{ctx.author.display_name}**! Slow down and try the command again in {remaining} seconds.")
        return
    
    user_data = get_user_data(ctx.author.id)
    bet, error = parse_bet(ctx, bet_input)
    if error:
        await ctx.send(error)
        return
    
    if bet < 10:
        await ctx.send("❌ Minimum 10 cowoncy bet required!")
        return
    
    number = random.randint(1, 100)
    win_number = random.randint(1, 100)
    
    if number == win_number:
        win = bet * 50
        user_data["cowoncy"] += win
        xp_gain = win // 10
        add_xp(ctx.author.id, xp_gain)
        save_db()
        await ctx.send(f"🎯 **{number}** - JACKPOT! You won **{win}** cowoncy! 🎉")
    elif abs(number - win_number) <= 5:
        win = bet * 5
        user_data["cowoncy"] += win
        xp_gain = win // 20
        add_xp(ctx.author.id, max(1, xp_gain))
        save_db()
        await ctx.send(f"🎯 **{number}** (Winning: {win_number}) - So close! You won **{win}** cowoncy!")
    elif abs(number - win_number) <= 10:
        win = bet * 2
        user_data["cowoncy"] += win
        xp_gain = win // 30
        add_xp(ctx.author.id, max(1, xp_gain))
        save_db()
        await ctx.send(f"🎯 **{number}** (Winning: {win_number}) - Close! You won **{win}** cowoncy!")
    else:
        user_data["cowoncy"] -= bet
        xp_gain = bet // 40
        add_xp(ctx.author.id, max(1, xp_gain))
        save_db()
        await ctx.send(f"🎯 **{number}** (Winning: {win_number}) - You lost **{bet}** cowoncy!")

# ===== HIGHLOW =====
@bot.command(name="highlow")
async def highlow_command(ctx, bet_input: str = None, guess: str = None):
    if bet_input is None or guess is None:
        await ctx.send("❌ Please specify bet and guess! Example: `.highlow 100 high` or `.highlow all low`")
        return
    
    if guess.lower() not in ["high", "low", "yuksek", "dusuk"]:
        await ctx.send("❌ Choose 'high' or 'low'!")
        return
    
    can_use, remaining = check_cooldown(ctx.author.id, "highlow", 1)
    if not can_use:
        await ctx.send(f"❌ **{ctx.author.display_name}**! Slow down and try the command again in {remaining} seconds.")
        return
    
    user_data = get_user_data(ctx.author.id)
    bet, error = parse_bet(ctx, bet_input)
    if error:
        await ctx.send(error)
        return
    
    if bet < 10:
        await ctx.send("❌ Minimum 10 cowoncy bet required!")
        return
    
    number = random.randint(1, 100)
    previous_number = random.randint(1, 100)
    
    user_guess = "high" if guess.lower() in ["high", "yuksek"] else "low"
    result = "high" if number > previous_number else "low"
    
    if user_guess == result:
        win = bet * 2
        user_data["cowoncy"] += win
        xp_gain = win // 15
        add_xp(ctx.author.id, max(1, xp_gain))
        save_db()
        await ctx.send(f"📈 Number: {number} (Previous: {previous_number})\nCorrect! You won **{win}** cowoncy!")
    else:
        user_data["cowoncy"] -= bet
        xp_gain = bet // 30
        add_xp(ctx.author.id, max(1, xp_gain))
        save_db()
        await ctx.send(f"📈 Number: {number} (Previous: {previous_number})\nWrong! You lost **{bet}** cowoncy.")

# ===== DAILY =====
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

# ===== CASH =====
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
    embed.set_footer(text=f"Level {user_data['level']} | XP: {user_data['xp']}/{get_level_xp(user_data['level'])}")
    
    await ctx.send(embed=embed)

# ===== GIVE =====
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

# ===== XP =====
@bot.command(name="xp")
async def xp_command(ctx):
    user_data = get_user_data(ctx.author.id)
    current_level_xp = user_data["xp"]
    needed_xp = get_level_xp(user_data["level"])
    progress = int((current_level_xp / needed_xp) * 100)
    
    bar_length = 20
    filled = int(bar_length * progress / 100)
    bar = "█" * filled + "░" * (bar_length - filled)
    
    embed = discord.Embed(
        title=f"📊 {ctx.author.display_name} - XP Durumu",
        color=0x00ff00
    )
    embed.add_field(name="📈 Level", value=user_data["level"], inline=True)
    embed.add_field(name="⭐ XP", value=f"{current_level_xp}/{needed_xp}", inline=True)
    embed.add_field(name="📊 İlerleme", value=f"{bar} **{progress}%**", inline=False)
    embed.add_field(name="🎯 Toplam XP", value=user_data["total_xp"], inline=True)
    embed.add_field(name="💬 Mesaj", value=user_data["message_count"], inline=True)
    
    next_level_bonus = (user_data["level"] + 1) * 100
    embed.set_footer(text=f"🎁 Sonraki seviye bonusu: {next_level_bonus} cowoncy")
    
    await ctx.send(embed=embed)

# ===== PROFILE =====
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
    embed.add_field(name="📊 Toplam XP", value=user_data["total_xp"], inline=True)
    embed.add_field(name="💬 Mesaj", value=user_data["message_count"], inline=True)
    embed.add_field(name="🎯 Boss Streak", value=user_data["boss_streak"], inline=True)
    embed.add_field(name="💍 Evli", value="Evet" if user_data["marriage"] else "Hayır", inline=True)
    embed.add_field(name="📦 Weapon Crates", value=user_data["weapon_crates"], inline=True)
    
    await ctx.send(embed=embed)

# ===== MARRY =====
@bot.command(name="marry")
async def marry_command(ctx, member: discord.Member):
    if member.id == ctx.author.id:
        await ctx.send("❌ You can't marry yourself!")
        return
    
    user_data = get_user_data(ctx.author.id)
    target_data = get_user_data(member.id)
    
    if user_data["marriage"]:
        await ctx.send("❌ You're already married!")
        return
    
    if target_data["marriage"]:
        await ctx.send("❌ This person is already married!")
        return
    
    user_data["marriage"] = member.id
    target_data["marriage"] = ctx.author.id
    add_xp(ctx.author.id, 100)
    add_xp(member.id, 100)
    save_db()
    
    await ctx.send(f"💍 {ctx.author.mention} and {member.mention} got married! Congratulations! (+100 XP)")

# ===== SHOP =====
@bot.command(name="shop")
async def shop_command(ctx):
    embed = discord.Embed(
        title="🛒 Mağaza",
        description="Satın almak için `.buy <ürün>` yaz",
        color=0x00ff00
    )
    
    shop_items = {
        "common": 100,
        "uncommon": 300,
        "rare": 500,
        "epic": 1000,
        "legendary": 2500
    }
    
    for item, price in shop_items.items():
        embed.add_field(
            name=item.upper(),
            value=f"💰 {price} cowoncy",
            inline=True
        )
    
    await ctx.send(embed=embed)

# ===== BUY =====
@bot.command(name="buy")
async def buy_item(ctx, item: str):
    user_data = get_user_data(ctx.author.id)
    
    shop_items = {
        "common": 100,
        "uncommon": 300,
        "rare": 500,
        "epic": 1000,
        "legendary": 2500
    }
    
    if item.lower() not in shop_items:
        await ctx.send("❌ Invalid item! Check `.shop`")
        return
    
    price = shop_items[item.lower()]
    if user_data["cowoncy"] < price:
        await ctx.send(f"❌ You need {price} cowoncy!")
        return
    
    user_data["cowoncy"] -= price
    user_data["inventory"].append(item.lower())
    add_xp(ctx.author.id, 10)
    save_db()
    
    await ctx.send(f"✅ You bought **{item.upper()}**! Remaining: {user_data['cowoncy']} cowoncy (+10 XP)")

# ===== TOP =====
@bot.command(name="top")
async def top_command(ctx, category: str = "global"):
    if category == "global":
        all_users = []
        for user_id, data in db["users"].items():
            all_users.append((user_id, data["cowoncy"]))
        
        all_users.sort(key=lambda x: x[1], reverse=True)
        
        embed = discord.Embed(
            title="🏆 Küresel Sıralama",
            color=0xffd700
        )
        
        top_10 = all_users[:10]
        for i, (uid, cowoncy) in enumerate(top_10, 1):
            try:
                user = await bot.fetch_user(int(uid))
                name = user.display_name
            except:
                name = f"Kullanıcı #{uid}"
            embed.add_field(
                name=f"#{i} {name}",
                value=f"💰 {cowoncy} cowoncy",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    elif category == "level":
        all_users = []
        for user_id, data in db["users"].items():
            all_users.append((user_id, data["level"], data["total_xp"]))
        
        all_users.sort(key=lambda x: x[1], reverse=True)
        
        embed = discord.Embed(
            title="🏆 Level Sıralaması",
            color=0x00ff00
        )
        
        top_10 = all_users[:10]
        for i, (uid, level, xp) in enumerate(top_10, 1):
            try:
                user = await bot.fetch_user(int(uid))
                name = user.display_name
            except:
                name = f"Kullanıcı #{uid}"
            embed.add_field(
                name=f"#{i} {name}",
                value=f"📈 Level {level} (Toplam XP: {xp})",
                inline=False
            )
        
        await ctx.send(embed=embed)

# ==================== EMOJİ KOMUTLARI ====================
@bot.command(name="hug")
async def hug_command(ctx, member: discord.Member = None):
    if member is None:
        add_xp(ctx.author.id, 3)
        await ctx.send(f"{ctx.author.mention} 🤗 hugs themselves (+3 XP)")
    else:
        add_xp(ctx.author.id, 5)
        add_xp(member.id, 5)
        await ctx.send(f"{ctx.author.mention} 🤗 hugs {member.mention} (+5 XP)")

@bot.command(name="kiss")
async def kiss_command(ctx, member: discord.Member = None):
    if member is None:
        add_xp(ctx.author.id, 3)
        await ctx.send(f"{ctx.author.mention} 😘 kisses themselves (+3 XP)")
    else:
        add_xp(ctx.author.id, 5)
        add_xp(member.id, 5)
        await ctx.send(f"{ctx.author.mention} 😘 kisses {member.mention} (+5 XP)")

@bot.command(name="pat")
async def pat_command(ctx, member: discord.Member = None):
    if member is None:
        add_xp(ctx.author.id, 3)
        await ctx.send(f"{ctx.author.mention} 🖐️ pats themselves (+3 XP)")
    else:
        add_xp(ctx.author.id, 5)
        add_xp(member.id, 5)
        await ctx.send(f"{ctx.author.mention} 🖐️ pats {member.mention} (+5 XP)")

@bot.command(name="blush")
async def blush_command(ctx):
    add_xp(ctx.author.id, 2)
    await ctx.send(f"{ctx.author.mention} 😊 blushes (+2 XP)")

@bot.command(name="cry")
async def cry_command(ctx):
    add_xp(ctx.author.id, 2)
    await ctx.send(f"{ctx.author.mention} 😢 cries (+2 XP)")

@bot.command(name="dance")
async def dance_command(ctx):
    add_xp(ctx.author.id, 2)
    await ctx.send(f"{ctx.author.mention} 💃 dances (+2 XP)")

@bot.command(name="happy")
async def happy_command(ctx):
    add_xp(ctx.author.id, 2)
    await ctx.send(f"{ctx.author.mention} 😄 is happy (+2 XP)")

@bot.command(name="smile")
async def smile_command(ctx):
    add_xp(ctx.author.id, 2)
    await ctx.send(f"{ctx.author.mention} 🙂 smiles (+2 XP)")

# ==================== OWNER KOMUTLARI ====================
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

# ==================== HELP ====================
@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="🎮 SantesHub - OwO Tarzı Bot",
        description="Tamamen OwO botu klonu! Butonlu oyunlar, daily sistemi ve daha fazlası!",
        color=0x00ff00
    )
    
    embed.add_field(
        name="🎰 Oyunlar",
        value="`.bj <miktar/all>` - Blackjack (Butonlu)\n`.cf <yazı/tura> <miktar/all>` - Yazı Tura\n`.slots <miktar/all>` - Slot Makinesi\n`.mines <miktar/all> <mayın>` - Mayın Tarlası (Butonlu)\n`.lottery <miktar/all>` - Piyango\n`.highlow <miktar/all> <high/low>` - Yüksek/Düşük",
        inline=False
    )
    embed.add_field(
        name="💰 Ekonomi",
        value="`.daily` - Günlük ödül al\n`.cash` - Bakiyeni gör\n`.give @kişi <miktar>` - Para gönder\n`.shop` - Mağazayı gör\n`.buy <ürün>` - Ürün satın al",
        inline=False
    )
    embed.add_field(
        name="📊 Diğer",
        value="`.top` - Sıralamalar\n`.top level` - Level sıralaması\n`.profile` - Profilini gör\n`.xp` - XP durumunu gör\n`.marry @kişi` - Evlenme teklifi et",
        inline=False
    )
    embed.add_field(
        name="😊 Emoji",
        value="`.hug`, `.kiss`, `.pat`, `.blush`, `.cry`, `.dance`, `.happy`, `.smile`",
        inline=False
    )
    embed.add_field(
        name="🎯 Örnekler",
        value="`.bj all` - Tüm paranla Blackjack oyna\n`.mines 1000 3` - 1000 parayla 3 mayınlı oyun başlat\n`.cf yazı 50` - 50 cowoncy ile yazı tura oyna",
        inline=False
    )
    embed.set_footer(text="SantesHub v2.0 | OwO tarzı butonlu oyunlar! | .paragonder & .xpver sadece owner")

    await ctx.send(embed=embed)

# ==================== MESAJ OLAYI ====================
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    user_data = get_user_data(message.author.id)
    user_data["message_count"] += 1
    
    xp_gain = random.randint(5, 15)
    leveled_up = add_xp(message.author.id, xp_gain)
    
    if leveled_up:
        level = user_data["level"]
        bonus = level * 100
        await message.channel.send(f"🎉 {message.author.mention} **Level {level}** oldu! (+{bonus} cowoncy bonus!)")
    
    save_db()
    await bot.process_commands(message)

# ==================== HATA YÖNETİMİ ====================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Eksik argüman! Doğru kullanım: `{ctx.prefix}{ctx.command.name} {ctx.command.usage or ''}`")
    elif isinstance(error, commands.CommandNotFound):
        # Sessizce geç - komut bulunamadı
        pass
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Geçersiz argüman! Doğru kullanım: `{ctx.prefix}{ctx.command.name} {ctx.command.usage or ''}`")
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
    await bot.change_presence(activity=discord.Game(name=".help | SantesHub"))

# Bot'u çalıştır
if __name__ == "__main__":
    bot.run(BOT_TOKEN)
