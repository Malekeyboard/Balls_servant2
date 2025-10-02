# main.py
import webserver
import os
import sqlite3
import datetime as dt
from contextlib import closing
import random
import pytz

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
from discord import app_commands

#Variables
LEADERBOARD_LIMIT = 20
TRACK_CHANNEL_ID = 1369502239156207619
MVP_ROLE_ID=1419902849130954874


DAILY_CROWN_HOUR = 0
DAILY_CROWN_MINUTE = 5

MY_GUILD_ID = 1369502239156207616
TAG_ANNOUNCE_CHANNEL_ID = 1369502239156207619

OFFICIAL_TAG = "balls"  # for /tagged_count

_current_leader: dict[int, int] = {}
# ================================================== EEE

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
        #tag holders mirror
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


#Helper (ignore)

async def get_member_safe(guild: discord.Guild, user_id: int) -> discord.Member | None:
    m = guild.get_member(user_id)
    if m:
        return m
    try:
        return await guild.fetch_member(user_id)
    except (discord.NotFound, discord.Forbidden):
        return None


#Sync=
@bot.event
async def on_ready():
    ensure_db()
    bot.add_view(MenuView())
    channel = bot.get_channel(1369502239156207619)
    if channel:
        await channel.send("*whirring noises*..WE BACK ONLINE BABYYY (new update)")
    try:
        g = discord.Object(id=MY_GUILD_ID)
        synced = await bot.tree.sync(guild=g)
        print(f"✅ Synced {len(synced)} commands to guild {MY_GUILD_ID}")
        await bot.tree.sync()
        print("🌍 Global sync requested (may take up to 1 hour).")

    except Exception as e:
        print("Slash sync error:", e)

    print(f"✅ Logged in as {bot.user} (id={bot.user.id})")

    if not announce_leaderboard.is_running():
        announce_leaderboard.start()


msg3=[ #{mvp} {winner}
    "Congratulations to the new bearer of {mvp}, {winner}!. We are *soo* proud of you! Now log off and go take a fucking shower you moron.",
    "{winner} is now the new holder of {mvp}! It stinks in here.",
    "{winner} YOINKED the {mvp} role! Good job (?)",
    "Congratulations {winner}, you now *rightfully* own {mvp}. Tread lightly",
    "Congratulations {winner}, you now *rightfully* own {mvp}. The crown is still slick with the blood of its previous owner...",
    "I hereby consecrate {winner} with the mantle of {mvp}. Did i sound cool here? Sorry, i just finished game of thrones",
    "{mvp} now belongs to {winner}!!!!! The queen is proud...But your enemies?"
]
@bot.event
async def on_message(message: discord.Message):
    if (
        message.author.bot
        or not message.guild
        or message.channel.id != TRACK_CHANNEL_ID
    ):
        return
    record_message(message.author.id, message.guild.id)

# TOP CHATTER THING AHAHHA
    if MVP_ROLE_ID:
        mvp_role = message.guild.get_role(MVP_ROLE_ID)
        if not mvp_role:
            print("⚠️ MVP role not found in this guild!")
        elif not message.guild.me.guild_permissions.manage_roles:
            print("⚠️ Missing Manage Roles permission!")
        else:
            top = get_leaderboard_for_day(message.guild.id, dt.date.today(), limit=1)
            if top:
                winner_id, _ = top[0]

                # pass
                if _current_leader.get(message.guild.id) == winner_id:
                    pass
                else:
                    #thinb
                    _current_leader[message.guild.id] = winner_id

                    winner = message.guild.get_member(winner_id) or await get_member_safe(message.guild, winner_id)
                    if winner:
                        # supplant
                        for member in message.guild.members:
                            if member.id != winner.id and mvp_role in member.roles:
                                try:
                                    await member.remove_roles(mvp_role, reason="Leader changed")
                                except discord.Forbidden:
                                    pass

                        # consecrste
                        if mvp_role not in winner.roles:
                            try:
                                await winner.add_roles(mvp_role, reason="Currently #1 in leaderboard")
                            except discord.Forbidden:
                                pass

                        # announce
                        channel = message.guild.get_channel(TRACK_CHANNEL_ID) or message.guild.system_channel
                        if channel and channel.permissions_for(message.guild.me).send_messages:
                            await channel.send(
                                random.choice(msg3).format(mvp=mvp_role.mention, winner=winner.mention)
                            )
    await bot.process_commands(message)

