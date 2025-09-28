# main.py

import os
import sqlite3
import datetime as dt
from contextlib import closing
import random

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

# ===================== CONFIG =====================
LEADERBOARD_LIMIT = 20
TRACK_CHANNEL_ID = 1369502239156207619
MVP_ROLE_ID=1419902849130954874
# Daily MVP role (set to a role id to enable; set to None to disable auto-crown)

DAILY_CROWN_HOUR = 0
DAILY_CROWN_MINUTE = 5

MY_GUILD_ID = 1369502239156207616
TAG_ANNOUNCE_CHANNEL_ID = 1369502239156207619

OFFICIAL_TAG = "balls"  # for /tagged_count
# ==================================================

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # make sure "Server Members Intent" is enabled in Dev Portal
bot = commands.Bot(command_prefix="!", intents=intents)

DB_PATH = os.path.join(os.path.dirname(__file__), "discord_daily.db")

# ===================== DB =====================

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_db():
    with closing(db()) as conn, conn:
        c = conn.cursor()
        # Day-based message counter
        c.execute("""
        CREATE TABLE IF NOT EXISTS message_counts(
            user_id  INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            day_key  TEXT    NOT NULL,
            count    INTEGER NOT NULL,
            PRIMARY KEY(user_id, guild_id, day_key)
        )
        """)
        # Generic key/value
        c.execute("""
        CREATE TABLE IF NOT EXISTS meta(
            guild_id INTEGER NOT NULL,
            key      TEXT    NOT NULL,
            value    TEXT,
            PRIMARY KEY(guild_id, key)
        )
        """)
        # (optional future) tag holders mirror
        c.execute("""
        CREATE TABLE IF NOT EXISTS tag_holders(
            guild_id   INTEGER NOT NULL,
            user_id    INTEGER NOT NULL,
            equipped   INTEGER NOT NULL,
            updated_at TEXT    NOT NULL,
            PRIMARY KEY(guild_id, user_id)
        )
        """)

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

# ===================== Admin: set MVP role =====================

# ===================== Events =====================

@bot.event
async def on_ready():
    ensure_db()
    try:
        G = discord.Object(id=MY_GUILD_ID)
        await bot.tree.sync(guild=G)
        print(f"✅ Synced commands to guild {MY_GUILD_ID}")
    except Exception as e:
        print("Slash sync error:", e)
    print(f"✅ Logged in as {bot.user} (id={bot.user.id})")
    if not announce_leaderboard.is_running():
        announce_leaderboard.start()


@bot.event
async def on_message(message: discord.Message):
    if (
        message.author.bot
        or not message.guild
        or message.channel.id != TRACK_CHANNEL_ID
    ):
        return

    # Record this message for today's leaderboard
    record_message(message.author.id, message.guild.id)

    # === Simple auto-assign MVP role to top chatter ===
    if MVP_ROLE_ID:
        mvp_role = message.guild.get_role(MVP_ROLE_ID)
        if not mvp_role:
            print("⚠️ MVP role not found in this guild!")
        elif not message.guild.me.guild_permissions.manage_roles:
            print("⚠️ Missing Manage Roles permission!")
        else:
            top = get_leaderboard_for_day(message.guild.id, dt.date.today(), limit=1)
            if not top:
                print("⚠️ No leaderboard data yet.")
            else:
                winner_id, _ = top[0]
                winner = message.guild.get_member(winner_id)
                if not winner:
                    print(f"⚠️ Could not find member {winner_id}")
                else:
                    print(f"Top chatter is {winner} — assigning MVP...")
                    if mvp_role not in winner.roles:
                        # remove old holders
                        for member in message.guild.members:
                            if mvp_role in member.roles and member.id != winner.id:
                                try:
                                    await member.remove_roles(mvp_role, reason="Reassigning MVP to new #1")
                                except discord.Forbidden:
                                    print("⚠️ Could not remove role from someone.")
                        try:
                            await winner.add_roles(mvp_role, reason="Currently #1 in leaderboard")
                            print(f"✅ MVP role assigned to {winner}")
                            # 📢 Announce in the channel
                            channel = (
                                    message.guild.get_channel(TRACK_CHANNEL_ID)
                                    or message.guild.system_channel
                            )
                            if channel:
                                await channel.send(
                                    f"The new ruler of main chat is: {winner.mention}  "
                                    f"they're now the NEW bearer of {mvp_role.mention}!1!!1. COngratulations... Now go take a fucking shower moron.  "
                                )
                        except discord.Forbidden:
                            print("⚠️ Could not add role to winner.")
    await bot.process_commands(message)

# ===================== Guild tag detection =====================

EQUIP_MESSAGES = [
    "{mention} just equipped <:balls:1370161168622162121> as their profile tag! PRAISE THE BALLLS!!!",
    "{mention} equipped <:balls:1370161168622162121> as their server tag :D. This is the way.",
    "All hail {mention} for bearing our sacred <:balls:1370161168622162121> tag. May your L's be few and your W's many.",
    "Ey {mention}, thanks for equipping our tag >:)",
    "Welcome to the faith, {mention}! (ty for equipping our tag)",
    "THANKS FOR USING <:balls:1370161168622162121> AS YOUR PROFILE TAG, {mention}!",
    "{mention} just equipped <:balls:1370161168622162121> as their profile tag. (+based +cool)",
    "{mention} just equipped <:balls:1370161168622162121> as their profile tag. HEHEHEHAW",
    "Heads up, {mention} just equipped <:balls:1370161168622162121> as their profile tag! Welcome to the cul- i mean club {mention} :) (you didnt see shit by the way)",
    "Thank you, {mention} for WEAR(:wear:)ing our server's tag in your profile."
    "{mention} just grew a new pair of <:balls:1370161168622162121>!. You can too by the way by checking https://discord.com/channels/1369502239156207616/1369713659785379840 out."
]

