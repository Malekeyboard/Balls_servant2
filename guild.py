import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    channel = bot.get_channel(1369873584608116796)
    if channel:
        await channel.send("whirring noises")
    await bot.close()  # closes after sending once

bot.run(TOKEN)
