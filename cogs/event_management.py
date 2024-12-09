import discord
from discord.ext import commands
from datetime import datetime, timedelta
import pytz

PST = pytz.timezone('America/Los_Angeles')

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
