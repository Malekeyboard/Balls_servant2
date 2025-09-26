# main.py


import os
import sqlite3
import datetime as dt
from contextlib import closing

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

# ===================== CONFIG =====================
LEADERBOARD_LIMIT = 20
TRACK_CHANNEL_ID = 1369502239156207619

# Daily MVP role (set to a role id to enable; set to None to disable auto-crown)
MVP_ROLE_ID = None


DAILY_CROWN_HOUR = 0
DAILY_CROWN_MINUTE = 5


MY_GUILD_ID = 1369502239156207616
# ==================================================

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

DB_PATH = os.path.join(os.path.dirname(__file__), "discord_daily.db")

@bot.tree.command(name="set_mvp_role", description="(Admin) Set the MVP role for this server.")
@discord.app_commands.describe(role="The role to use as MVP")
@discord.app_commands.default_permissions(manage_guild=True)
async def set_mvp_role(interaction: discord.Interaction, role: discord.Role):
    global MVP_ROLE_ID
    MVP_ROLE_ID = role.id
    await interaction.response.send_message(
        f"✅ MVP role has been updated to {role.mention}", ephemeral=True  # type: ignore
    )

# ===================== DB =====================

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_db():
    with closing(db()) as conn, conn:
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS message_counts(
            user_id    INTEGER NOT NULL,
            guild_id   INTEGER NOT NULL,
            day_key    TEXT    NOT NULL,   -- YYYY-MM-DD
            count      INTEGER NOT NULL,
            PRIMARY KEY(user_id, guild_id, day_key)
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS meta(
            guild_id INTEGER NOT NULL,
            key      TEXT    NOT NULL,
            value    TEXT,
            PRIMARY KEY(guild_id, key)
        )""")

def today_key() -> str:
    return dt.date.today().isoformat()

def day_key_of(d: dt.date) -> str:
    return d.isoformat()

def record_message(user_id: int, guild_id: int):
    key = today_key()
    with closing(db()) as conn, conn:
        conn.execute("""
        INSERT INTO message_counts(user_id, guild_id, day_key, count)
        VALUES(?, ?, ?, 1)
        ON CONFLICT(user_id, guild_id, day_key)
        DO UPDATE SET count = count + 1
        """, (user_id, guild_id, key))

def get_leaderboard_for_day(guild_id: int, the_day: dt.date, limit: int = LEADERBOARD_LIMIT):
    key = day_key_of(the_day)
    with closing(db()) as conn:
        cur = conn.execute("""
        SELECT user_id, count FROM message_counts
        WHERE guild_id=? AND day_key=?
        ORDER BY count DESC
        LIMIT ?
        """, (guild_id, key, limit))
        return [(r["user_id"], r["count"]) for r in cur.fetchall()]

def pick_day_winner(guild_id: int, the_day: dt.date) -> tuple[int | None, int]:
    key = day_key_of(the_day)
    with closing(db()) as conn:
        cur = conn.execute("""
        SELECT user_id, count FROM message_counts
        WHERE guild_id=? AND day_key=?
        ORDER BY count DESC
        LIMIT 1
        """, (guild_id, key))
        row = cur.fetchone()
        if row:
            return row["user_id"], row["count"]
    return None, 0

def meta_get(guild_id: int, key: str) -> str | None:
    with closing(db()) as conn:
        cur = conn.execute("SELECT value FROM meta WHERE guild_id=? AND key=?", (guild_id, key))
        row = cur.fetchone()
        return row["value"] if row else None

def meta_set(guild_id: int, key: str, value: str | None):
    with closing(db()) as conn, conn:
        if value is None:
            conn.execute("DELETE FROM meta WHERE guild_id=? AND key=?", (guild_id, key))
        else:
            conn.execute("""
            INSERT INTO meta(guild_id, key, value) VALUES(?, ?, ?)
            ON CONFLICT(guild_id, key) DO UPDATE SET value=excluded.value
            """, (guild_id, key, value))


# ===================== Helpers =====================

async def get_member_safe(guild: discord.Guild, user_id: int) -> discord.Member | None:
    m = guild.get_member(user_id)
    if m:
        return m
    try:
        return await guild.fetch_member(user_id)
    except (discord.NotFound, discord.Forbidden):
        return None


# ===================== Events =====================

@bot.event
async def on_ready():
    ensure_db()
    try:
        await bot.tree.sync()
    except Exception as e:
        print("Slash sync error:", e)
    print(f"Logged in as {bot.user} (id={bot.user.id}) >:)))")
    if MVP_ROLE_ID:
        daily_crown_loop.start()

@bot.event
async def on_message(message: discord.Message):
    # Count ONLY messages in the configured channel
    if (
        message.author.bot
        or not message.guild
        or message.channel.id != TRACK_CHANNEL_ID
    ):
        return
    record_message(message.author.id, message.guild.id)
    await bot.process_commands(message)



#GUILD TAG DETECTION BY YOURS TRULLYYY
#PLEASE ACKNOWLEDGE TS I SPENT LIKE 2 WHOLE ASS HOURS TRYING TO FIGURE IT OUT
MY_GUILD_ID = 1369502239156207616
TAG_ANNOUNCE_CHANNEL_ID = 1369502239156207619

@bot.event
async def on_user_update(before: discord.User, after: discord.User):
    b_pg = getattr(before, "primary_guild", None)
    a_pg = getattr(after, "primary_guild", None)
    b_id = getattr(b_pg, "id", None)
    a_id = getattr(a_pg, "id", None)


    if b_id == a_id:
        return

    guild = bot.get_guild(MY_GUILD_ID)
    if not guild:
        return


    channel = guild.get_channel(TAG_ANNOUNCE_CHANNEL_ID) or guild.system_channel \
        or next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)
    if not channel:
        return

    member = guild.get_member(after.id) or await get_member_safe(guild, after.id)
    mention = member.mention if member else f"<@{after.id}>"


    if a_id == MY_GUILD_ID:
        await channel.send(f"🏷️ {mention} just equipped <:balls:1370161168622162121> as their **primary tag**! "
                           f"PRAISE THE BALLLS!!!")
        return


    if b_id == MY_GUILD_ID and a_id != MY_GUILD_ID:
        await channel.send(f"❌ {mention} removed THEIR GUILD TAG, THE COURT DECLARES HERESY, "
                           f"BUGGER THEIR CORPSE RAHHHH")
        return


# ===================== Auto-crown loop (Daily MVP) =====================

@tasks.loop(minutes=1)
async def daily_crown_loop():
    now = dt.datetime.now()
    if now.hour == DAILY_CROWN_HOUR and now.minute == DAILY_CROWN_MINUTE:
        for guild in bot.guilds:
            await crown_daily_mvp(guild)

async def crown_daily_mvp(guild: discord.Guild):
    if not MVP_ROLE_ID:
        return
    mvp_role = guild.get_role(MVP_ROLE_ID)
    if not mvp_role:
        return
    if not guild.me.guild_permissions.manage_roles or mvp_role >= guild.me.top_role:
        return

    yesterday = dt.date.today() - dt.timedelta(days=1)
    winner_id, count = pick_day_winner(guild.id, yesterday)

    # remove old holder
    prev_id = meta_get(guild.id, "daily_mvp")
    if prev_id:
        prev_member = await get_member_safe(guild, int(prev_id))
        if prev_member and mvp_role in prev_member.roles:
            try:
                await prev_member.remove_roles(mvp_role, reason="New daily MVP")
            except discord.Forbidden:
                pass

    if not winner_id:
        meta_set(guild.id, "daily_mvp", None)
        channel = guild.system_channel or next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)
        if channel:
            await channel.send("No messages yesterday—no Daily MVP.")
        return

    winner = await get_member_safe(guild, winner_id)
    if not winner:
        return
    try:
        await winner.add_roles(mvp_role, reason="Daily top chatter")
        meta_set(guild.id, "daily_mvp", str(winner_id))
    except discord.Forbidden:
        return

    channel = guild.system_channel or next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)
    if channel:
        await channel.send(f"🥇 **Daily MVP:** {winner.mention} with **{count}** messages! {mvp_role.mention} consecrated, good job. Now go TAKE A GODDAMN SHOWER HOLY.")


# ===================== Slash commands =====================

@bot.tree.command(name="daily", description="Show today's jobless lot (only for main-chat).")
async def daily_cmd(interaction: discord.Interaction):
    rows = get_leaderboard_for_day(interaction.guild_id, dt.date.today())
    if not rows:
        await interaction.response.send_message(
            "*you hear crickets chirping* No messages today :(",
            ephemeral=True  # type: ignore
        )
        return

    lines = []
    for i, (uid, cnt) in enumerate(rows, 1):
        m = interaction.guild.get_member(uid)
        name = m.mention if m else f"<@{uid}>"
        lines.append(f"**{i}.** {name} — {cnt}")

    embed = discord.Embed(
        title="📊 Today’s jobless lot:",
        description="\n".join(lines),
        color=discord.Color.blurple()
    )
    ch = interaction.guild.get_channel(TRACK_CHANNEL_ID)
    if ch:
        embed.set_footer(text=f"Counting messages only in: #{ch.name}")
    await interaction.response.send_message(embed=embed)  # type: ignore

@bot.tree.command(name="crown_now", description="(Admin) Crown MVP now for 'today' or 'yesterday'.")
@discord.app_commands.describe(scope="Choose 'today' or 'yesterday'")
@discord.app_commands.default_permissions(manage_guild=True)
async def crown_now(interaction: discord.Interaction, scope: str = "today"):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("Run this in a server, dumbass.", ephemeral=True)  # type: ignore
        return

    if not MVP_ROLE_ID:
        await interaction.response.send_message("Daily crowning is disabled (MVP_ROLE_ID is None).", ephemeral=True)  # type: ignore
        return

    mvp_role = guild.get_role(MVP_ROLE_ID)
    if not mvp_role:
        await interaction.response.send_message("MVP role not found. Check MVP_ROLE_ID.", ephemeral=True)  # type: ignore
        return
    if not guild.me.guild_permissions.manage_roles:
        await interaction.response.send_message("I need **Manage Roles**.", ephemeral=True)  # type: ignore
        return
    if mvp_role >= guild.me.top_role:
        await interaction.response.send_message("Move my role **above** the MVP role.", ephemeral=True)  # type: ignore
        return

    scope = (scope or "today").strip().lower()
    the_day = dt.date.today() if scope == "today" else (dt.date.today() - dt.timedelta(days=1))
    label = "today" if scope == "today" else "yesterday"

    winner_id, count = pick_day_winner(guild.id, the_day)

    # remove current holder
    prev_id = meta_get(guild.id, "daily_mvp")
    if prev_id:
        prev_member = await get_member_safe(guild, int(prev_id))
        if prev_member and mvp_role in prev_member.roles:
            try:
                await prev_member.remove_roles(mvp_role, reason="Manual daily crown")
            except discord.Forbidden:
                pass

    if not winner_id:
        await interaction.response.send_message(f"No eligible messages {label}.", ephemeral=True)  # type: ignore
        return

    winner = await get_member_safe(guild, winner_id)
    if not winner:
        await interaction.response.send_message("Could not fetch the winner’s member object.", ephemeral=True)  # type: ignore
        return

    try:
        await winner.add_roles(mvp_role, reason="Manual daily crown")
        meta_set(guild.id, "daily_mvp", str(winner_id))
    except discord.Forbidden:
        await interaction.response.send_message("I was blocked from assigning the MVP role.", ephemeral=True)  # type: ignore
        return

    await interaction.response.send_message(  # type: ignore
        f"🥇 Crowned {winner.mention} as {label}'s today's <:balls:1370161168622162121>  loyalist/addict with **{count}** messages! {mvp_role.mention} congratulate them! (god it fucking stinks here, go take a shower you moron)"
    )


from discord.ext import tasks

# === HOURLY LEADERBOARD ANNOUNCER ===
ANNOUNCE_CHANNEL_ID = 1369502239156207619# replace with your channel's ID

@tasks.loop(hours=1)
async def announce_leaderboard():
    for guild in bot.guilds:
        rows = get_leaderboard_for_day(guild.id, dt.date.today())
        if not rows:
            continue

        # Build the leaderboard text
        lines = []
        for i, (uid, cnt) in enumerate(rows, 1):
            member = guild.get_member(uid)
            name = member.mention if member else f"<@{uid}>"
            lines.append(f"**{i}.** {name} — {cnt}")

        embed = discord.Embed(
            title="The hall of shame: <:Fnaf:1374428051227807744> (hourly) ",
            description="\n".join(lines),
            color=discord.Color.green()
        )
        embed.set_footer(text="please take a shower :D (counting messages only in main-chat)")

        # Always send in the specific channel
        channel = guild.get_channel(ANNOUNCE_CHANNEL_ID)
        if channel and channel.permissions_for(guild.me).send_messages:
            await channel.send(embed=embed)

# start the loop once the bot is ready
@bot.event
async def on_ready():
    ensure_db()
    try:
        await bot.tree.sync()
    except Exception as e:
        print("Slash sync error:", e)
    print(f"✅ Logged in as {bot.user} (id={bot.user.id})")
    if not announce_leaderboard.is_running():
        announce_leaderboard.start()









# ===================== RUN =====================

if __name__ == "__main__":
    ensure_db()
    bot.run(TOKEN)