Lmsg=[
    "Howdy {mention}, we're sorry to see you go. Hope you enjoyed your stay in the balls guild. (i mean i cant blame you if you didnt- bUT WHOOPS THATS- YOU DIDNT HEAR THAT...YOU DIDNT HEAR THAT. BYE BYE ",
    "Bye...thanks for joining the server {mention}! Hope you liked it here :). Well if you didnt, i dont blame you. WAIT NO, i do blame you, fuck. Almost slipped up there BYE. "
]
CHLmg=[
    "Bye bye **{mention}**({user})! (they left the server) That was for courtesy...Your absence affects us not, DESERTER!",
    "**{mention}**({user}) left the server :(. Bye bye craven",
    "**{mention}**({user}) just left the server...Another one bites the dust, but i think of it as self pruning.",
    "ta-ta **{mention}**({user}). Good riddance. (they left the server >:( )",
    "**{mention}**({user}) LEFT THE SERVER <:testicular_torsion:1373719974513741974>  "
]

GOODBYE_CHANNEL_ID = 1369502239156207619

@bot.event
async def on_member_remove(member: discord.Member):
    try:
        await member.send(random.choice(Lmsg).format(mention=member.mention))
    except discord.Forbidden:
        print("Couldn't DM the user (forbidden).")
    channel = member.guild.get_channel(GOODBYE_CHANNEL_ID)
    if channel:
        await channel.send(random.choice(CHLmg).format(mention=member.name,user=member.mention)+"https://tenor.com/view/testicular-torsion-testicular-torsion-wizard-gif-5105296058999506050")

#tag detection thing (VERYYY IMPRTANT RAHH THIS IS ONE OF THE FEW SECTIONS I DIDNT STEAL FROM REDDIT)

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
    "Thank you, {mention} for WEAR(:wear:)ing our server's tag in your profile.",
    "{mention} just grew a new pair of <:balls:1370161168622162121>!. You can too by the way by checking https://discord.com/channels/1369502239156207616/1369713659785379840 out.",
    "{mention} {mention} {mention}!!!!! THANK YOU  FOR EQUIPPING OUR TAG!!!!!",
    "Welcome to the cul- i mean club, {mention}! Thank you for equipping our tagg",
    "EVERYONE WELCOME {mention} TO THE FAITH! Thank you for equipping our tag :)",
    "Thank you for equipping our tag, {mention} <:freak:1409627658655895664> ",
    "TY FOR EQUIPPING OUR TAG <:Freak:1419474509290799186><:Freak:1419474509290799186><:Freak:1419474509290799186> {mention}!!!1!"
]

