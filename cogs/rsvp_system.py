import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, date
import pytz
import asyncio

PST = pytz.timezone('America/Los_Angeles')
UTC = pytz.utc

class RSVPCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reminders = []  # List of reminders: [(reminder_time, channel_id, message_id, event_data)]
        self.event_messages = {}  # Track event embeds (message_id -> channel_id)

        try:
            print("Attempting to start reminder task...")
            if self.reminder_task.is_running():
                self.reminder_task.stop()
            self.reminder_task.start()
            print("Reminder task started.")
        except Exception as e:
            print(f"Failed to start reminder task: {e}")

        try:
            print("Attempting to start cleanup task...")
            if self.cleanup_task.is_running():
                self.cleanup_task.stop()
            self.cleanup_task.start()
            print("Cleanup task started.")
        except Exception as e:
            print(f"Failed to start cleanup task: {e}")

        try:
            print("Attempting to start event monitor task...")
            if self.event_monitor_task.is_running():
                self.event_monitor_task.stop()
            self.event_monitor_task.start()
            print("Event monitor task started.")
        except Exception as e:
            print(f"Failed to start event monitor task: {e}")

        try:
            print("Attempting to start time logger task...")
            if self.time_logger_task.is_running():
                self.time_logger_task.stop()
            self.time_logger_task.start()
            print("Time logger task started.")
        except Exception as e:
            print(f"Failed to start time logger task: {e}")

        try:
            print("Attempting to start status update task...")
            if self.update_status_task.is_running():
                self.update_status_task.stop()
            self.update_status_task.start()
            print("Status update task started.")
        except Exception as e:
            print(f"Failed to start status update task: {e}")

        print("RSVPCog initialized and tasks started.")

    @tasks.loop(seconds=59)
    async def update_status_task(self):
        """Update bot status to indicate reminder loop status."""
        try:
            print(f"[Status Task] Loop triggered at {datetime.now()}. Checking reminder_task status...")
            if self.reminder_task.is_running():
                print("[Status Task] Reminder task is running.")
                status_message = "🟢"
            else:
                print("[Status Task] Reminder task is NOT running.")
                status_message = "🔴"
            
            # Set activity with status message
            activity = discord.Activity(type=discord.ActivityType.watching, name=status_message)
            await self.bot.change_presence(activity=activity)
            print(f"[Status Task] Status updated to: {status_message}")
        except Exception as e:
            print(f"[Status Task] Error updating status: {e}")

    def cog_unload(self):
        if self.reminder_task.is_running():
            self.reminder_task.cancel()
        if self.cleanup_task.is_running():
            self.cleanup_task.cancel()
        if self.event_monitor_task.is_running():
            self.event_monitor_task.cancel()
        if self.time_logger_task.is_running():
            self.time_logger_task.cancel()
        if self.update_status_task.is_running():
            self.update_status_task.cancel()
        print("RSVPCog tasks unloaded.")

    def ensure_datetime(self, value):
        """Ensure the value is a datetime object."""
        if isinstance(value, datetime):
            if value.tzinfo is None:  # If naive, assume UTC
                return value.replace(tzinfo=UTC)
            return value
        if isinstance(value, str):
            dt = datetime.fromisoformat(value)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)  # Assume UTC if naive
        if isinstance(value, date):  # Handle date type
            return datetime.combine(value, datetime.min.time(), UTC)
        if isinstance(value, timedelta):  # Handle timedelta type
            return datetime.min + value
        if value is None:
            raise ValueError("Encountered None when expecting a datetime string or object.")
        raise TypeError(f"Unsupported type for datetime conversion: {type(value)}")

    async def load_rsvp_events(self):
        """Load existing events and reminders into memory at startup."""
        cursor = self.bot.conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT *
            FROM events
            WHERE reminder_sent = false
        """)
        events = cursor.fetchall()

        print("Loading RSVP events from the database...")
        self.reminders.clear()  # Clear existing reminders to avoid duplication
        for event in events:
            try:
                reminder_time = self.ensure_datetime(event["reminder_time"])
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
                self.reminders.append((reminder_time, event["channel_id"], event["message_id"], event_data))
                self.event_messages[event["message_id"]] = event["channel_id"]
                print(f"Loaded event: {event_data['name']} (Message ID: {event['message_id']}, Reminder Time: {reminder_time})")
            except Exception as e:
                print(f"Error loading event ID {event['event_id']}: {e}")

        print(f"Finished loading {len(self.reminders)} reminders into memory.")

    async def register_event(self, message_id, channel_id, reminder_time, event_data):
        """Register a new event dynamically."""
        self.event_messages[message_id] = channel_id
        self.reminders.append((reminder_time, channel_id, message_id, event_data))
        print(f"New event registered: {event_data['name']} (Message ID: {message_id})")

    async def register_rsvp(self, event_id, user_id):
        """Save RSVP details to the database."""
        cursor = self.bot.conn.cursor(dictionary=True)
        try:
            # Check if the user has already RSVP'd
            cursor.execute("""
                SELECT * FROM rsvp_users
                WHERE event_id = %s AND user_id = %s
            """, (event_id, user_id))
            existing_rsvp = cursor.fetchone()

            if existing_rsvp:
                print(f"User {user_id} has already RSVP'd to event {event_id}. Skipping duplicate entry.")
                # Notify the user about the duplicate RSVP
                user = self.bot.get_user(user_id)
                if user:
                    try:
                        await user.send("You have already RSVP'd to this event!")
                    except discord.Forbidden:
                        print(f"Unable to notify user {user_id} about duplicate RSVP.")
                return

            # Insert new RSVP
            cursor.execute("""
                INSERT INTO rsvp_users (event_id, user_id, rsvp_time)
                VALUES (%s, %s, %s)
            """, (event_id, user_id, datetime.now(UTC)))
            self.bot.conn.commit()
            print(f"User {user_id} RSVP'd to event {event_id}.")
        except Exception as e:
            print(f"Failed to save RSVP for user {user_id} to event {event_id}: {e}")

    @tasks.loop(seconds=59)
    async def reminder_task(self):
        """Send reminders for events."""
        print("[Reminder Task] Task initiated and running.")
        try:
            now_utc = datetime.now(UTC)
            print(f"[Reminder Task] Current Time (UTC): {now_utc}")

            if not self.reminders:
                print("[Reminder Task] No reminders currently loaded.")
            else:
                print(f"[Reminder Task] Processing {len(self.reminders)} reminders.")

            reminders_to_remove = []
            for reminder in self.reminders:
                reminder_time_utc, channel_id, message_id, event_data = reminder
                if now_utc >= reminder_time_utc and not event_data.get("reminder_sent", False):
                    print(f"[Reminder Task] Sending reminders for event: {event_data['name']} (Event ID: {event_data['event_id']})")

                    # Fetch RSVP users for the event dynamically
                    cursor = self.bot.conn.cursor(dictionary=True)
                    cursor.execute("""
                        SELECT user_id
                        FROM rsvp_users
                        WHERE event_id = %s
                    """, (event_data["event_id"],))
                    rsvp_users = cursor.fetchall()

                    if rsvp_users:
                        for user in rsvp_users:
                            user_id = user["user_id"]
                            member = self.bot.get_user(user_id)
                            if member:
                                try:
                                    start_time_pst = event_data["start_time"].astimezone(PST)
                                    await member.send(
                                        f"Reminder: The event '{event_data['name']}' is happening soon! Here are the details:\n\n"
                                        f"**Location**: {event_data['location']}\n"
                                        f"**Date**: {start_time_pst.strftime('%m-%d-%Y')}\n"
                                        f"**Start Time**: {start_time_pst.strftime('%I:%M %p')} PST\n"
                                        f"**Contact Info**: {event_data['info']}"
                                    )
                                    print(f"Reminder sent to {member.name} for Event: {event_data['name']}")
                                except discord.Forbidden:
                                    print(f"Failed to send reminder to {member.name}. DMs might be disabled.")
                    else:
                        print(f"No RSVP users found for Event ID: {event_data['event_id']}")

                    # Mark reminder as sent in the database
                    cursor.execute("UPDATE events SET reminder_sent = true WHERE event_id = %s", (event_data["event_id"],))
                    self.bot.conn.commit()

                    reminders_to_remove.append(reminder)

            for reminder in reminders_to_remove:
                self.reminders.remove(reminder)
                print(f"[Reminder Task] Reminder removed for Event: {reminder[3]['name']}")

        except Exception as e:
            print(f"[Reminder Task] Encountered an error: {e}")

    @tasks.loop(minutes=5)
    async def cleanup_task(self):
        """Delete event messages from Discord after the event has ended."""
        now_utc = datetime.now(UTC)
        cursor = self.bot.conn.cursor(dictionary=True)

        try:
            # Fetch events where the end_time has passed
            cursor.execute("""
                SELECT event_id, message_id, channel_id, name, end_time
                FROM events
                WHERE end_time <= %s
            """, (now_utc,))

            expired_events = cursor.fetchall()

            for event in expired_events:
                channel = self.bot.get_channel(event["channel_id"])
                if channel:
                    try:
                        # Fetch the message and delete it
                        message = await channel.fetch_message(event["message_id"])
                        await message.delete()
                        print(f"Deleted event message: {event['name']} (Message ID: {event['message_id']})")
                    except discord.NotFound:
                        print(f"Message not found for event: {event['name']} (Message ID: {event['message_id']}).")
                    except discord.Forbidden:
                        print(f"Permission denied to delete message for event: {event['name']} (Message ID: {event['message_id']}).")
                    except Exception as e:
                        print(f"Unexpected error while deleting message for event {event['name']}: {e}")

                # Optionally mark the event as processed
                cursor.execute("UPDATE events SET reminder_sent = true WHERE event_id = %s", (event["event_id"],))
                self.bot.conn.commit()

        except Exception as e:
            print(f"[Cleanup Task] Error during cleanup: {e}")

    @tasks.loop(seconds=30)
    async def time_logger_task(self):
        """Log the current time every 30 seconds."""
        while True:
            now_utc = datetime.now(UTC)
            now_pst = datetime.now(PST)
            print(f"[Time Logger Task] Current Time (UTC): {now_utc}")
            print(f"[Time Logger Task] Current Time (PST): {now_pst}")
            await asyncio.sleep(30)

    @tasks.loop(minutes=1)
    async def event_monitor_task(self):
        """Check for new events and add them to memory."""
        try:
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
        except Exception as e:
            print(f"[Event Monitor Task] Encountered an error: {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Handle RSVP reactions."""
        if payload.message_id in self.event_messages and str(payload.emoji) == "✅":
            guild = self.bot.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)

            cursor = self.bot.conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT *
                FROM events
                WHERE message_id = %s
            """, (payload.message_id,))
            event = cursor.fetchone()

            if event and member:
                await self.register_rsvp(event["event_id"], payload.user_id)

                # Check if the current time is past the reminder time
                now_utc = datetime.now(UTC)
                reminder_time = self.ensure_datetime(event["reminder_time"])

                if now_utc >= reminder_time:
                    try:
                        start_time_pst = self.ensure_datetime(event["start_time"]).astimezone(PST)
                        await member.send(
                            f"Reminder: The event '{event['name']}' is happening now or soon! Here are the details:\n\n"
                            f"**Location**: {event['location']}\n"
                            f"**Date**: {start_time_pst.strftime('%m-%d-%Y')}\n"
                            f"**Start Time**: {start_time_pst.strftime('%I:%M %p')} PST\n"
                            f"**Contact Info**: {event['contact_info']}"
                        )
                        print(f"Immediate RSVP reminder sent to {member.name} for Event: {event['name']}")
                    except discord.Forbidden:
                        print(f"Failed to send RSVP reminder to {member.name}. DMs might be disabled.")
                else:
                    try:
                        await member.send(
                            "You have successfully RSVPed to the event! We'll send you a reminder closer to the event date."
                        )
                        print(f"RSVP confirmation sent to {member.name}.")
                    except discord.Forbidden:
                        print(f"Failed to send RSVP confirmation to {member.name}. DMs might be disabled.")
                    
    @commands.command(name="test_reminder")
    async def test_reminder(self, ctx):
        """Test command to check upcoming reminders and RSVP users."""
        now_utc = datetime.now(UTC)
        # Ensure all reminders are timezone-aware for comparison
        upcoming_reminders = [reminder for reminder in self.reminders if reminder[0].astimezone(UTC) > now_utc]

        if not upcoming_reminders:
            await ctx.send("No upcoming reminders found.")
            return

        next_reminder = min(upcoming_reminders, key=lambda r: r[0])
        time_until_next = next_reminder[0] - now_utc

        # Fetch the RSVP users for the next reminder's event
        cursor = self.bot.conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT user_id FROM rsvp_users
            WHERE event_id = %s
        """, (next_reminder[3]["event_id"],))
        rsvp_users = cursor.fetchall()

        # Fetch usernames for the RSVP users
        usernames = []
        for user in rsvp_users:
            discord_user = self.bot.get_user(int(user["user_id"]))
            if discord_user:
                usernames.append(discord_user.name)
            else:
                usernames.append(f"Unknown User ({user['user_id']})")

        # Format the response
        response = (
            f"The next reminder is for event: {next_reminder[3]['name']}\n"
            f"Time until next reminder: {time_until_next}\n"
            f"RSVP Users: {', '.join(usernames) if usernames else 'No users found.'}"
        )
        await ctx.send(response)
        
async def setup(bot):
    cog = RSVPCog(bot)
    await cog.load_rsvp_events()
    await bot.add_cog(cog)
    bot.rsvp_cog = cog  # Expose RSVP Cog for interaction with other cogs
    print("RSVPCog setup complete.")