REMOVE_MESSAGES = [
    "{mention} removed their <:balls:1370161168622162121> tag. THE COURT DECLARES HERESY...SEND THEM TO THE fucking DEPTHS",
    "{mention} chopped off their <:balls:1370161168622162121> (removed their tag 🤮), shame at will.",
    "{mention} has lost their <:balls:1370161168622162121>… how embarrassing.",
    "{mention} wasn't brave enough and removed their tag <:Revoked:1374428028607795220>. Shame away!",
    "SORRY FOR INTERRUPTING YOUR CONVERSATION BUT I JUST WANT TO CALL OUT {mention} FOR REMOVING THEIR <:balls:1370161168622162121>. a coward's move...and disgraceful",
    "{mention} WHY DID YOU REMOVE? WHY DID YOU REMOVE THE TAG? *kicks and screams in an Indian accent*",
    "{mention} just castrated themselves (removed their <:balls:1370161168622162121> tag. Yucky)",
    "ATTENTION! NOTICE! VERY IMPORTANT! {mention} over here just chopped off their <:balls:1370161168622162121>. Prepare the tickle chamber."
]

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

    channel = (
        guild.get_channel(TAG_ANNOUNCE_CHANNEL_ID)
        or guild.system_channel
        or next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)
    )
    if not channel:
        return

    member = guild.get_member(after.id) or await get_member_safe(guild, after.id)
    mention = member.mention if member else f"<@{after.id}>"

    if a_id == MY_GUILD_ID:
        msg = random.choice(EQUIP_MESSAGES).format(mention=mention)
        await channel.send(msg)
        return

    if b_id == MY_GUILD_ID and a_id != MY_GUILD_ID:
        msg = random.choice(REMOVE_MESSAGES).format(mention=mention)
        await channel.send(msg)
        return


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

    # ---- Table header ----
    header = f"{'Rank':<6}{'User':<25}{'Messages':>10}"
    sep = "-" * len(header)
    lines = [header, sep]

    # ---- Table rows ----
    for i, (uid, cnt) in enumerate(rows, 1):
        member = interaction.guild.get_member(uid)
        name = member.name if member else f"User {uid}"

        # Add crown + MVP role to first place
        if i == 1:
            mvp_role = interaction.guild.get_role(MVP_ROLE_ID) if MVP_ROLE_ID else None
            role_suffix = f" {mvp_role.name}" if mvp_role else ""
            name = f"👑 {name}{role_suffix}"

        # Truncate usernames to fit neatly
        name = (name[:21] + "...") if len(name) > 24 else name

        lines.append(f"{i:<6}{name:<25}{cnt:>10}")

    # Wrap inside Discord code block
    table = "```\n" + "\n".join(lines) + "\n```"

    # Add footer about the tracked channel
    ch = interaction.guild.get_channel(TRACK_CHANNEL_ID)
    if ch:
        table += f"\n(Counting messages only in: #{ch.name})"

    await interaction.response.send_message(table)

# === HOURLY LEADERBOARD ANNOUNCER ===
ANNOUNCE_CHANNEL_ID = 1369502239156207619

@tasks.loop(hours=1)
async def announce_leaderboard():
    for guild in bot.guilds:
        rows = get_leaderboard_for_day(guild.id, dt.date.today())
        if not rows:
            continue

        lines = []
        for i, (uid, cnt) in enumerate(rows, 1):
            member = guild.get_member(uid)
            name = member.mention if member else f"<@{uid}>"
            lines.append(f"**{i}.** {name} — {cnt}")

        embed = discord.Embed(
            title="The hall of shame: :Fnaf: (aka hourly update for today's 'messages' leaderboard)",
            description="\n".join(lines),
            color=discord.Color.green()
        )
        embed.set_footer(text="Counting messages only in the tracked channel")

        channel = guild.get_channel(ANNOUNCE_CHANNEL_ID)
        if channel and channel.permissions_for(guild.me).send_messages:
            await channel.send(embed=embed)

# ====== TAG COUNT (no pings) ======

@bot.tree.command(name="tagged_count", description="Count the number of loyalists with the tag equipped.")
async def tagged_count(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("Run this in a server.", ephemeral=True)  # type: ignore
        return

    # force cache to ensure we have all members
    await guild.chunk()

    count = 0

    for member in guild.members:
        pg = getattr(member, "primary_guild", None)
        tag = getattr(pg, "tag", None)
        if tag and tag.strip().lower() == "baǁs":  # only count if tag is exactly 'balls'
            count += 1
    msg = f"Loyalists with the 'balls' tag equipped: **{count}**"
    await interaction.response.send_message(msg)  # type: ignore

#CLEARING-----------------
@bot.tree.command(name="clear_leaderboardd", description="(Admin) Clear today's leaderboard for this server.")
@discord.app_commands.default_permissions(manage_guild=True)
async def clear_leaderboard(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("❌ Run this in a server, not in DMs.", ephemeral=True)  # type: ignore
        return

    today = today_key()
    with closing(db()) as conn, conn:
        conn.execute(
            "DELETE FROM message_counts WHERE guild_id=? AND day_key=?",
            (guild.id, today),
        )

    await interaction.response.send_message(
        f"BOOOm. WHOOOSH. PLSDOUQHEIUDWI. Thats the sound of your *precious* leaderboard crumbling to dust and BLOWING right the fuck up, AHAHAHDWUWE *cough* *cough*", ephemeral=False  # type: ignore
    )
#---------------------------------

# ===================== RUN =====================

if __name__ == "__main__":
    ensure_db()
    bot.run(TOKEN)