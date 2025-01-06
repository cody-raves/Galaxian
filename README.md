# **Galaxian**

_A Discord bot for managing underground rave events, invites, and RSVP's – acting like a hybrid interactive rave info line._

---

## **Features**

### **Invites**
- Handles all invites related to the server.
- Limits users to **one invite per 30 days** by reacting to a central embed.
- Each invite is a **one-time use only**.
- `Admin` Role can **bypass 30 day limits**.

### **Events**
- Users with the "Promoter" role can use the `!newevent` command in channel `events`.
- Anything typed in channel `events` gets deleted instantly if its not the command `!newevent` .
- A private channel is created to ask all relevant questions before posting the event embed when `!newevents` is triggered.
- After and event's end time the emebeds are auto deleted from the `events` channel.

### **RSVPs**
- All event posts have reaction-based RSVP functionality.
- RSVP reminders are triggered based on the time set by promoters during the event creation phase.

---

### **Technical Details**
- The bot uses **SQL** for data persistence, ensuring reliability across restarts.
- It is divided into **modular cogs** for easier debugging and updates.

### **Status Emojis**
- **SQL connected** = 📊
- **Reminders active** = 🔔

---

### **Current Limitations**
- The bot is currently hardcoded with specific channel IDs and images for a particular Discord server.
- You can easily modify these to adapt the bot to your own server.