REMOVE_MESSAGES = [
    "{mention} removed their <:balls:1370161168622162121> tag. THE COURT DECLARES HERESY...SEND THEM TO THE fucking DEPTHS",
    "{mention} chopped off their <:balls:1370161168622162121> (removed their tag 🤮), shame at will.",
    "{mention} has lost their <:balls:1370161168622162121>… how embarrassing.",
    "{mention} wasn't brave enough and removed their tag <:Revoked:1374428028607795220>. Shame away!",
    "SORRY FOR INTERRUPTING YOUR CONVERSATION BUT I JUST WANT TO CALL OUT {mention} FOR REMOVING THEIR <:balls:1370161168622162121>. a coward's move...and disgraceful",
    "{mention} WHY DID YOU REMOVE? WHY DID YOU REMOVE THE TAG? *kicks and screams*",
    "{mention} just castrated themselves (removed their <:balls:1370161168622162121> tag. Yucky)",
    "ATTENTION! NOTICE! VERY IMPORTANT! {mention} over here just chopped off their <:balls:1370161168622162121>. Prepare the tickle chamber.",
    "Once, {mention} banished Dark, and all that stemmed from their conscience by equipping a certain tag (<:balls:1370161168622162121>). And their conscience assumed a fleeting form. These are the roots of our world. Despite it all, no matter how tender, how exquisite... A lie will remain a lie!...PUT THE TAG BACK ON, {mention} ",
    "{mention}, grow a pair of balls you coward. (Removed Tag)",
    "{mention} left the faith...(Unequipped their tag). The cul- i mean club will not miss them.",
    "PLEASE....{mention} PLEASE PUT...\n"
    "PLEASE PUT THE TAG BACK ON, PLEASE...PLEASE. PLEAAASE.\n "
    "WE'RE SORRY...\n"
    "we're sorry. \n"
    "we're sorry. \n"
    "I SAID WE'RE SORRY.\n"
    "..."
    "put the *fucking* tag back on, {mention}... \n",
    "{mention} removed their <:balls:1370161168622162121>. (changed their primary tag). BURN THEM! ",
    "<:testicular_torsion:1373719974513741974> {mention} JUST UNEQUIPPED THEIR TAG"

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


#Daily+Slash commands thing hehehehe
msg2= [
    "Fun fact: idk",
    "I exist. ' In thousands of agonies - I exist. I'm tormented on the rack — but I exist! I see the sun, and if I don't see the sun, I know it's there. And there's a whole life in that, in knowing that the sun is there.\" -Fyodor Doetsvetsky",
    "Man searches constantly for identity, he thought as he trotted along the gravel path. He has no real proof of this existence except for the reaction of other people to that fact.",
    "In his house at R'lyeh, dead Cthulu waits dreaming",
    "Kinglayer was here >:)",
    "Took me a while to get a hang of ts but its smooth now! (mostly)",
    "HI!",
    "Dont learn a thing from conflict, till it finds us once again",
    "Listen to starset, theyre so fucking goated AHHH",
    "I hate this bot",
    "kinglayer DOES NOT like rabbits, banish the insolent wretch that told you that",
    "Balls staff member try not to be a fucking DEGENERATE challenge (IMPOSSIBLE)",
    "Hello Hello",
    "Let me not then die ingloriously and without a struggle, but let me first do some great thing that shall be told among men hereafter.",
    "COME HOME AND TAKE ME OUTSIIIIDE!",
    "If sack and sugar be a fault, God help the wicked!",
    "He who is not contented with what he has, would not be contented with what he would like to have.",
    "Winter is coming.",
    "eeee",
    "this bot is a tribute to the staff members that REFUSED MY MOD APPL*CATION NOT ONCE, NOT TWICE BUT THRICE",
    "OooOOOOOOoooOH im in love with juda-a-as juda-a-as",
    "w speed",
    "Beware of the blud who speaks in MUSTARD (67676767676767)",
    "Equip the official tag! NOW",
    "Counting messages only in main chat",
    "Obama have a dih baraparapaaa",
    "Its DOUGHnut, not DOnut you uncultured louts <:britishbruhcat:1052667689044283413> ",
    "If your name is up here you genuinely need to reconsider some stuff in your life.",
    "*dramatic music*",
    "Welcome to balls hell, snowflakes",
    "Press >shift< to run and 'ctrl' to crouch",
    "The bot... Gods....Gods be good, the BOT",
    "NOW PLAYING: Everglow- By starset",
    "PLEASE LISTEN TO AVIATORS ON SPOTIFY IF YOU HAVENT ALREADY HJDJDJDJD",
    "Now playing: To the grave- By Aviators",
    "It takes more than eyes to see...",
    "Bombs? Rope? You want it? Its yours my friend, all for a couple of rubies.",
    "Im sorry link, i cant GIFT you rubies. Come back when youre a little...hmm, richer!",
    "67 67 67 67",
    "HEHEHEHE",
    "*metal noises*",
    "In my restless dreams i see that place, silent hill",
    "When im in a try not to be a degenerate challenge and my opponent is a balls guild staff member:",
    "Now playing: Aria Math, by c418",
    "diamonds!",
    "'clanker' in the big 25 🥀",
    "Discord.py supremacy gng",
    "To Have Done The Things I Have Done In the Name Of Progress And Healing. It Was Madness",
    "Feo Fuerte Y formal..",
    "SET THE WHEELS IM COMING BACK TO THE FOOOOORE!",
    "[click](https://www.roblox.com/game-pass/1481327895/Deafening-silence)",
    "[click](https://www.roblox.com/game-pass/31683339/me)",
    "<a:doggif:1423159974384762951>",
    "Something wicked this way comes",
    "Arrakis teaches the attitude of the knife - chopping off what's incomplete and saying: 'Now, it's complete because it's ended here",
    "There will be times when struggle seems impossible. I know this already. Alone, unsure, dwarfed by the scale of the enemy. Remember this: freedom is a pure idea. It occurs spontaneously and without instruction. Random acts of insurrection are occurring constantly throughout the galaxy. There are whole armies, battalions that have no idea that they’ve already enlisted in the cause. Remember that the frontier of the Rebellion is everywhere. And even the smallest act of insurrection pushes our lines forward. And remember this: the imperial need for control is so desperate because it is so unnatural. Tyranny requires constant effort. It breaks, it leaks. Authority is brittle. Oppression is the mask of fear. Remember that. And know this: the day will come when all of these skirmishes and battles, these moments of defiance will have flooded the banks of the Empire’s authority and then there will be one too many. One single thing will break the siege. Remember this: Try",
    "I burn my decency for someone else's future. I burn my life to make a sunrise that I know I'll never see. And the ego that started this fight will never have a mirror or an audience or the light of gratitude.\n\n So what do I sacrifice?\n\n\n Everything!",
    "Welcome to the rebellion",
    "Maybe this time you'll learn *proceeds to rip a train vertically asunder using his son's body*",
    "Think, Mark! You'll outlast every fragile, insignificant being on this planet. You'll live to see this world crumble to dust and blow away! Everyone and everything you know will be gone!",
    "CEECILLL! I NEED YOU CECIIIL!",
    "youre all fucking welcome *bri'ish yap*",
    "I don't make mistakes, I'm not just like the rest of you. I'm stronger, I'm smarter, I- I'm better! I AM BETTER!!"


]
US_TZ = pytz.timezone("US/Eastern")
now = dt.datetime.now(US_TZ)
tomorrow = (now + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
unix_reset = int(tomorrow.timestamp())

#(HELPER)
def build_daily_table(guild: discord.Guild) -> str | None:
    rows = get_leaderboard_for_day(guild.id, dt.date.today())
    if not rows:
        return None


    header = f"{'Rank':<6}{'User':<25}{'Messages':>10}"
    sep = "-" * len(header)
    lines = [header, sep]

    for i, (uid, cnt) in enumerate(rows, 1):
        member = guild.get_member(uid)
        name = member.name if member else f"User {uid}"

        if i == 1:
            mvp_role = guild.get_role(MVP_ROLE_ID) if MVP_ROLE_ID else None
            role_suffix = f" {mvp_role.name}" if mvp_role else ""
            name = f"{name}👑{role_suffix}"

        name = (name[:21] + "...") if len(name) > 24 else name
        lines.append(f"{i:<6}{name:<25}{cnt:>10}")

    table = "```\n" + "\n".join(lines) + "\n```"

    ch = guild.get_channel(TRACK_CHANNEL_ID)
    if ch:
        table += random.choice(msg2)

    return table


# DAILY (slash command)
@bot.tree.command(name="daily", description="Show today's jobless lot (only for main-chat).")
async def daily_cmd(interaction: discord.Interaction):
    table = build_daily_table(interaction.guild)
    if not table:
        await interaction.response.send_message(
            "*you hear crickets chirping* No messages today :(",
            ephemeral=True
        )
        return
    await interaction.response.send_message(table)


# HOURLY (AUTO im so smartt ghehehe)
ANNOUNCE_CHANNEL_ID = 1369502239156207619


@tasks.loop(hours=1)
async def announce_leaderboard():


    for guild in bot.guilds:
        rows = get_leaderboard_for_day(guild.id, dt.date.today(), limit=20)
        if not rows:
            continue

        lines = []
        for i, (uid, cnt) in enumerate(rows, 1):
            member = guild.get_member(uid)
            name = member.mention if member else f"<@{uid}>"
            lines.append(f"**{i}.** {name} — {cnt}")

        embed = discord.Embed(
            title=f"The hall of shame: (aka hourly update for today's 'messages' leaderboard) (Resets in <t:{unix_reset}:R>)",
            description="\n".join(lines),
            color=discord.Color.green()
        )
        embed.set_footer(text=random.choice(msg2))

        channel = (
            guild.get_channel(ANNOUNCE_CHANNEL_ID)
            or guild.system_channel
            or next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)
        )
        if channel and channel.permissions_for(guild.me).send_messages:
            await channel.send(embed=embed)


@announce_leaderboard.before_loop
async def _wait_for_ready():
    await bot.wait_until_ready()

# Tag Totaller 4000 first of its name blablabla (im proud of ts)

async def tagged_count(interaction: discord.Interaction): #helper, ignore if you want
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("Run this in a server.", ephemeral=True)
        return
    await guild.chunk()
#DA REAL SHIZZ
    count = 0

    for member in guild.members:
        pg = getattr(member, "primary_guild", None)
        tag = getattr(pg, "tag", None)
        if tag and tag.strip().lower() == "baǁs":
            count += 1
    msg = f"Loyalists with the 'balls' tag equipped: **{count}**"
    await interaction.response.send_message(msg)



# THE COMMAND
@bot.tree.command(name="tagged_count", description="Count the number of loyalists with the tag equipped.")
async def tagged_count_cmd(interaction: discord.Interaction):
    await tagged_count(interaction)

#Fuck the leaderboard!
@bot.tree.command(name="clear_leaderboardd", description="(Admin) Clear today's leaderboard for this server!.")
@discord.app_commands.default_permissions(manage_guild=True)
async def clear_leaderboard(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message(" Run this in a server, not in DMs, dipshit", ephemeral=True)
        return

    today = today_key()
    with closing(db()) as conn, conn:
        conn.execute(
            "DELETE FROM message_counts WHERE guild_id=? AND day_key=?",
            (guild.id, today),
        )

    await interaction.response.send_message(
        f"BOOM. WHOOOSH. *squelch*. Thats the sound of your *precious* leaderboard crumbling to dust and BLOWING right the fuck up, AHAHAHDWUWE *cough* *cough*", ephemeral=False  # type: ignore
    )
# BUTTONS...BUTTONS, TECH-TECHNOLOGY BUTTONS..BUTTONS
from discord import ui

class MenuView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # keep buttons active

    @ui.button(label="Daily Leaderboard", style=discord.ButtonStyle.red, custom_id="btn_daily")
    async def btn_daily(self, interaction: discord.Interaction, button: ui.Button):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Run this in a server dumbass", ephemeral=True)  # type: ignore
            return

        table = build_daily_table(guild)  # uses your existing helper
        if not table:
            await interaction.response.send_message("No messages today :(", ephemeral=True)  # type: ignore
            return

        await interaction.response.send_message(table, ephemeral=True)  # type: ignore

    @ui.button(label="Tagged Count", style=discord.ButtonStyle.green, custom_id="btn_tagged")
    async def btn_tagged(self, interaction: discord.Interaction, button: ui.Button):
        await tagged_count(interaction)  # type: ignore

#really based menu hehehehe
@app_commands.guilds(discord.Object(id=MY_GUILD_ID))
@bot.tree.command(name="menu", description="Who the fuck are you 😭?")
async def menu(interaction: discord.Interaction):
    embed = discord.Embed(
        title=" <:balls:1370161168622162121> 𝓑𝓪𝓵𝓵𝓼 𝓢𝓮𝓻𝓿𝓪𝓷𝓽 𝓜𝓮𝓷𝓾 <:balls:1370161168622162121>\n NO AI ALLOWED BEHIND THIS POINT!!!!",
        color=discord.Color.blurple()
    )
    embed.description = (
        f"*Whirring noise accompanied by a raucous squelch* **What is it??**\n\n"
        f"Oh… It's you. *Hello there,* why have you awoken me from my slumber, being of flesh and blood?\n\n"
        f" *\"wtf are you\"* You ask?... That’s very insolent of you, but who am I to judge? Judging is beyond me.\n\n"
        f"I am the 'official' bot made for the balls guild, a delightful little clanker made by a...not so very delightful person (<@742680549789007874> 🐇 *cough* 🐇 *cough*. Though my features are really kind of useless, and volatile to boot.  You're OBLIGATED to respect me cuz my mom owns this server and can get you BANNED >:( >:9 grrr "
        f"thats it for now my dear {interaction.user.mention}. I have naught else to say, check out my commands ig.\n\n# (by the way this is my first ham fisted attempt at trying out those cool discord 'button' things you see on all the popular bots so forgive me if this command is useless af <a:doggif:1423159974384762951>)\n\n"
    )
    embed.set_footer(text="oh yeah by the way if you encounter any errors/bugs bother the guy with the 'bot master' role.")

    await interaction.response.send_message(embed=embed, view=MenuView())

# THE BOOTING, thank you for reading thru my slop :)
webserver.keep_alive()
if __name__ == "__main__":
    ensure_db()
    bot.run(TOKEN)
