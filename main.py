#PREP
import os, sqlite3, random, logging, datetime as dt
from contextlib import closing
import pytz, discord, webserver
from dotenv import load_dotenv
from discord import app_commands, ui
from discord.ext import commands, tasks

#retarded variables (pardon my ocd)
LEADERBOARD_LIMIT=20
TRACK_CHANNEL_ID=1369502239156207619
MVP_ROLE_ID=1419902849130954874
MY_GUILD_ID=1369502239156207616
ANNOUNCE_CHANNEL_ID=1369502239156207619
OFFICIAL_TAG="balls"
OWNER_ID=742680549789007874
US_TZ=pytz.timezone("US/Eastern")
DB_PATH=os.path.join(os.path.dirname(__file__),"discord_daily.db")

load_dotenv(); TOKEN=os.getenv("DISCORD_TOKEN")
logging.basicConfig(level=logging.INFO); log=logging.getLogger("balls-bot")

#configure i stole from the wiki 
intents=discord.Intents.default(); intents.message_content=True; intents.members=True
class BallsBot(commands.Bot):
    async def setup_hook(self):
        if not clear_leaderboard_daily.is_running(): clear_leaderboard_daily.start()
        if not announce_leaderboard2.is_running(): announce_leaderboard2.start()
    async def on_ready(self):
        ensure_db(); self.add_view(MenuView())
        ch=self.get_channel(ANNOUNCE_CHANNEL_ID)
        if ch: await ch.send("*whirring noises*..WE BACK ONLINE BABYYY (new update)")
        try:
            g=discord.Object(id=MY_GUILD_ID); synced=await self.tree.sync(guild=g)
            print(f"✅ Synced {len(synced)} commands to guild {MY_GUILD_ID}")
            await self.tree.sync(); print("🌍 Global sync requested (may take up to 1 hour).")
        except Exception as e: print("Slash sync error:", e)
        log.info(f"✅ Logged in as {self.user} (id={self.user.id})")
        try: await post_hourly_once()
        except Exception as e: log.exception(f"initial hourly post failed: {e}")
bot=BallsBot(command_prefix="!", intents=intents)

# sql databases (https://www.youtube.com/watch?v=W_belnWXFhE&pp=ygUhaG93IHRvIG1ha2UgYSBkYXRhYmFzZSBpbiBkaXNjb3Jk is really cool go check 'im out)
def db():
    c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; return c
