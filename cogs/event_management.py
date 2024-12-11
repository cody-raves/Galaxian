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
            WHERE reminder_sent = 0
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
        existing_ids = tuple(self.event_messages.keys()) or (0,)
        cursor.execute("""
            SELECT message_id, channel_id, reminder_time, name, crew_name, flyer_url, crew_logo_url, location, event_date, start_time, age_requirement, cover_fee, contact_info, event_type
            FROM events
            WHERE message_id NOT IN %s
        """, (existing_ids,))
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
                    cursor.execute("UPDATE events SET reminder_sent = 1 WHERE message_id = %s", (message_id,))
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

class EventCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def parse_time(self, input_time):
        """Parse 12-hour time input into a time object."""
        return datetime.strptime(input_time.strip().lower(), "%I:%M%p" if ":" in input_time else "%I%p").time()

    @commands.command(name="newevent")
    @commands.has_role("promoter")
    async def new_event(self, ctx):
        events_channel_id = 1306918418116771892  # Replace with your events channel ID
        is_admin = ctx.author.guild_permissions.administrator

        # Determine where to post the final embed
        if is_admin and ctx.channel.id != events_channel_id:
            post_channel = ctx.channel
        else:
            if ctx.channel.id != events_channel_id:
                await ctx.send(f"This command can only be used in <#{events_channel_id}>.")
                return
            post_channel = self.bot.get_channel(events_channel_id)

        # Create a private channel for the event setup
        guild = ctx.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            ctx.author: discord.PermissionOverwrite(read_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }

        event_channel = await guild.create_text_channel(f'event-setup-{ctx.author.display_name}', overwrites=overwrites)
        await ctx.message.delete()
        await event_channel.send(f"{ctx.author.mention}, let's set up your event!")

        event_data = {}

        async def ask_question(question, valid_responses=None):
            while True:
                await event_channel.send(question)

                def check(m):
                    return m.author == ctx.author and m.channel == event_channel

                response = await self.bot.wait_for("message", check=check)

                if not valid_responses or response.content.title() in valid_responses or response.content.strip().lower() in valid_responses:
                    return response

                await event_channel.send(f"Invalid response. Please choose from: {', '.join(valid_responses)}.")

        try:
            # Collect event details
            msg = await ask_question("Let's set up your event! Please provide the name of the party:")
            event_data["name"] = msg.content

            msg = await ask_question("Please provide a flyer (URL or upload an image):")
            event_data["flyer"] = msg.attachments[0].url if msg.attachments else msg.content

            msg = await ask_question("What DJs or live musical acts will be playing? Please separate each with a comma.")
            event_data["acts"] = [act.strip() for act in msg.content.split(",")]

            msg = await ask_question("What crew is hosting the event?")
            event_data["crew_name"] = msg.content

            msg = await ask_question("Do you have a crew logo you’d like to include? If yes, send it now as an image attachment, or reply with 'skip'.")
            if msg.content.lower() == 'skip':
                event_data["crew_logo"] = None
            else:
                event_data["crew_logo"] = msg.attachments[0].url if msg.attachments else None

            locations = ["East Bay", "South Bay", "North Bay", "The City"]
            msg = await ask_question("Please specify the general location of the event: East Bay, South Bay, North Bay, or The City.", valid_responses=locations)
            event_data["location"] = msg.content.title()

            while True:
                msg = await ask_question("Please provide the date of the event (MM-DD-YYYY):")
                try:
                    event_date = datetime.strptime(msg.content, "%m-%d-%Y").date()
                    if event_date < datetime.now(PST).date():
                        await event_channel.send("The event date cannot be in the past.")
                    else:
                        event_data["date"] = event_date
                        break
                except ValueError:
                    await event_channel.send("Invalid date format. Please use MM-DD-YYYY.")

            while True:
                msg = await ask_question("Please provide the start time of the event (e.g., 12pm or 1:30am) in PST:")
                try:
                    event_data["start_time"] = self.parse_time(msg.content)
                    break
                except ValueError:
                    await event_channel.send("Invalid time format. Please use formats like 12pm, 1:30am.")

            while True:
                msg = await ask_question("Please provide the end time of the event (e.g., 12pm or 1:30am) in PST:")
                try:
                    event_data["end_time"] = self.parse_time(msg.content)
                    break
                except ValueError:
                    await event_channel.send("Invalid time format. Please use formats like 12pm, 1:30am.")

            age_requirements = ["18+", "21+", "All Ages"]
            msg = await ask_question("What is the age requirement? (18+, 21+, All Ages)", valid_responses=age_requirements)
            event_data["age_requirement"] = msg.content.strip()

            msg = await ask_question("Is there a cover fee? Please reply with 'yes' or 'no'.", valid_responses=["yes", "no"])
            cover_fee = msg.content.strip().lower()
            if cover_fee == "yes":
                msg = await ask_question("Please specify the cover fee amount (e.g., $10):")
                event_data["cover_fee"] = msg.content.strip()
            else:
                event_data["cover_fee"] = "Free"

            msg = await ask_question("Please provide the contact info (e.g., infoline number, address, or GPS coordinates):")
            event_data["info"] = msg.content

            msg = await ask_question("What type of event is this? (e.g., club, renegade, underground, day party, campout, festival)")
            event_data["type"] = msg.content

            # Ask for reminder time
            msg = await ask_question("When should we send a reminder? (e.g., 2 hours, 30 minutes):")
            while True:
                try:
                    time_value, time_unit = msg.content.split()[0], msg.content.split()[1].lower()
                    reminder_delta = (
                        timedelta(hours=int(time_value)) if "hour" in time_unit else timedelta(minutes=int(time_value))
                    )

                    start_time_pst = PST.localize(datetime.combine(event_data["date"], event_data["start_time"]))
                    start_time_utc = start_time_pst.astimezone(pytz.utc)

                    reminder_time_utc = start_time_utc - reminder_delta
                    if reminder_time_utc < datetime.now(pytz.utc):
                        await event_channel.send("Reminder time must be in the future. Please provide a valid time.")
                        msg = await ask_question("When should we send a reminder? (e.g., 2 hours, 30 minutes):")
                    else:
                        event_data["reminder_time"] = reminder_time_utc
                        break
                except (ValueError, IndexError):
                    await event_channel.send("Invalid format. Please provide a valid time (e.g., '2 hours', '30 minutes').")
                    msg = await ask_question("When should we send a reminder? (e.g., 2 hours, 30 minutes):")

            # Create an event embed preview
            embed = discord.Embed(
                title=f"{event_data['name']} hosted by {event_data['crew_name']}",
                description="Performing Acts:\n" + "\n".join(event_data["acts"]),
                color=discord.Color.green()
            )
            embed.set_image(url=event_data["flyer"])
            if event_data["crew_logo"]:
                embed.set_thumbnail(url=event_data["crew_logo"])
            embed.add_field(name="Location", value=event_data["location"], inline=True)
            embed.add_field(name="Type", value=event_data["type"], inline=True)
            embed.add_field(name="Date", value=event_data["date"].strftime("%m-%d-%Y"), inline=True)
            embed.add_field(name="Time", value=f"{event_data['start_time'].strftime('%I:%M %p')} - {event_data['end_time'].strftime('%I:%M %p')} PST", inline=True)
            embed.add_field(name="Age Requirement", value=event_data["age_requirement"], inline=True)
            embed.add_field(name="Cover Fee", value=event_data["cover_fee"], inline=True)
            embed.add_field(
                name="RSVP",
                value="React with ✅ to RSVP and receive reminders and updates closer to the event.",
                inline=False
            )
            embed.set_footer(text="Hosted by Your Discord Server")

            # Show preview to promoter
            await event_channel.send("Here is a preview of your event post:")
            preview_message = await event_channel.send(embed=embed)

            # Ask for confirmation to post
            msg = await ask_question(
                "All set! Reply with 'confirm' to post the event, 'edit' to restart, or 'cancel' to abort.",
                valid_responses=["confirm", "edit", "cancel"]
            )
            if msg.content.lower() == "cancel":
                await event_channel.send("Event setup cancelled.")
                await event_channel.delete()
                return
            elif msg.content.lower() == "edit":
                await event_channel.send("Restarting the event setup...")
                await event_channel.delete()
                await self.new_event(ctx)
                return

            # Post event publicly
            final_message = await post_channel.send(embed=embed)
            await final_message.add_reaction("\u2705")

            # Dynamically register the event with the RSVP cog
            event_data = {
                "name": event_data["name"],
                "crew_name": event_data["crew_name"],
                "flyer": event_data["flyer"],
                "crew_logo": event_data["crew_logo"],
                "location": event_data["location"],
                "date": event_data["date"],
                "start_time": event_data["start_time"],
                "end_time": event_data["end_time"],  # Include end_time
                "age_requirement": event_data["age_requirement"],
                "cover_fee": event_data["cover_fee"],
                "info": event_data["info"],
                "type": event_data["type"],
                "reminder_time": event_data["reminder_time"],  # Include reminder time
            }

            # Call the register_event method from RSVPCog
            await self.bot.rsvp_cog.register_event(
                message_id=final_message.id,
                channel_id=post_channel.id,
                reminder_time=event_data["reminder_time"],
                event_data=event_data,
            )

            # Save to database
            cursor = self.bot.conn.cursor()
            cursor.execute('''
                INSERT INTO events (name, crew_name, flyer_url, crew_logo_url, location, event_date, start_time, end_time, age_requirement, cover_fee, contact_info, event_type, reminder_time, message_id, channel_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                event_data["name"], event_data["crew_name"], event_data["flyer"], event_data["crew_logo"], event_data["location"],
                event_data["date"], event_data["start_time"], event_data["end_time"], event_data["age_requirement"],
                event_data["cover_fee"], event_data["info"], event_data["type"], event_data["reminder_time"], final_message.id, post_channel.id
            ))
            self.bot.conn.commit()

            await event_channel.delete()

            # Send DM to promoter
            try:
                await ctx.author.send("Your event has been posted! Here is the final version:")
                await ctx.author.send(embed=embed)
            except discord.Forbidden:
                await ctx.send(f"{ctx.author.mention}, I couldn't send you a DM. Please make sure your DMs are open.")

        except Exception as e:
            print(f"An error occurred during event setup: {e}")
            if event_channel:
                await event_channel.delete()

async def setup(bot):
    await bot.add_cog(EventCog(bot))