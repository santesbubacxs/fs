import discord
from discord.ui import Button, View, Modal, TextInput
import requests
import os

# --- BOT AYARLARI ---
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Discord Bot Token'ınızı buraya yazın
TARGET_CHANNEL_ID = 1527272715130769578  # Botun paneli göndereceği kanal ID'si

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
client = discord.Client(intents=intents)

# --- MODAL (Açılır Pencere) Sınıfı ---
class UsernameModal(Modal, title="Roblox Kullanıcı Sorgulama"):
    username = TextInput(
        label="Roblox Kullanıcı Adı",
        placeholder="Örnek: Kylaaa",
        min_length=3,
        max_length=20,
        required=True
    )

    def __init__(self, mode):
        super().__init__()
        self.mode = mode  # Hangi butona basıldığını hatırla (avatar veya profil)

    async def on_submit(self, interaction: discord.Interaction):
        username = self.username.value
        await interaction.response.defer() # Yanıtı beklet, işlem yapılırken bekleme animasyonu göster
        
        # Roblox API: Kullanıcı ID'sini çek
        url = "https://users.roblox.com/v1/usernames/users"
        payload = {"usernames": [username], "excludeBannedUsers": True}
        
        try:
            response = requests.post(url, json=payload)
            data = response.json()
            
            if not data['data']:
                await interaction.followup.send(f"❌ **{username}** isminde bir Roblox kullanıcısı bulunamadı.", ephemeral=True)
                return
                
            user_id = data['data'][0]['id']
            
            # --- SEÇENEK 1: PROFİL SORGULA ---
            if self.mode == "profile":
                profile_link = f"https://www.roblox.com/users/{user_id}/profile"
                
                embed = discord.Embed(
                    title=f"🎮 {username} Profili Bulundu!",
                    description=f"🔗 **Profil Linki:**\n{profile_link}",
                    color=discord.Color.green()
                )
                embed.set_footer(text=f"Roblox ID: {user_id}")
                await interaction.followup.send(embed=embed)

            # --- SEÇENEK 2: AVATAR SORGULA ---
            elif self.mode == "avatar":
                # Avatar görselini çek
                thumbnail_url = f"https://thumbnails.roblox.com/v1/users/avatar?userIds={user_id}&size=720x720&format=Png&isCircular=false"
                thumb_response = requests.get(thumbnail_url)
                thumb_data = thumb_response.json()
                
                if thumb_data['data']:
                    avatar_image = thumb_data['data'][0]['imageUrl']
                    
                    embed = discord.Embed(
                        title=f"🎭 {username} Avatarı",
                        description=f"🔗 [Roblox Profili](https://www.roblox.com/users/{user_id}/profile)",
                        color=discord.Color.blue()
                    )
                    embed.set_image(url=avatar_image)
                    embed.set_footer(text=f"Roblox ID: {user_id}")
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send("⚠️ Avatar görseli alınamadı. Kullanıcının avatarı gizli veya boş olabilir.")

        except Exception as e:
            await interaction.followup.send("⚠️ Bir hata oluştu, lütfen daha sonra tekrar deneyin.", ephemeral=True)
            print(f"Hata: {e}")

# --- BUTONLAR (Panel) ---
class PanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    # 1. Buton: Avatar Sorgula
    @discord.ui.button(label="🖼️ Roblox Avatar Sorgula", style=discord.ButtonStyle.primary, custom_id="btn_avatar")
    async def avatar_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(UsernameModal(mode="avatar"))

    # 2. Buton: Profil Sorgula
    @discord.ui.button(label="🔗 Roblox Profil Sorgula", style=discord.ButtonStyle.success, custom_id="btn_profile")
    async def profile_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(UsernameModal(mode="profile"))

# --- BOT OLAYI ---
@client.event
async def on_ready():
    print(f"✅ {client.user} olarak giriş yapıldı!")
    
    # Panelin gönderileceği kanalı bul
    channel = client.get_channel(TARGET_CHANNEL_ID)
    if channel is None:
        print(f"❌ Hata: {TARGET_CHANNEL_ID} ID'li kanal bulunamadı! Lütfen ID'yi kontrol et.")
        return

    # Embed Panelini oluştur
    embed = discord.Embed(
        title="🎮 Roblox Sorgulama Paneli",
        description="Aşağıdaki butonlardan birine tıklayarak istediğiniz işlemi seçin.",
        color=discord.Color.purple()
    )
    embed.add_field(name="🖼️ Avatar Sorgula", value="Seçtiğiniz kullanıcının 3D avatar görselini gösterir.", inline=False)
    embed.add_field(name="🔗 Profil Sorgula", value="Seçtiğiniz kullanıcının Roblox profil bağlantısını verir.", inline=False)
    embed.set_footer(text="Bot tarafından otomatik oluşturulmuştur.")

    # Mesajı kanala gönder (Eski mesajları temizlemediğimiz için yeni mesaj olarak eklenir)
    await channel.send(embed=embed, view=PanelView())

# Botu çalıştır
client.run(BOT_TOKEN)