def ensure_db():
    with closing(db()) as conn, conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS message_counts(
            user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, day_key TEXT NOT NULL,
            count INTEGER NOT NULL, PRIMARY KEY(user_id,guild_id,day_key))""")
def today_key(): return dt.datetime.now(US_TZ).date().isoformat()
def reset_ts(now=None):
    now=now or dt.datetime.now(US_TZ)
    return int((now+dt.timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0).timestamp())
def record_message(user_id:int,guild_id:int):
    with closing(db()) as conn, conn:
        conn.execute("""INSERT INTO message_counts(user_id,guild_id,day_key,count)
                        VALUES(?,?,?,1) ON CONFLICT(user_id,guild_id,day_key)
                        DO UPDATE SET count=count+1""",(user_id,guild_id,today_key()))
def get_leaderboard_for_day(gid:int,the_day:dt.date,limit:int=LEADERBOARD_LIMIT):
    with closing(db()) as conn:
        cur=conn.execute("""SELECT user_id,count FROM message_counts
                            WHERE guild_id=? AND day_key=? ORDER BY count DESC LIMIT ?""",
                         (gid,the_day.isoformat(),limit))
        return [(r["user_id"],r["count"]) for r in cur.fetchall()]

#Helper thing i stole from reddit
_current_leader:dict[int,int]={}
async def get_member_safe(guild:discord.Guild,user_id:int):
    m=guild.get_member(user_id)
    if m: return m
    try: return await guild.fetch_member(user_id)
    except (discord.NotFound,discord.Forbidden): return None
#MESSAGES EHHEHEHE
msg3=[
"Congratulations to the new bearer of {mvp}, {winner}!. We are *soo* proud of you! Now log off and go take a fucking shower you moron.",
"{winner} is now the new holder of {mvp}! It stinks in here.","{winner} YOINKED the {mvp} role! Good job (?)",
"Congratulations {winner}, you now *rightfully* own {mvp}. Tread lightly",
"Congratulations {winner}, you now *rightfully* own {mvp}. The crown is still slick with the blood of its previous owner...",
"I hereby consecrate {winner} with the mantle of {mvp}. Did i sound cool here? Sorry, i just finished game of thrones",
"{mvp} now belongs to {winner}!!!!! The queen is proud...But your enemies?"
]

Lmsg=[
"Howdy {mention}, we're sorry to see you go. Hope you enjoyed your stay in the balls guild. (i mean i cant blame you if you didnt- bUT WHOOPS THATS- YOU DIDNT HEAR THAT...YOU DIDNT HEAR THAT. BYE BYE ",
"Bye...thanks for joining the server {mention}! Hope you liked it here :). Well if you didnt, i dont blame you. WAIT NO, i do blame you, fuck. Almost slipped up there BYE. ",
"Why'd you leave? :(( Was the degeneracy that bad??? Listen i get that you found this server either creepy, unhinged or corny but you have to understand that with every person that drops out, the more they torture their 'servants'. Youre going to live with this fact now <:NOBALLS:1374428047205339186> ",
'Shi was corny af am i right? I MEAN, NOPE. SORRY, I WAS NOT SUPPOSED TO- BYE..BYE THANKS FOR JOINING BY-BYE AAHHHH *scraping noises*'
]
CHLmg=[
"Bye bye **{mention}**({user})! (they left the server) That was for courtesy...Your absence affects us not, DESERTER!",
"**{mention}**({user}) left the server :(. Bye bye craven",
"**{mention}**({user}) just left the server...Another one bites the dust, but i think of it as self pruning.",
"ta-ta **{mention}**({user}). Good riddance. (they left the server >:( )",
"**{mention}**({user}) LEFT THE SERVER <:testicular_torsion:1373719974513741974>  "
]

EQUIP_MESSAGES=[
"{mention} just equipped <:balls:1370161168622162121> as their profile tag! PRAISE THE BALLLS!!!",
"{mention} equipped <:balls:1370161168622162121> as their server tag :D. This is the way.",
"All hail {mention} for bearing our sacred <:balls:1370161168622162121> tag. May your L's be few and your bitches's many.<:Spooky:1374429245153087549> ",
"Ey {mention}, thanks for equipping our tag >:)","Welcome to the faith, {mention}! (ty for equipping our tag)",
"THANKS FOR USING <:balls:1370161168622162121> AS YOUR PROFILE TAG, {mention}!","{mention} just equipped <:balls:1370161168622162121> as their profile tag. (+based +cool)",
"{mention} just equipped <:balls:1370161168622162121> as their profile tag. HEHEHEHAW",
"Heads up, {mention} just equipped <:balls:1370161168622162121> as their profile tag! Welcome to the cul- i mean club {mention} :)",
"Thank you, {mention} for WEAR(:wear:)ing our server's tag on your profile.",
"{mention} just grew a new pair of <:balls:1370161168622162121>!. You can too by the way by checking https://discord.com/channels/1369502239156207616/1369713659785379840 out.",
"{mention} {mention} {mention}!!!!! THANK YOU  FOR EQUIPPING OUR TAG!!!!!",
"Welcome to the cul- i mean club, {mention}! Thank you for equipping our tagg",
"EVERYONE WELCOME {mention} TO THE FAITH! Thank you for equipping our tag :)",
"Thank you for equipping our tag, {mention} <:freak:1409627658655895664> ",
"TY FOR EQUIPPING OUR TAG <a:doggif:1423159974384762951><a:doggif:1423159974384762951><a:doggif:1423159974384762951> {mention}!!!1!"
]
REMOVE_MESSAGES=[
"{mention} removed their <:balls:1370161168622162121> tag. THE COURT DECLARES HERESY...SEND THEM TO THE fucking DEPTHS",
"{mention} chopped off their <:balls:1370161168622162121> (removed their tag 🤮), shame at will<:NOBALLS:1374428047205339186> .",
"{mention} has lost their <:balls:1370161168622162121>… how embarrassing.",
"{mention} wasn't brave enough and removed their tag <:Revoked:1374428028607795220>. prepare the stick",
"SORRY FOR INTERRUPTING YOUR CONVERSATION BUT I JUST WANT TO CALL OUT {mention} FOR REMOVING THEIR <:balls:1370161168622162121>. a coward's move...and disgraceful<:Revoked:1374428028607795220> ",
"{mention} WHY DID YOU REMOVE? WHY DID YOU REMOVE THE TAG? *kicks and screams*",
"{mention} just castrated themselves (removed their <:balls:1370161168622162121> tag. Yucky)",
"ATTENTION! NOTICE! VERY IMPORTANT! {mention} over here just chopped off their <:balls:1370161168622162121>. Prepare the tickle chamber.",
"Once, {mention} banished Dark, and all that stemmed from their conscience by equipping a certain tag (<:balls:1370161168622162121>). And their conscience assumed a fleeting form. These are the roots of our world. Despite it all, no matter how tender, how exquisite... A lie will remain a lie!...PUT THE TAG BACK ON, {mention} ",
"{mention}, grow a pair of balls you coward. (Removed Tag)",
"{mention} left the faith...(Unequipped their tag). The cul- i mean club will not miss them<:noballs:1371881387027861656> .",
"PLEASE....{mention} PLEASE PUT...\nPLEASE PUT THE TAG BACK ON, PLEASE...PLEASE. PLEAAASE.\n WE'RE SORRY...\nwe're sorry. \nwe're sorry. \nI SAID WE'RE SORRY.\n...put the *fucking* tag back on, {mention}... \n",
"{mention} removed their <:balls:1370161168622162121>. (changed their primary tag). BURN THEM<:Revoked:1374428028607795220> ! ",
"<:testicular_torsion:1373719974513741974> {mention} JUST UNEQUIPPED THEIR TAG"
]

msg2=[
"Fun fact: idk","I exist. ' In thousands of agonies - I exist. I'm tormented on the rack — but I exist! I see the sun, and if I don't see the sun, I know it's there. And there's a whole life in that, in knowing that the sun is there.\" -Fyodor Doetsvetsky",
"Man searches constantly for identity, he thought as he trotted along the gravel path. He has no real proof of this existence except for the reaction of other people to that fact.",
"In his house at R'lyeh, dead Cthulu waits dreaming...of <:balls:1370161168622162121>","Kinglayer was here >:)","Took me a while to get a hang of ts but its smooth now! (mostly)",
"One tag to rule them all (<:balls:1370161168622162121>), one tag to find them (<:balls:1370161168622162121>) one tag to bring them all (<:balls:1370161168622162121>) and in the darkness, cuck them",
"Dont learn a thing from conflict, till it finds us once again","Listen to starset, theyre so fucking goated AHHH","I hate this bot",
"kinglayer DOES NOT like rabbits, banish the insolent wretch that told you that","<:balls:1370161168622162121> staff member try not to be a fucking DEGENERATE challenge (IMPOSSIBLE)","G'day ballers",
"Let me not then die ingloriously and without a struggle, but let me first do some great thing that shall be told among <:balls:1370161168622162121> hereafter.",
"COME HOME AND TAKE ME OUTSIIIIDE!","If <:balls:1370161168622162121> and sugar be a fault, God help the wicked!",
"He who is not contented with what he has, would not be contented with what he would like to have (<:balls:1370161168622162121>).","Winter is coming.","eeee",
"this bot is a tribute to the staff members that REFUSED MY MOD APPL*CATION NOT ONCE, NOT TWICE BUT THRICE","OooOOOOOOoooOH im in love with juda-a-as juda-a-as","w speed",
"Beware of the <:balls:1370161168622162121> who speaks in MUSTARD (67676767676767)","Equip the official tag! NOW","Counting messages only in main chat",
"I am in a cage, in search of some <:balls:1370161168622162121> - Franz Kafka ","Its DOUGHnut, not DOnut you uncultured louts <:britishbruhcat:1052667689044283413> ",
"If your name is up here you genuinely need to reconsider some stuff in your life.","*dramatic music*","Welcome to balls hell, snowflakes",
"Press >shift< to run and 'ctrl' to crouch","The bot... Gods....Gods be good, the BOT","NOW PLAYING: Everglow- By starset",
"PLEASE LISTEN TO AVIATORS ON SPOTIFY IF YOU HAVENT ALREADY HJDJDJDJD","Now playing: To the grave- By Aviators","It takes more than eyes to see...",
"Bombs? Rope? You want it? Its yours my friend, all for a couple of rubies.","Im sorry link, i cant GIFT you rubies. Come back when youre a little...hmm, richer!",
"67 67 67 67","HEHEHEHE","*metal noises*","In my restless dreams i see that place, silent hill",
"When im in a try not to be a degenerate challenge and my opponent is a balls guild staff member:","Now playing: Aria Math, by c418","<:balls:1370161168622162121> supremacy",
"'clanker' in the big 25 🥀","Discord.py supremacy gng","To Have Done The Things I Have Done In the Name Of Progress And Healing. It Was Madness",
"Feo Fuerte Y formal..","SET THE WHEELS IM COMING BACK TO THE FOOOOORE!","[click](https://www.roblox.com/game-pass/1481327895/Deafening-silence)",
"[click](https://www.roblox.com/game-pass/31683339/me)","<a:doggif:1423159974384762951>","Something wicked this way comes",
"Arrakis teaches the attitude of the knife - chopping off what's incomplete and saying: 'Now, it's complete because it's ended here",
"I burn my decency for someone else's future. I burn my life to make a sunrise that I know I'll never see. And the ego that started this fight will never have a mirror or an audience or the light of gratitude.\n\n So what do I sacrifice?\n\n\n Everything!",
"Welcome to the rebellion","Maybe this time you'll learn *proceeds to rip a train vertically asunder using his son's body*",
"Think, Mark! You'll outlast every fragile, insignificant being on this planet. You'll live to see this world crumble to dust and blow away! Everyone and everything you know will be gone!",
"CEECILLL! I NEED YOU CECIIIL!","youre all fucking welcome *bri'ish yap*",
"I don't make mistakes, I'm not just like the rest of you. I'm stronger, I'm smarter, I- I'm better! I AM BETTER!!",
"<:balls:1370161168622162121>","<:avocado:1371645911968780288> *ngh*","Prepare yourselves","<:head:1373755448410243072> ",
"In a coat of gold or a coat of red, the lion still has <:balls:1370161168622162121>. \n Mine are large, and bold my lord. As large and bold as yours "
]

# Evenets + crowning
@bot.event
async def on_message(message:discord.Message):
    if message.author.bot or not message.guild: return
    if message.channel.id==TRACK_CHANNEL_ID:
        record_message(message.author.id,message.guild.id)
        if MVP_ROLE_ID:
            mvp=message.guild.get_role(MVP_ROLE_ID)
            if mvp and message.guild.me.guild_permissions.manage_roles:
                top=get_leaderboard_for_day(message.guild.id,dt.datetime.now(US_TZ).date(),1)
                if top:
                    winner_id,_=top[0]
                    if _current_leader.get(message.guild.id)!=winner_id:
                        _current_leader[message.guild.id]=winner_id
                        win=message.guild.get_member(winner_id) or await get_member_safe(message.guild,winner_id)
                        if win:
                            for mem in message.guild.members:
                                if mem.id!=win.id and mvp in mem.roles:
                                    try: await mem.remove_roles(mvp,reason="Leader changed")
                                    except discord.Forbidden: pass
                            if mvp not in win.roles:
                                try: await win.add_roles(mvp,reason="Currently #1 in leaderboard")
                                except discord.Forbidden: pass
                            ch=message.guild.get_channel(TRACK_CHANNEL_ID) or message.guild.system_channel
                            if ch and ch.permissions_for(message.guild.me).send_messages:
                                try: await ch.send(random.choice(msg3).format(mvp=mvp.mention,winner=win.mention))
                                except discord.HTTPException: pass
    await bot.process_commands(message)

@bot.event
async def on_member_remove(member:discord.Member):
    try: await member.send(random.choice(Lmsg).format(mention=member.mention))
    except discord.Forbidden: print("Couldn't DM the user (forbidden).")
    ch=member.guild.get_channel(1369502239156207619)
    if ch: await ch.send(random.choice(CHLmg).format(mention=member.name,user=member.mention),file=discord.File("bale.gif"),reference=None)

_last_user_update:dict[int,float]={}
@bot.event
async def on_user_update(before:discord.User,after:discord.User):
    b_pg=getattr(before,"primary_guild",None); a_pg=getattr(after,"primary_guild",None)
    b_id=getattr(b_pg,"id",None); a_id=getattr(a_pg,"id",None)
    if b_id==a_id: return
    now_ts=dt.datetime.now().timestamp(); last=_last_user_update.get(after.id,0)
    if now_ts-last<10: return
    _last_user_update[after.id]=now_ts
    guild=bot.get_guild(MY_GUILD_ID);
    if not guild: return
    ch=guild.get_channel(ANNOUNCE_CHANNEL_ID) or guild.system_channel or next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages),None)
    if not ch: return
    member=guild.get_member(after.id) or await get_member_safe(guild,after.id)
    mention=member.mention if member else f"<@{after.id}>"
    try:
        if a_id==MY_GUILD_ID: await ch.send(random.choice(EQUIP_MESSAGES).format(mention=mention)); return
        if b_id==MY_GUILD_ID and a_id!=MY_GUILD_ID: await ch.send(random.choice(REMOVE_MESSAGES).format(mention=mention)); return
    except discord.HTTPException: pass

#THE LEADERBOARD DUN DUNDUN *insert lord of the rings score*
def build_daily_table(g:discord.Guild):
    rows=get_leaderboard_for_day(g.id,dt.datetime.now(US_TZ).date())
    if not rows: return None
    hdr=f"{'Rank':<6}{'User':<25}{'Messages':>10}"; sep="-"*len(hdr); lines=[hdr,sep]
    for i,(uid,cnt) in enumerate(rows,1):
        m=g.get_member(uid); name=m.name if m else f"User {uid}"
        if i==1:
            mvp=g.get_role(MVP_ROLE_ID) if MVP_ROLE_ID else None
            role_suffix=f" {mvp.name}" if mvp else ""
            name=f"{name}👑{role_suffix}"
        name=(name[:21]+"...") if len(name)>24 else name
        lines.append(f"{i:<6}{name:<25}{cnt:>10}")
    table="```\n"+"\n".join(lines)+"\n```"
    if g.get_channel(TRACK_CHANNEL_ID): table+=random.choice(msg2)+f"\n\n(resets <t:{reset_ts()}:R>)"
    return table

#hourly
@tasks.loop(minutes=1)
async def clear_leaderboard_daily():
    now=dt.datetime.now(US_TZ)
    if now.hour==0 and now.minute==0:
        with closing(db()) as conn, conn: conn.execute("DELETE FROM message_counts")
        ch=bot.get_channel(1369502239156207619)
        if ch: await ch.send("Leaderboard cleared neyehehe (auto)")
        print(f"[RESET] Leaderboard cleared at {now.isoformat()}")
@clear_leaderboard_daily.before_loop
async def _wait_reset(): await bot.wait_until_ready()

@tasks.loop(hours=1,reconnect=True)
async def announce_leaderboard2():
    now=dt.datetime.now(US_TZ); today=now.date(); uts=reset_ts(now)
    for g in bot.guilds:
        try:
            rows=get_leaderboard_for_day(g.id,today,20)
            if not rows: continue
            lines=[f"**{i}.** {(g.get_member(uid).mention if g.get_member(uid) else f'<@{uid}>')} — {cnt}" for i,(uid,cnt) in enumerate(rows,1)]
            embed=discord.Embed(title=f"~THE HALL OF SHAME~(Resets <t:{uts}:R>): \n(-# aka hourly update for today's 'messages' leaderboard)",description="\n".join(lines)+"\n\n"+'🎗️ '+random.choice(msg2)+' 🎗️',color=discord.Color.green())
            ch=g.get_channel(ANNOUNCE_CHANNEL_ID) or g.system_channel or next((c for c in g.text_channels if c.permissions_for(g.me).send_messages),None)
            if ch and ch.permissions_for(g.me).send_messages: await ch.send(embed=embed); log.info(f"[hourly] posted in {g.name} #{ch.name}")
            else: log.warning(f"[hourly] {g.name}: no sendable channel found")
        except Exception as e: log.exception(f"[hourly] Failed in {g.id}: {e}")
@announce_leaderboard2.before_loop
async def _wait_hourly(): await bot.wait_until_ready()

async def post_hourly_once():
    now=dt.datetime.now(US_TZ); today=now.date(); uts=reset_ts(now)
    for g in bot.guilds:
        rows=get_leaderboard_for_day(g.id,today,20)
        if not rows: continue
        lines=[f"**{i}.** {(g.get_member(uid).mention if g.get_member(uid) else f'<@{uid}>')} — {cnt}" for i,(uid,cnt) in enumerate(rows,1)]
        embed=discord.Embed(title=f"~THE HALL OF SHAME~(Resets <t:{uts}:R>): \n(-# aka hourly update for today's 'messages' leaderboard)",description="\n".join(lines)+"\n\n"+'🎗️ '+random.choice(msg2)+' 🎗️',color=discord.Color.green())
        ch=g.get_channel(ANNOUNCE_CHANNEL_ID) or g.system_channel or next((c for c in g.text_channels if c.permissions_for(g.me).send_messages),None)
        if ch and ch.permissions_for(g.me).send_messages: await ch.send(embed=embed); log.info(f"[boot] posted in {g.name} #{ch.name}")

# very peak commands
@bot.tree.command(name="daily", description="Show today's jobless lot (only for main-chat).")
async def daily_cmd(interaction:discord.Interaction):
    t=build_daily_table(interaction.guild)
    if not t: await interaction.response.send_message("*you hear crickets chirping* No messages today :(",ephemeral=True); return
    await interaction.response.send_message(t)

async def tagged_count(interaction:discord.Interaction):
    g=interaction.guild
    if g is None: await interaction.response.send_message("Run this in a server.",ephemeral=True); return
    await g.chunk(); c=0
    for m in g.members:
        pg=getattr(m,"primary_guild",None); tag=getattr(pg,"tag",None)
        if tag and tag.strip().lower()=="baǁs": c+=1
    await interaction.response.send_message(f"Loyalists with the 'balls' tag equipped: **{c}**")

@bot.tree.command(name="tagged_count", description="Count the number of loyalists with the tag equipped.")
async def tagged_count_cmd(interaction:discord.Interaction): await tagged_count(interaction)

@bot.tree.command(name="clear_leaderboardd", description="(Admin) Clear today's leaderboard for this server!.")
@app_commands.default_permissions(manage_guild=True)
async def clear_leaderboard(interaction:discord.Interaction):
    g=interaction.guild
    if g is None: await interaction.response.send_message(" Run this in a server, not in DMs, dipshit.",ephemeral=True); return
    with closing(db()) as conn, conn: conn.execute("DELETE FROM message_counts WHERE guild_id=? AND day_key=?",(g.id,today_key()))
    await interaction.response.send_message("BOOM. WHOOOSH. *squelch*. Thats the sound of your *precious* leaderboard crumbling to dust and BLOWING right the fuck up, AHAHAHDWUWE *cough* *cough*",ephemeral=False)

class MenuView(ui.View):
    def __init__(self): super().__init__(timeout=None)
    @ui.button(label="Daily Leaderboard", style=discord.ButtonStyle.red, custom_id="btn_daily")
    async def btn_daily(self,interaction:discord.Interaction,button:ui.Button):
        g=interaction.guild
        if g is None: await interaction.response.send_message("Run this in a server dumbass",ephemeral=True); return
        t=build_daily_table(g)
        if not t: await interaction.response.send_message("No messages today :(",ephemeral=True); return
        await interaction.response.send_message(t,ephemeral=True)
    @ui.button(label="Tagged Count", style=discord.ButtonStyle.green, custom_id="btn_tagged")
    async def btn_tagged(self,interaction:discord.Interaction,button:ui.Button): await tagged_count(interaction)

@app_commands.guilds(discord.Object(id=MY_GUILD_ID))
@bot.tree.command(name="menu", description="Who the fuck are you 😭?")
async def menu(interaction:discord.Interaction):
    embed=discord.Embed(title=" <:balls:1370161168622162121> 𝓑𝓪𝓵𝓵𝓼 𝓢𝓮𝓻𝓿𝓪𝓷𝓽 𝓜𝓮𝓷𝓾 <:balls:1370161168622162121>\n NO AI ALLOWED BEHIND THIS POINT!!!!",color=discord.Color.blurple())
    embed.description=(f"*Whirring noise accompanied by a raucous squelch* **What is it??**\n\n"
        f"Oh… It's you. *Hello there,* why have you awoken me from my slumber, being of flesh and blood?\n\n"
        f" *\"wtf are you\"* You ask?... That’s very insolent of you, but who am I to judge? Judging is beyond me.\n\n"
        f"I am the 'official' bot made for the balls guild, a delightful little clanker made by a...not so very delightful person (<@742680549789007874> 🐇 *cough* 🐇 *cough*. Though my features are really kind of useless, and volatile to boot.  You're OBLIGATED to respect me cuz my mom owns this server and can get you BANNED >:( >:9 grrr "
        f"thats it for now my dear {interaction.user.mention}. I have naught else to say, check out my commands ig.\n\n# (by the way this is my first ham fisted attempt at trying out those cool discord 'button' things you see on all the popular bots so forgive me if this command is useless af <a:doggif:1423159974384762951>)\n\n")
    embed.set_footer(text="ALSO if you encounter any errors/bugs bother the guy with the 'bot master' role.")
    await interaction.response.send_message(embed=embed,view=MenuView())

@bot.tree.command(name="start_hourly", description="(Owner) Start the hourly leaderboard announcer.")
async def start_hourly(interaction:discord.Interaction):
    if interaction.user.id!=OWNER_ID: await interaction.response.send_message("Nope. King only, hands off knave.",ephemeral=True); return
    if not announce_leaderboard2.is_running(): announce_leaderboard2.start(); await interaction.response.send_message("OPEN THE GATES.",ephemeral=True)
    else: await interaction.response.send_message("cant do.",ephemeral=True)

@bot.tree.command(name="announce_now", description="(Owner) Post the leaderboard once, now.")
async def announce_now(interaction:discord.Interaction):
    if interaction.user.id!=OWNER_ID: await interaction.response.send_message("Nope. King only, hands off knave.",ephemeral=True); return
    await post_hourly_once(); await interaction.response.send_message("Sent.",ephemeral=True)

# AD ASTRA! INFINITUM! THANK YOU FOR READING THROUGH MY SLOP :DDD i hope i never have to touch this accursed thing EVER again
webserver.keep_alive()
if __name__=="__main__":
    ensure_db(); bot.run(TOKEN)
