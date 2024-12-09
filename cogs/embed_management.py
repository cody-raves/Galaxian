import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone


class EmbedManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cursor = bot.cursor
        self.conn = bot.conn
        self.PST = timezone(timedelta(hours=-8))
        print("EmbedManagement cog initialized.")
        self.update_invite_board.start()  # Start the task when the cog is loaded

    @commands.command(name="embedhere")
    @commands.has_permissions(administrator=True)
    async def embed_here(self, ctx):
        """
        Create or update an embed in a specific channel.
        """
        channel = self.bot.get_channel(950561797381955634)
        if channel is None:
            await ctx.send("The specified channel could not be found.")
            print("embed_here: Channel not found.")
            return

        await ctx.send("Creating or updating the embed...")
        await self.create_new_embed(channel)

    async def create_new_embed(self, channel):
        """
        Logic for creating or updating the embed with specific content.
        """
        # Check if an embed already exists
        try:
            self.cursor.execute("SELECT message_id, channel_id FROM embeds WHERE id = 'central'")
            row = self.cursor.fetchone()
        except Exception as e:
            print(f"create_new_embed: Failed to fetch embed info from database. Error: {e}")
            row = None

        old_message = None
        if row:
            old_channel = self.bot.get_channel(row[1])
            if old_channel:
                try:
                    old_message = await old_channel.fetch_message(row[0])
                except discord.NotFound:
                    print("create_new_embed: Old message not found.")
                except Exception as e:
                    print(f"create_new_embed: Failed to fetch old message. Error: {e}")

        # Create embed content
        embed = discord.Embed(
            description="Embed rules and content here...",
            color=discord.Color.from_str('#00FFE4')
        )

        # Update or send new embed
        if old_message:
            await old_message.edit(embed=embed)
            message = old_message
            print("create_new_embed: Updated existing embed.")
        else:
            message = await channel.send(embed=embed)
            print("create_new_embed: Sent new embed.")

        # Save embed info in the database
        try:
            self.cursor.execute('''
                INSERT INTO embeds (id, message_id, channel_id) VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE message_id = VALUES(message_id), channel_id = VALUES(channel_id)
            ''', ('central', message.id, channel.id))
            self.conn.commit()
        except Exception as e:
            print(f"create_new_embed: Failed to save embed info to database. Error: {e}")

    @commands.command(name="inviteboard")
    @commands.has_permissions(administrator=True)
    async def invite_board(self, ctx):
        """
        Create or update the invite summary board in a specific channel.
        """
        channel = self.bot.get_channel(1308580887197257809)
        if channel is None:
            await ctx.send("The specified channel could not be found.")
            print("invite_board: Channel not found.")
            return

        await ctx.send("Creating or updating the invite summary board...")
        await self.create_invite_board_embed(channel)

    async def create_invite_board_embed(self, channel):
        """
        Logic for creating or updating the invite summary board.
        """
        # Check if the invite board already exists
        try:
            self.cursor.execute("SELECT message_id, channel_id FROM embeds WHERE id = 'invite_board'")
            row = self.cursor.fetchone()
        except Exception as e:
            print(f"create_invite_board_embed: Failed to fetch invite board info from database. Error: {e}")
            row = None

        old_message = None
        if row:
            old_channel = self.bot.get_channel(row[1])
            if old_channel:
                try:
                    old_message = await old_channel.fetch_message(row[0])
                except discord.NotFound:
                    print("create_invite_board_embed: Old invite board message not found.")
                except Exception as e:
                    print(f"create_invite_board_embed: Failed to fetch old invite board message. Error: {e}")

        # Calculate invite stats
        try:
            self.cursor.execute("SELECT COUNT(*) FROM invites")
            active_invites = self.cursor.fetchone()[0] if self.cursor.fetchone() else 0
        except Exception as e:
            print(f"create_invite_board_embed: Failed to fetch active invites. Error: {e}")
            active_invites = 0

        recent_joins = sum(1 for member in self.bot.get_all_members() if member.joined_at and member.joined_at >= datetime.now(self.PST) - timedelta(hours=24))
        try:
            self.cursor.execute("SELECT inviter FROM invites ORDER BY last_invite DESC LIMIT 1")
            last_invite_created_by = self.cursor.fetchone()
            last_invite_created_by = last_invite_created_by[0] if last_invite_created_by else '----'
        except Exception as e:
            print(f"create_invite_board_embed: Failed to fetch last invite created by. Error: {e}")
            last_invite_created_by = '----'

        invite_conversion_rate = round((recent_joins / active_invites) * 100, 2) if active_invites else 0
        member_count = sum(1 for _ in self.bot.get_all_members())

        # Create the embed
        current_time = datetime.now(self.PST).strftime("%I:%M %p PST")
        embed = discord.Embed(
            title="Invite Summary Board",
            description=(
                f"**Server Member Count**: {member_count}\n\n"
                f"**Active Invites**: {active_invites}\n\n"
                f"**Members Joined in Last 24 Hours**: {recent_joins}\n\n"
                f"**Last Invite Created By**: {last_invite_created_by}\n\n"
                f"**Invite Conversion Rate**: {invite_conversion_rate}%\n\n"
                f"*(Last updated {current_time})*"
            ),
            color=discord.Color.from_str('#00FFE4')
        )

        # Update or send new embed
        if old_message:
            await old_message.edit(embed=embed)
            print("create_invite_board_embed: Updated existing invite board.")
        else:
            message = await channel.send(embed=embed)
            print("create_invite_board_embed: Sent new invite board.")

            # Save invite board info in the database
            try:
                self.cursor.execute('''
                    INSERT INTO embeds (id, message_id, channel_id) VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE message_id = VALUES(message_id), channel_id = VALUES(channel_id)
                ''', ('invite_board', message.id, channel.id))
                self.conn.commit()
            except Exception as e:
                print(f"create_invite_board_embed: Failed to save invite board info to database. Error: {e}")

    @tasks.loop(minutes=5)
    async def update_invite_board(self):
        """
        Periodically update the invite summary board every 5 minutes.
        """
        channel = self.bot.get_channel(1308580887197257809)
        if channel:
            print("update_invite_board: Updating invite board.")
            await self.create_invite_board_embed(channel)
        else:
            print("update_invite_board: Channel not found, skipping update.")

    @update_invite_board.before_loop
    async def before_update_invite_board(self):
        """
        Wait until the bot is ready before starting the periodic task.
        """
        await self.bot.wait_until_ready()


async def setup(bot):
    """
    Set up the EmbedManagement cog.
    """
    print("Setting up EmbedManagement cog...")
    await bot.add_cog(EmbedManagement(bot))
    print("EmbedManagement cog loaded successfully.")
