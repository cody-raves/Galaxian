import discord
from discord.ext import commands
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageDraw, ImageFont
import qrcode
import os
import asyncio


class InviteSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cursor = bot.cursor
        self.conn = bot.conn
        self.PST = timezone(timedelta(hours=-8))
        self.events_channel_id = 1325380437048299593  # Replace with your events channel ID

    @commands.Cog.listener()
    async def on_message(self, message):
        """Delete any message in the events channel that isn't the !newevent command."""
        if message.channel.id != self.events_channel_id:
            return

        if message.author == self.bot.user:
            return

        if message.content.lower() == "!newevent":
            return

        # Try to send a DM before deleting the message
        try:
            await message.author.send(f"Only the !newevent command is allowed in {message.channel.mention}.")
        except discord.Forbidden:
            print(f"Could not send a DM to {message.author}. They might have DMs disabled.")

        # Wait briefly before deleting the message to ensure the DM is sent
        await asyncio.sleep(1)
        await message.delete()

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

        # Check if the user is an admin
        if user.guild_permissions.administrator:
            invite = await guild.text_channels[0].create_invite(max_uses=1, unique=True, max_age=86400)
            img_path = self.create_qr_image(invite.url, user_id)

            await user.send(
                content=f"Here is your one-time invite QR code.\n\nDirect link: {invite.url}",
                file=discord.File(img_path)
            )
            os.remove(img_path)
            return

        # Non-admin users must wait 30 days between invites
        self.cursor.execute("SELECT last_invite FROM invites WHERE user_id = %s", (user_id,))
        result = self.cursor.fetchone()
        if result and (current_time - result[0].replace(tzinfo=None)).days < 30:
            await user.send("You can only generate a new invite QR code every 30 days.")
            return

        invite = await guild.text_channels[0].create_invite(max_uses=1, unique=True, max_age=86400)
        img_path = self.create_qr_image(invite.url, user_id)

        await user.send(
            content=f"Here is your one-time invite QR code.\n\nDirect link: {invite.url}",
            file=discord.File(img_path)
        )
        os.remove(img_path)

        self.cursor.execute('''
            INSERT INTO invites (user_id, last_invite, invite_url) VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE last_invite = VALUES(last_invite), invite_url = VALUES(invite_url)
        ''', (user_id, current_time, invite.url))
        self.conn.commit()

    def create_qr_image(self, data, user_id):
        """Generate a static PNG QR code with text overlay."""
        invite_code = data.split("https://")[-1]

        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#00FFE4", back_color="black").convert("RGBA")

        # Add text overlay
        draw = ImageDraw.Draw(img)
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        font_code = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)

        # Title text
        title_text = "DARKNET"
        title_x = (img.width - draw.textlength(title_text, font=font_title)) // 2
        draw.text((title_x, 10), title_text, font=font_title, fill="#00FFE4")

        # Invite code text
        code_text = f"{invite_code}"
        code_x = (img.width - draw.textlength(code_text, font=font_code)) // 2
        draw.text((code_x, img.height - 40), code_text, font=font_code, fill="#00FFE4")

        # Save image
        img_path = f"invite_{user_id}.png"
        img.save(img_path)
        return img_path


async def setup(bot):
    await bot.add_cog(InviteSystem(bot))
