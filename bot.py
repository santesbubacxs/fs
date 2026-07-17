import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
import json
import random
import asyncio
from datetime import datetime, timedelta
import math
import os
import requests

# Bot ayarları
BOT_TOKEN = os.getenv('BOT_TOKEN', 'SENIN_BOT_TOKENIN')
OWNER_ID = int(os.getenv('OWNER_ID', 123456789))
MAX_ALL_BET = 250000
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')  # PHP paneli ile iletişim için

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
        "invites": {},  # Davet takibi için
        "giveaways": {},  # Çekilişler için
        "events": {}  # Etkinlikler için
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
            "message_count": 0,
            "quest": None,
            "invites": 0,  # Toplam davet
            "invite_claimed": 0  # Toplanan davet ödülleri
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

# ==================== PHP PANELİ İLE ENTEGRASYON ====================
def send_to_panel(data):
    """PHP paneline veri gönderir"""
    if WEBHOOK_URL:
        try:
            response = requests.post(WEBHOOK_URL, json=data, timeout=5)
            return response.status_code == 200
        except:
            return False
    return False

def sync_invites_to_panel(user_id, invite_count):
    """Davet sayısını PHP paneline senkronize eder"""
    data = {
        "action": "update_invites",
        "user_id": str(user_id),
        "invites": invite_count
    }
    return send_to_panel(data)

# ==================== DAVET TAKİP SİSTEMİ ====================
@bot.event
async def on_member_join(member):
    """Yeni üye katıldığında davet edeni bul"""
    # Davet eden kişiyi bul
    invites = await member.guild.invites()
    
    # Bu sunucu için davet sayılarını tut
    if str(member.guild.id) not in db["guilds"]:
        db["guilds"][str(member.guild.id)] = {"invites": {}}
    
    guild_data = db["guilds"][str(member.guild.id)]
    invite_data = guild_data.get("invites", {})
    
    # Son davetleri kontrol et
    for invite in invites:
        invite_id = str(invite.id)
        if invite_id not in invite_data:
            invite_data[invite_id] = {
                "inviter_id": str(invite.inviter.id),
                "uses": invite.uses
            }
        else:
            # Davet kullanımı arttıysa
            old_uses = invite_data[invite_id]["uses"]
            if invite.uses > old_uses:
                inviter_id = int(invite_data[invite_id]["inviter_id"])
                user_data = get_user_data(inviter_id)
                user_data["invites"] += 1
                save_db()
                
                # PHP paneline gönder
                sync_invites_to_panel(inviter_id, user_data["invites"])
                
                # Davet edene tebrik mesajı
                try:
                    inviter = await bot.fetch_user(inviter_id)
                    await member.guild.get_channel(member.guild.system_channel.id).send(
                        f"🎉 {inviter.mention} davetiyle {member.mention} sunucuya katıldı! ({user_data['invites']} davet)"
                    )
                except:
                    pass
                
                # Davet sayısını güncelle
                invite_data[invite_id]["uses"] = invite.uses
                break
    
    db["guilds"][str(member.guild.id)]["invites"] = invite_data
    save_db()

