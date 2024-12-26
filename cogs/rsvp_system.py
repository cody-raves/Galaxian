import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, date
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
        print("RSVPCog initialized and tasks started.")

    def cog_unload(self):
        self.reminder_task.cancel()
        self.cleanup_task.cancel()
        self.event_monitor_task.cancel()
        print("RSVPCog tasks unloaded.")

    def ensure_datetime(self, value):
        """Ensure the value is a datetime object."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        if isinstance(value, date):  # Handle `date` type
            return datetime.combine(value, datetime.min.time(), UTC)
        if isinstance(value, timedelta):  # Handle `timedelta` type
            return datetime.min + value
        if value is None:
            raise ValueError("Encountered None when expecting a datetime string or object.")
        raise TypeError(f"Unsupported type for datetime conversion: {type(value)}")

    async def load_rsvp_events(self):
        """Load existing events and reminders into memory at startup."""
        cursor = self.bot.conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM events
            WHERE reminder_sent = false
        """)
        events = cursor.fetchall()

        print("Loading RSVP events from the database...")
        for event in events:
            self.event_messages[event["message_id"]] = event["channel_id"]

            event_data = {
                "event_id": event["event_id"],
                "name": event["name"],
                "crew_name": event["crew_name"],
                "flyer": event["flyer_url"],
                "crew_logo": event["crew_logo_url"],
                "location": event["location"],
                "date": self.ensure_datetime(event["event_date"]),
                "start_time": self.ensure_datetime(event["start_time"]),
                "end_time": self.ensure_datetime(event["end_time"]),
                "age_requirement": event["age_requirement"],
                "cover_fee": event["cover_fee"],
                "info": event["contact_info"],
                "type": event["event_type"],
            }
            reminder_time = self.ensure_datetime(event["reminder_time"])
            self.reminders.append((reminder_time, event["channel_id"], event["message_id"], event_data))
            print(f"Loaded event: {event_data['name']} (Message ID: {event['message_id']})")

        print(f"Finished loading {len(events)} events into RSVP system.")

    async def register_event(self, message_id, channel_id, reminder_time, event_data):
        """Register a new event dynamically."""
        self.event_messages[message_id] = channel_id
        self.reminders.append((reminder_time, channel_id, message_id, event_data))
        print(f"New event registered: {event_data['name']} (Message ID: {message_id})")

    async def register_rsvp(self, event_id, user_id):
        """Save RSVP details to the database."""
        cursor = self.bot.conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO rsvp_users (event_id, user_id, rsvp_time)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE rsvp_time = VALUES(rsvp_time)
            """, (event_id, user_id, datetime.now(UTC)))
            self.bot.conn.commit()
            print(f"User {user_id} RSVP'd to event {event_id}.")
        except Exception as e:
            print(f"Failed to save RSVP for user {user_id} to event {event_id}: {e}")

    @tasks.loop(seconds=30)
    async def reminder_task(self):
        """Send reminders for events."""
        print(f"[Reminder Task] Loop started at {datetime.now(UTC)}")
        now_utc = datetime.now(UTC)
        print(f"[Reminder Task] Current Time (UTC): {now_utc}")
        reminders_to_remove = []

        for reminder in self.reminders:
            reminder_time_utc, channel_id, message_id, event_data = reminder
            print(f"[Reminder Task] Checking Reminder:")
            print(f"    Event Name: {event_data['name']}")
            print(f"    Reminder Time (UTC): {reminder_time_utc}")
            print(f"    Current Time (UTC): {now_utc}")
            print(f"    Channel ID: {channel_id}")
            print(f"    Message ID: {message_id}")

            # Check if it's time to send the reminder
            if now_utc >= reminder_time_utc:
                print(f"[Reminder Task] Triggering reminder for event: {event_data['name']}")
                cursor = self.bot.conn.cursor(dictionary=True)
                cursor.execute("""
                    SELECT user_id FROM rsvp_users
                    WHERE event_id = %s
                """, (event_data["event_id"],))
                users = cursor.fetchall()

                print(f"[Reminder Task] Found {len(users)} user(s) to notify.")

                for user in users:
                    discord_user = self.bot.get_user(int(user["user_id"]))
                    if discord_user:
                        try:
                            start_time_pst = event_data["start_time"].astimezone(PST)
                            print(f"[Reminder Task] Sending reminder to user: {discord_user.name}")
                            await discord_user.send(
                                f"Reminder: The event '{event_data['name']}' is happening soon! Here are the details:\n\n"
                                f"**Location**: {event_data['location']}\n"
                                f"**Date**: {start_time_pst.strftime('%m-%d-%Y')}\n"
                                f"**Start Time**: {start_time_pst.strftime('%I:%M %p')} PST\n"
                                f"**Contact Info**: {event_data['info']}"
                            )
                            print(f"[Reminder Task] Reminder sent to {discord_user.name} for Event: {event_data['name']}")
                        except discord.Forbidden:
                            print(f"[Reminder Task] Failed to send reminder to {discord_user.name}. DMs might be disabled.")

                cursor.execute("UPDATE events SET reminder_sent = true WHERE event_id = %s", (event_data["event_id"],))
                self.bot.conn.commit()
                print(f"[Reminder Task] Updated reminder_sent in database for event: {event_data['name']}")
                reminders_to_remove.append(reminder)

        # Clean up reminders that were sent
        for reminder in reminders_to_remove:
            self.reminders.remove(reminder)
            print(f"[Reminder Task] Removed reminder for Event: {reminder[3]['name']} from active reminders.")

        print(f"[Reminder Task] Loop ended at {datetime.now(UTC)}")

    @tasks.loop(minutes=5)
    async def cleanup_task(self):
        """Clean up expired events."""
        now_pst = datetime.now(PST)
        cursor = self.bot.conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT event_id, message_id, channel_id
            FROM events
            WHERE event_date < %s OR (event_date = %s AND end_time < %s)
        """, (now_pst.date(), now_pst.date(), now_pst.time()))

        expired_events = cursor.fetchall()
        for event in expired_events:
            channel = self.bot.get_channel(event["channel_id"])
            if channel:
                try:
                    message = await channel.fetch_message(event["message_id"])
                    await message.delete()
                    print(f"Deleted expired event message ID {event['message_id']} in channel {event['channel_id']}.")
                except (discord.NotFound, discord.Forbidden):
                    print(f"Failed to delete message ID {event['message_id']}. It might not exist.")

            cursor.execute("DELETE FROM events WHERE event_id = %s", (event["event_id"],))
            self.bot.conn.commit()

    @tasks.loop(minutes=1)
    async def event_monitor_task(self):
        """Check for new events and add them to memory."""
        print("Monitoring for new events...")
        cursor = self.bot.conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM events
            WHERE reminder_sent = false AND message_id NOT IN (%s)
        """, (tuple(self.event_messages.keys()) or (0,)))
        events = cursor.fetchall()

        for event in events:
            self.event_messages[event["message_id"]] = event["channel_id"]
            event_data = {
                "event_id": event["event_id"],
                "name": event["name"],
                "crew_name": event["crew_name"],
                "flyer": event["flyer_url"],
                "crew_logo": event["crew_logo_url"],
                "location": event["location"],
                "date": self.ensure_datetime(event["event_date"]),
                "start_time": self.ensure_datetime(event["start_time"]),
                "end_time": self.ensure_datetime(event["end_time"]),
                "age_requirement": event["age_requirement"],
                "cover_fee": event["cover_fee"],
                "info": event["contact_info"],
                "type": event["event_type"],
            }
            reminder_time = self.ensure_datetime(event["reminder_time"])
            self.reminders.append((reminder_time, event["channel_id"], event["message_id"], event_data))
            print(f"New event added: {event_data['name']} (Message ID: {event['message_id']})")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Handle RSVP reactions."""
        if payload.message_id in self.event_messages and str(payload.emoji) == "✅":
            guild = self.bot.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)

            cursor = self.bot.conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT event_id FROM events
                WHERE message_id = %s
            """, (payload.message_id,))
            event = cursor.fetchone()

            if event and member:
                await self.register_rsvp(event["event_id"], payload.user_id)
                try:
                    await member.send(
                        "You have successfully RSVPed to the event! We'll send you a reminder closer to the event date."
                    )
                    print(f"RSVP confirmation sent to {member.name}.")
                except discord.Forbidden:
                    print(f"Failed to send RSVP confirmation to {member.name}. DMs might be disabled.")

async def setup(bot):
    cog = RSVPCog(bot)
    await cog.load_rsvp_events()
    await bot.add_cog(cog)
    bot.rsvp_cog = cog  # Expose RSVP Cog for interaction with other cogs
    print("RSVPCog setup complete.")