import discord
from discord.ext import commands
from datetime import datetime, timedelta, timezone
import qrcode
import os

class InviteSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cursor = bot.cursor
        self.conn = bot.conn
        self.PST = timezone(timedelta(hours=-8))

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            return

        self.cursor.execute("SELECT message_id, channel_id FROM embeds WHERE id = 'central'")
        row = self.cursor.fetchone()
        if row and payload.message_id == row[0]:
            guild = self.bot.get_guild(payload.guild_id)
            user = guild.get_member(payload.user_id)
            if user:
                await self.handle_invite(user, guild)

    async def handle_invite(self, user, guild):
        user_id = str(user.id)
        current_time = datetime.now(self.PST).replace(tzinfo=None)

        self.cursor.execute("SELECT last_invite FROM invites WHERE user_id = %s", (user_id,))
        result = self.cursor.fetchone()
        if result and (current_time - result[0].replace(tzinfo=None)).days < 30:
            await user.send("You can only generate a new invite QR code every 30 days.")
            return

        invite = await guild.text_channels[0].create_invite(max_uses=1, unique=True, max_age=86400)
        img_path = await self.generate_qr_code(invite.url, user_id)

        await user.send(file=discord.File(img_path), content="Here is your one-time invite QR code.")
        os.remove(img_path)

        self.cursor.execute('''
            INSERT INTO invites (user_id, last_invite, invite_url) VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE last_invite = VALUES(last_invite), invite_url = VALUES(invite_url)
        ''', (user_id, current_time, invite.url))
        self.conn.commit()

    async def generate_qr_code(self, data, user_id):
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#00FFE4", back_color="white")
        img_path = f"invite_{user_id}.png"
        img.save(img_path)
        return img_path

async def setup(bot):
    await bot.add_cog(InviteSystem(bot))