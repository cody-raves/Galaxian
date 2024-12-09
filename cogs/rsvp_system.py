import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import pytz

PST = pytz.timezone('America/Los_Angeles')
UTC = pytz.utc

class RSVPCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reminders = []  # List of reminders: [(reminder_time, channel_id, message_id, event_data)]
        self.event_messages = {}  # Track event embeds (message_id -> channel_id)
        self.reminder_task.start()
        self.cleanup_task.start()
        self.event_monitor_task.start()

    def cog_unload(self):
        self.reminder_task.cancel()
        self.cleanup_task.cancel()
        self.event_monitor_task.cancel()

    async def load_rsvp_events(self):
        """Load existing events and reminders into memory at startup."""
        cursor = self.bot.conn.cursor()
        cursor.execute("""
            SELECT message_id, channel_id, reminder_time, name, crew_name, flyer_url, crew_logo_url, location, event_date, start_time, age_requirement, cover_fee, contact_info, event_type
            FROM events
            WHERE reminder_sent = false
        """)
        events = cursor.fetchall()

        for event in events:
            message_id, channel_id, reminder_time, name, crew_name, flyer_url, crew_logo_url, location, event_date, start_time, age_requirement, cover_fee, contact_info, event_type = event
            
            self.event_messages[message_id] = channel_id  # Track the event message
            
            # Prepare the event data and store it in the reminders list
            event_data = {
                "name": name,
                "crew_name": crew_name,
                "flyer": flyer_url,
                "crew_logo": crew_logo_url,
                "location": location,
                "date": event_date,
                "start_time": start_time,
                "age_requirement": age_requirement,
                "cover_fee": cover_fee,
                "info": contact_info,
                "type": event_type,
            }
            self.reminders.append((reminder_time, channel_id, message_id, event_data))

        print(f"Loaded {len(self.reminders)} reminders and {len(self.event_messages)} events into RSVP system.")

    async def check_for_new_events(self):
        """Fetch new events from the database and update memory."""
        cursor = self.bot.conn.cursor()
        cursor.execute("""
            SELECT message_id, channel_id, reminder_time, name, crew_name, flyer_url, crew_logo_url, location, event_date, start_time, age_requirement, cover_fee, contact_info, event_type
            FROM events
            WHERE message_id NOT IN (%s)
        """, (tuple(self.event_messages.keys()) or (0,)))  # Handle empty tuple case
        new_events = cursor.fetchall()

        for event in new_events:
            message_id, channel_id, reminder_time, name, crew_name, flyer_url, crew_logo_url, location, event_date, start_time, age_requirement, cover_fee, contact_info, event_type = event
            
            self.event_messages[message_id] = channel_id  # Track the event message
            
            # Prepare the event data and add to reminders
            event_data = {
                "name": name,
                "crew_name": crew_name,
                "flyer": flyer_url,
                "crew_logo": crew_logo_url,
                "location": location,
                "date": event_date,
                "start_time": start_time,
                "age_requirement": age_requirement,
                "cover_fee": cover_fee,
                "info": contact_info,
                "type": event_type,
            }
            self.reminders.append((reminder_time, channel_id, message_id, event_data))

            print(f"Added new event to RSVP system: message_id={message_id}, channel_id={channel_id}")

    @tasks.loop(minutes=1)
    async def reminder_task(self):
        """Send reminders for events."""
        now_utc = datetime.now(UTC)
        reminders_to_remove = []

        for reminder in self.reminders:
            reminder_time_utc, channel_id, message_id, event_data = reminder

            if now_utc >= reminder_time_utc:
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    continue

                try:
                    message = await channel.fetch_message(message_id)
                    users_to_notify = []

                    for reaction in message.reactions:
                        if str(reaction.emoji) == "\u2705":
                            async for user in reaction.users():
                                if user != self.bot.user:
                                    users_to_notify.append(user)

                    for user in users_to_notify:
                        try:
                            start_time_pst = event_data["start_time"].astimezone(PST)
                            await user.send(
                                f"Reminder: The event '{event_data['name']}' is happening soon! Here are the details:\n\n"
                                f"**Location**: {event_data['location']}\n"
                                f"**Date**: {start_time_pst.strftime('%m-%d-%Y')}\n"
                                f"**Start Time**: {start_time_pst.strftime('%I:%M %p')} PST\n"
                                f"**Contact Info**: {event_data['info']}"
                            )
                        except discord.Forbidden:
                            print(f"Failed to send reminder to {user.name}; they may have DMs disabled.")

                    cursor = self.bot.conn.cursor()
                    cursor.execute("UPDATE events SET reminder_sent = true WHERE message_id = %s", (message_id,))
                    self.bot.conn.commit()
                    reminders_to_remove.append(reminder)

                except discord.NotFound:
                    print(f"Message with ID {message_id} not found. Cleaning up.")
                    cursor = self.bot.conn.cursor()
                    cursor.execute("DELETE FROM events WHERE message_id = %s", (message_id,))
                    self.bot.conn.commit()
                    reminders_to_remove.append(reminder)

        for reminder in reminders_to_remove:
            self.reminders.remove(reminder)

    @tasks.loop(minutes=5)
    async def cleanup_task(self):
        """Clean up expired events."""
        now = datetime.now(PST)
        cursor = self.bot.conn.cursor()

        cursor.execute("SELECT * FROM events WHERE event_date <= %s AND end_time <= %s", (now.date(), now.time()))
        expired_events = cursor.fetchall()
        for event in expired_events:
            channel = self.bot.get_channel(event[14])
            if channel:
                try:
                    message = await channel.fetch_message(event[13])
                    await message.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass

            cursor.execute("DELETE FROM events WHERE message_id = %s", (event[13],))
            self.bot.conn.commit()

    @tasks.loop(minutes=1)
    async def event_monitor_task(self):
        """Check for new events and add them to memory."""
        await self.check_for_new_events()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Handle RSVP reactions."""
        if payload.message_id in self.event_messages and str(payload.emoji) == "\u2705":
            guild = self.bot.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)
            if member:
                try:
                    await member.send(
                        "You have successfully RSVPed to the event! We'll send you a reminder closer to the event date."
                    )
                except discord.Forbidden:
                    print(f"Failed to DM {member.name}. DMs might be disabled.")

async def setup(bot):
    cog = RSVPCog(bot)
    await cog.load_rsvp_events()
    await bot.add_cog(cog)
