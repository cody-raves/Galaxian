import discord
from discord.ext import commands, tasks
import mysql.connector
from mysql.connector import Error
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
intents.presences = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Function to create a MySQL connection
def connect_to_database():
    try:
        conn = mysql.connector.connect(
            host='-',         # Replace with your server IP or hostname
            user='-',         # Replace with your MySQL username
            password='-',     # Replace with your MySQL password
            database='-'      # Replace with your MySQL database name
        )
        print("Connected to the database successfully.")
        return conn
    except mysql.connector.Error as err:
        print(f"Error: Could not connect to the database. {err}")
        return None

# Set up MySQL database connection
conn = connect_to_database()
if conn is None:
    print("Failed to establish a database connection. Exiting.")
    exit(1)

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
    start_time DATETIME,
    end_time DATETIME,
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

# Connection monitoring task
@tasks.loop(minutes=1)
async def monitor_database_connection():
    """Ensure the MySQL connection remains active."""
    global conn, cursor
    try:
        conn.ping(reconnect=True, attempts=3, delay=2)
        print("Database connection is active.")
    except Error as err:
        print(f"Database connection lost: {err}. Reconnecting...")
        conn = connect_to_database()
        if conn:
            cursor = conn.cursor()
            bot.conn = conn
            bot.cursor = cursor
            print("Database reconnected successfully.")

# Load extensions (cogs)
async def load_cogs():
    cogs = ["cogs.embed_management", "cogs.event_management", "cogs.invite_system", "cogs.rsvp_system"]
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            print(f"Loaded cog: {cog}")
        except Exception as e:
            print(f"Failed to load cog {cog}: {e}")

@bot.event
async def on_ready():
    print(f"{bot.user.name} has connected to Discord and is ready.")

    # Log time information
    system_time = time.ctime()
    tz_name = time.tzname
    utc_now = datetime.now(pytz.utc)
    pst = pytz.timezone('America/Los_Angeles')
    pst_now = utc_now.astimezone(pst)

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

    # Start the database monitoring task
    monitor_database_connection.start()

    # Load cogs dynamically
    await load_cogs()

    # Check if RSVPCog is loaded and run initialization tasks
    rsvp_cog = bot.get_cog('RSVPCog')
    if rsvp_cog:
        await rsvp_cog.load_rsvp_events()
        await rsvp_cog.sync_reactions_on_startup()

    print("All systems are go!")

@bot.event
async def on_disconnect():
    conn.close()
    print("Database connection closed.")

# Running the bot
if __name__ == "__main__":
    bot.run("-")  # Replace with your bot token