# ==================== ÖDÜL TALEP SİSTEMİ ====================
@bot.command(name="ödültalep", aliases=["odultalep", "claimreward"])
async def claim_reward(ctx):
    """Davet ödülünü talep et"""
    user_data = get_user_data(ctx.author.id)
    invites = user_data["invites"]
    claimed = user_data["invite_claimed"]
    
    # Talep edilebilecek davet sayısı
    available = invites - claimed
    
    if available <= 0:
        await ctx.send(f"❌ **{ctx.author.display_name}**, talep edebileceğin ödül yok! (Toplam davetin: {invites})")
        return
    
    # Her davet için ödül hesapla (10-50 cowoncy arası)
    reward_per_invite = min(50, 10 + (user_data["level"] // 5))
    total_reward = available * reward_per_invite
    
    # Ödülü ver
    user_data["cowoncy"] += total_reward
    user_data["invite_claimed"] = invites
    add_xp(ctx.author.id, total_reward // 10)
    save_db()
    
    # PHP paneline güncelleme gönder
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

# ==================== ÇEKİLİŞ KOMUTLARI ====================
@bot.command(name="cekilisbaslat", aliases=["cekilis-baslat"])
@commands.has_permissions(administrator=True)
async def start_giveaway(ctx, prize: str, duration: str = None):
    """Çekiliş başlat: .cekilisbaslat <ödül> <süre>"""
    if not duration:
        await ctx.send("❌ Lütfen süre belirtin! Örnek: `.cekilisbaslat 1000 cowoncy 10m`")
        return
    
    # Süreyi çözümle
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
    
    # Çekiliş ID'si oluştur
    giveaway_id = f"{ctx.guild.id}_{ctx.channel.id}_{int(datetime.now().timestamp())}"
    
    # Çekilişi veritabanına kaydet
    db["giveaways"][giveaway_id] = {
        "guild_id": ctx.guild.id,
        "channel_id": ctx.channel.id,
        "message_id": None,
        "prize": prize,
        "duration": time_seconds,
        "start_time": datetime.now().isoformat(),
        "end_time": (datetime.now() + timedelta(seconds=time_seconds)).isoformat(),
        "host": ctx.author.id,
        "participants": [],
        "winner": None,
        "ended": False
    }
    save_db()
    
    # Embed oluştur
    embed = discord.Embed(
        title="🎉 Çekiliş Başladı!",
        description=f"**Ödül:** {prize}\n**Katılmak için:** 🎲 tıklayın!",
        color=0xffd700
    )
    embed.add_field(name="⏱️ Süre", value=f"{time_seconds // 60}m {time_seconds % 60}s", inline=True)
    embed.add_field(name="👤 Başlatan", value=ctx.author.mention, inline=True)
    embed.add_field(name="📊 Katılımcı", value="0", inline=True)
    embed.set_footer(text=f"ID: {giveaway_id[:8]}")
    
    # Buton ekle
    view = GiveawayView(giveaway_id, ctx)
    message = await ctx.send(embed=embed, view=view)
    
    # Mesaj ID'sini kaydet
    db["giveaways"][giveaway_id]["message_id"] = message.id
    save_db()
    
    # Zamanlayıcı başlat
    await schedule_giveaway_end(giveaway_id)

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
        
        # Embed'i güncelle
        embed = interaction.message.embeds[0]
        embed.set_field_at(2, name="📊 Katılımcı", value=str(len(giveaway["participants"])), inline=True)
        await interaction.message.edit(embed=embed)
        
        await interaction.response.send_message("🎉 Çekilişe katıldın! İyi şanslar!", ephemeral=True)

async def schedule_giveaway_end(giveaway_id):
    """Çekiliş bitişini zamanla"""
    giveaway = db["giveaways"].get(giveaway_id)
    if not giveaway:
        return
    
    end_time = datetime.fromisoformat(giveaway["end_time"])
    wait_time = (end_time - datetime.now()).total_seconds()
    
    if wait_time > 0:
        await asyncio.sleep(wait_time)
    
    # Çekilişi sonlandır
    await end_giveaway(giveaway_id)

async def end_giveaway(giveaway_id):
    """Çekilişi sonlandır ve kazananı seç"""
    giveaway = db["giveaways"].get(giveaway_id)
    if not giveaway or giveaway["ended"]:
        return
    
    giveaway["ended"] = True
    participants = giveaway["participants"]
    
    # Kanala mesaj gönder
    try:
        channel = bot.get_channel(giveaway["channel_id"])
        message = await channel.fetch_message(giveaway["message_id"])
    except:
        return
    
    if participants:
        winner_id = random.choice(participants)
        giveaway["winner"] = winner_id
        save_db()
        
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
            
            # Kazanana ödülü ver
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

# ==================== ETKİNLİK KOMUTLARI ====================
@bot.command(name="etkinlikbaslat", aliases=["etkinlik-baslat"])
@commands.has_permissions(administrator=True)
async def start_event(ctx, cowoncy_reward: int, invite_requirement: int):
    """Etkinlik başlat: .etkinlikbaslat <cowoncy> <invite>"""
    if cowoncy_reward < 1 or invite_requirement < 1:
        await ctx.send("❌ Ödül ve davet sayısı 1'den büyük olmalı!")
        return
    
    event_id = f"event_{ctx.guild.id}_{int(datetime.now().timestamp())}"
    
    db["events"][event_id] = {
        "guild_id": ctx.guild.id,
        "channel_id": ctx.channel.id,
        "cowoncy_reward": cowoncy_reward,
        "invite_requirement": invite_requirement,
        "start_time": datetime.now().isoformat(),
        "ended": False,
        "completed": []
    }
    save_db()
    
    embed = discord.Embed(
        title="🎯 Yeni Etkinlik Başladı!",
        description=f"**{invite_requirement}** davet yapan herkese **{cowoncy_reward}** cowoncy!",
        color=0x00ff00
    )
    embed.add_field(name="💰 Ödül", value=f"{cowoncy_reward} cowoncy", inline=True)
    embed.add_field(name="🎯 Hedef", value=f"{invite_requirement} davet", inline=True)
    embed.set_footer(text="Davetleri topla ve ödülü kaçırma!")
    
    await ctx.send(embed=embed)
    
    # Otomatik kontrol başlat
    asyncio.create_task(auto_check_event(event_id))

async def auto_check_event(event_id):
    """Etkinlik katılımcılarını otomatik kontrol et"""
    event = db["events"].get(event_id)
    if not event:
        return
    
    while not event["ended"]:
        await asyncio.sleep(60)  # Her dakika kontrol et
        
        for user_id, user_data in db["users"].items():
            if user_id in event["completed"]:
                continue
            
            if user_data.get("invites", 0) >= event["invite_requirement"]:
                # Ödülü ver
                user_data["cowoncy"] += event["cowoncy_reward"]
                add_xp(int(user_id), event["cowoncy_reward"] // 10)
                event["completed"].append(user_id)
                save_db()
                
                # Bildirim gönder
                try:
                    channel = bot.get_channel(event["channel_id"])
                    user = await bot.fetch_user(int(user_id))
                    await channel.send(
                        f"🎉 {user.mention} etkinlik ödülünü kazandı! "
                        f"**{event['cowoncy_reward']}** cowoncy cüzdanına eklendi!"
                    )
                except:
                    pass

# ==================== PİYANGO KOMUTLARI ====================
@bot.command(name="piyangobaslat", aliases=["piyango-baslat"])
@commands.has_permissions(administrator=True)
async def start_lottery(ctx, prize_amount: int):
    """Piyango başlat: .piyangobaslat <ödül-miktarı>"""
    if prize_amount < 100:
        await ctx.send("❌ Ödül en az 100 cowoncy olmalı!")
        return
    
    # Piyango ID'si
    lottery_id = f"lottery_{ctx.guild.id}_{int(datetime.now().timestamp())}"
    
    db["daily_quests"][lottery_id] = {
        "type": "lottery",
        "guild_id": ctx.guild.id,
        "channel_id": ctx.channel.id,
        "prize": prize_amount,
        "ticket_price": 10,
        "tickets": {},
        "start_time": datetime.now().isoformat(),
        "end_time": (datetime.now() + timedelta(minutes=10)).isoformat(),
        "ended": False,
        "winner": None
    }
    save_db()
    
    embed = discord.Embed(
        title="🎰 Piyango Başladı!",
        description=f"**Toplam Ödül:** {prize_amount} cowoncy\n**Bilet Fiyatı:** 10 cowoncy\n\nKatılmak için `.biletal` yaz!",
        color=0xffd700
    )
    embed.add_field(name="⏱️ Süre", value="10 dakika", inline=True)
    embed.add_field(name="🎟️ Toplam Bilet", value="0", inline=True)
    embed.set_footer(text="Piyango 10 dakika sonra sona erecek")
    
    await ctx.send(embed=embed)
    
    # Otomatik sonlandırma
    asyncio.create_task(end_lottery(lottery_id))

@bot.command(name="biletal")
async def buy_ticket(ctx):
    """Piyango bileti al"""
    # Aktif piyangoyu bul
    active_lottery = None
    lottery_id = None
    
    for lid, lottery in db["daily_quests"].items():
        if (lottery["type"] == "lottery" and 
            not lottery["ended"] and 
            lottery["guild_id"] == ctx.guild.id):
            active_lottery = lottery
            lottery_id = lid
            break
    
    if not active_lottery:
        await ctx.send("❌ Şu anda aktif piyango yok!")
        return
    
    user_data = get_user_data(ctx.author.id)
    ticket_price = active_lottery["ticket_price"]
    
    if user_data["cowoncy"] < ticket_price:
        await ctx.send(f"❌ Yeterli cowoncyin yok! ({ticket_price} cowoncy gerekli)")
        return
    
    # Bilet al
    user_id = str(ctx.author.id)
    if user_id not in active_lottery["tickets"]:
        active_lottery["tickets"][user_id] = 0
    
    active_lottery["tickets"][user_id] += 1
    user_data["cowoncy"] -= ticket_price
    save_db()
    
    # Toplam bilet sayısını güncelle
    total_tickets = sum(active_lottery["tickets"].values())
    
    # Embed'i güncelle
    try:
        channel = bot.get_channel(active_lottery["channel_id"])
        async for msg in channel.history(limit=10):
            if msg.embeds and "Piyango Başladı!" in msg.embeds[0].title:
                embed = msg.embeds[0]
                embed.set_field_at(1, name="🎟️ Toplam Bilet", value=str(total_tickets), inline=True)
                await msg.edit(embed=embed)
                break
    except:
        pass
    
    await ctx.send(f"✅ **{ctx.author.display_name}** {ticket_price} cowoncy karşılığında 1 bilet aldı! (Toplam biletin: {active_lottery['tickets'][user_id]})")

async def end_lottery(lottery_id):
    """Piyangoyu sonlandır"""
    await asyncio.sleep(600)  # 10 dakika
    
    lottery = db["daily_quests"].get(lottery_id)
    if not lottery or lottery["ended"]:
        return
    
    lottery["ended"] = True
    
    # Kazananı seç
    tickets = []
    for user_id, count in lottery["tickets"].items():
        tickets.extend([user_id] * count)
    
    try:
        channel = bot.get_channel(lottery["channel_id"])
        
        if tickets:
            winner_id = random.choice(tickets)
            lottery["winner"] = winner_id
            save_db()
            
            # Kazanana ödülü ver
            user_data = get_user_data(int(winner_id))
            user_data["cowoncy"] += lottery["prize"]
            add_xp(int(winner_id), lottery["prize"] // 10)
            save_db()
            
            try:
                winner = await bot.fetch_user(int(winner_id))
                await channel.send(
                    f"🎊 **Piyango Kazananı:** {winner.mention}\n"
                    f"💰 **{lottery['prize']}** cowoncy kazandı! 🎊"
                )
            except:
                await channel.send(f"🎊 Piyango kazananı: <@{winner_id}>")
        else:
            await channel.send("😔 Piyangoya katılım olmadı, ödül iade edildi!")
            
    except Exception as e:
        print(f"Piyango sonlandırma hatası: {e}")

# ==================== DAVET KONTROL KOMUTU ====================
@bot.command(name="davetlerim", aliases=["invites"])
async def my_invites(ctx):
    """Davet sayını göster"""
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

# ==================== DİĞER KOMUTLAR ====================
# (Buraya önceki tüm komutlar gelir - blackjack, mines, cf, slots, lottery, highlow, daily, quest, vb.)
# Kodu kısaltmak için önceki komutlar buraya eklenir...

# ==================== YARDIM KOMUTU (GÜNCELLENMİŞ) ====================
@bot.command(name="yardım", aliases=["help", "yardim"])
async def help_command(ctx):
    """Tüm komutları gösterir"""
    
    embed = discord.Embed(
        title="🎮 Arigato Bot - Komut Listesi",
        description="Tüm komutlar ve açıklamaları aşağıda!",
        color=0x00ff00
    )
    
    # Ana Kategoriler
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
        name="`.mines <miktar/all> <mayın>`",
        value="Mayın Tarlası oyna (Butonlu)\nÖrnek: `.mines 1000 3`",
        inline=False
    )
    embed.add_field(
        name="`.lottery <miktar/all>`",
        value="Piyango oyna\nÖrnek: `.lottery 50`",
        inline=False
    )
    embed.add_field(
        name="`.highlow <miktar/all> <high/low>`",
        value="Yüksek/Düşük oyna\nÖrnek: `.highlow 100 high`",
        inline=False
    )
    
    embed.add_field(
        name="━━━━━━━━━━━━━━━━━━━━━",
        value="**📋 GÜNLÜK GÖREVLER**",
        inline=False
    )
    embed.add_field(
        name="`.quest` veya `.görev`",
        value="Günlük görevini görüntüle\nHer gün yeni görev!",
        inline=False
    )
    embed.add_field(
        name="`.claimquest` veya `.ödüial`",
        value="Görev ödülünü al (Tamamlandıysa)\nMax 5000 cowoncy kazanabilirsin!",
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
        name="`.piyangobaslat <ödül>`",
        value="Piyango başlat\nÖrnek: `.piyangobaslat 5000`",
        inline=False
    )
    embed.add_field(
        name="`.etkinlikbaslat <cowoncy> <invite>`",
        value="Etkinlik başlat\nÖrnek: `.etkinlikbaslat 1000 5`",
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
        name="`.shop`",
        value="Mağazayı görüntüle",
        inline=False
    )
    embed.add_field(
        name="`.buy <ürün>`",
        value="Mağazadan ürün satın al\nÜrünler: common, uncommon, rare, epic, legendary",
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
    embed.add_field(
        name="`.xp`",
        value="XP ve level durumunu göster",
        inline=False
    )
    embed.add_field(
        name="`.top`",
        value="Küresel sıralamayı göster\nÖrnek: `.top level` (Level sıralaması)",
        inline=False
    )
    
    embed.add_field(
        name="━━━━━━━━━━━━━━━━━━━━━",
        value="**💍 SOSYAL KOMUTLAR**",
        inline=False
    )
    embed.add_field(
        name="`.marry <@kişi>`",
        value="Evlenme teklifi et\nÖrnek: `.marry @Ayşe`",
        inline=False
    )
    embed.add_field(
        name="`.hug`, `.kiss`, `.pat`",
        value="Sarılmak, öpmek veya okşamak\nÖrnek: `.hug @kişi`",
        inline=False
    )
    embed.add_field(
        name="`.blush`, `.cry`, `.dance`",
        value="Duygu ifadeleri kullan\nÖrnek: `.dance`",
        inline=False
    )
    embed.add_field(
        name="`.happy`, `.smile`",
        value="Mutlu veya gülümse\nÖrnek: `.happy`",
        inline=False
    )
    
    # Owner komutları (sadece sahibine göster)
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
        embed.add_field(
            name="`.resetquest <@kişi>`",
            value="Kişinin görevini sıfırla\nÖrnek: `.resetquest @Ahmet`",
            inline=False
        )
        embed.add_field(
            name="`.setquest <@kişi> <tip> <hedef> <ödül>`",
            value="Özel görev oluştur\nTipler: bj, cf, slots, mines, lottery, highlow, hug, kiss\nÖrnek: `.setquest @Ahmet bj 5 1000`",
            inline=False
        )
    
    embed.set_footer(
        text="Arigato Bot v3.0 | Davet sistemi & Çekilişler & Etkinlikler!",
        icon_url=ctx.author.avatar.url if ctx.author.avatar else None
    )
    
    await ctx.send(embed=embed)

# ==================== MESAJ OLAYI ====================
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    user_data = get_user_data(message.author.id)
    user_data["message_count"] += 1
    
    # Mesaj gönderme görevi için
    if user_data.get("quest") and user_data["quest"]["command"] == "message":
        check_quest_progress(message.author.id, "message", 1)
    
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
        await ctx.send(f"❌ Eksik argüman! `.yardım` yazarak doğru kullanımı öğrenebilirsin.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Geçersiz argüman! `.yardım` yazarak doğru kullanımı öğrenebilirsin.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Bu komutu kullanmak için yeterli yetkin yok! (Admin gerekiyor)")
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
    print(f"🎯 {len(db['giveaways'])} aktif çekiliş")
    print(f"🎪 {len(db['events'])} aktif etkinlik")
    await bot.change_presence(activity=discord.Game(name=".yardım | Arigato Bot v3.0"))

# Bot'u çalıştır
if __name__ == "__main__":
    bot.run(BOT_TOKEN)
