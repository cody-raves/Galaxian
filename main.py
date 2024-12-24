import discord
from discord.ext import commands
import mysql.connector
import asyncio
from datetime import datetime
import pytz
import time

# Initialize the bot
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True
intents.invites = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Set up MySQL database connection
try:
    conn = mysql.connector.connect(
        host='-',         # Replace with your server IP or hostname
        user='-',         # Replace with your MySQL username
        password='-',     # Replace with your MySQL password
        database='-'      # Replace with your MySQL database name
    )
    cursor = conn.cursor()

    # Create tables if they do not exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS embeds (
        id VARCHAR(255) PRIMARY KEY,
        message_id BIGINT,
        channel_id BIGINT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS invites (
        user_id VARCHAR(255) PRIMARY KEY,
        last_invite DATETIME,
        invite_url TEXT,
        inviter VARCHAR(255),
        invitee TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS events (
        event_id INT PRIMARY KEY AUTO_INCREMENT,
        name VARCHAR(255) NOT NULL,
        crew_name VARCHAR(255) NOT NULL,
        flyer_url TEXT,
        crew_logo_url TEXT,
        location VARCHAR(255),
        event_date DATE,
        start_time TIME,
        end_time TIME,
        age_requirement VARCHAR(10),
        cover_fee VARCHAR(255),
        reminder_time DATETIME,
        contact_info TEXT,
        event_type VARCHAR(255),
        message_id BIGINT,
        channel_id BIGINT,
        reminder_sent BOOLEAN DEFAULT FALSE
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS rsvp_users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        event_id INT NOT NULL,
        user_id BIGINT NOT NULL,
        rsvp_time DATETIME NOT NULL,
        FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE
    )
    ''')

    conn.commit()

    # Attach connection to bot
    bot.conn = conn
    bot.cursor = cursor

except mysql.connector.Error as err:
    print(f"Error: Could not connect to the database. {err}")
    exit(1)

# Load extensions (cogs)
async def load_cogs():
    for cog in ["cogs.embed_management", "cogs.event_management", "cogs.invite_system", "cogs.rsvp_system"]:
        try:
            await bot.load_extension(cog)
            print(f"Loaded cog: {cog}")
        except Exception as e:
            print(f"Failed to load cog {cog}: {e}")

    # Add confirmation messages after each successful load
    if "cogs.event_management" in bot.cogs:
        print("EventCog has successfully connected and is ready.")
    if "cogs.invite_system" in bot.cogs:
        print("InviteSystemCog has successfully connected and is ready.")
    if "cogs.embed_management" in bot.cogs:
        print("EmbedManagementCog has successfully connected and is ready.")
    if "cogs.rsvp_system" in bot.cogs:
        print("RSVPCog has successfully connected and is ready.")

@bot.event
async def on_ready():
    print(f"{bot.user.name} has connected to Discord and is ready.")

    # Log time information
    # System time
    system_time = time.ctime()
    tz_name = time.tzname

    # UTC time
    utc_now = datetime.now(pytz.utc)

    # PST time
    pst = pytz.timezone('America/Los_Angeles')
    pst_now = utc_now.astimezone(pst)

    # Log to console
    print(f"System time: {system_time} (Time Zone: {tz_name})")
    print(f"Current UTC time: {utc_now}")
    print(f"Current PST time: {pst_now}")

    # Optional: Send to a Discord channel
    channel_id = 123456789012345678  # Replace with your testing channel ID
    channel = bot.get_channel(channel_id)
    if channel:
        await channel.send(
            f"**Bot Startup Time**:\n"
            f"System time: {system_time} (Time Zone: {tz_name})\n"
            f"Current UTC time: {utc_now.strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
            f"Current PST time: {pst_now.strftime('%Y-%m-%d %I:%M %p')} PST"
        )

@bot.event
async def on_close():
    conn.close()
    print("Database connection closed.")

# Running the bot
if __name__ == "__main__":
    asyncio.run(load_cogs())
    bot.run("-")  # Replace with your bot token
