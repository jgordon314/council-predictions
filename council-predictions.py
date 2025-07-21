import os
import discord
from discord.ext import commands
import asyncio
import math
from dotenv import load_dotenv
import json

SAVE_FILE = "players.json"

load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_KEY')

# Set up Discord intents
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

players = {}
admin_users = [int(os.getenv('ADMINS'))]
playerAmount1 = {}
playerAmount2 = {}

accepting = False
description = ""
item1 = ""
item2 = ""
amount1 = 0
amount2 = 0

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

@bot.command()
async def join(ctx):
    user_id = ctx.author.id
    if user_id not in players.keys():
        players[user_id] = 100
        playerAmount1[user_id] = 0
        playerAmount2[user_id] = 0
        try:
            await ctx.author.send(f'{ctx.author.name}, you have joined the game!')
            await ctx.message.add_reaction('🪿')
        except discord.Forbidden:
            await ctx.send(f"{ctx.author.name}, I couldn't DM you. Please check your privacy settings.")
    else:
        await ctx.author.send(f'{ctx.author.name}, you are already in the game!')
        await ctx.message.add_reaction('🪿')

@bot.command()
async def player_info(ctx):
    if ctx.author.id in admin_users:
        if players.keys():
            user_info = [f"{user.name} ({user_id}) - {amount}" for user_id, user, amount in zip(players.keys(), [await bot.fetch_user(uid) for uid in players.keys()], players.values())]
            await ctx.send("Joined users:\n" + "\n".join(user_info))
        else:
            await ctx.send("No users have joined yet.")
    
@bot.command()
async def alert(ctx, *, message: str):
    if ctx.author.id in admin_users:
        if players.keys():
            sent_count = 0
            for user_id in players.keys():
                user = await bot.fetch_user(user_id)
                try:
                    await user.send(message)
                    sent_count += 1
                except discord.Forbidden:
                    await ctx.send(f"Could not DM {user.name} ({user_id}).")
            await ctx.send(f"Alert sent to {sent_count} users.")
        else:
            await ctx.send("No users have joined yet.")


@bot.command()
async def start(ctx, *, message: str):
    global description, item1, item2, accepting

    # --- permission check ----------------------------------------------------
    if ctx.author.id not in admin_users:
        return

    # --- basic validation ----------------------------------------------------
    parts = [p.strip() for p in message.split(',')]
    if not players:
        await ctx.send("No users have joined yet.")
        return
    if description:
        await ctx.send("Please end the other bet before starting a new one.")
        return
    if len(parts) < 3:
        await ctx.send("Improper formatting, please follow: 'description, option 1, option 2'")
        return

    # --- store current bet ---------------------------------------------------
    description, item1, item2 = parts[:3]

    # --- confirmation embed --------------------------------------------------
    confirm_msg = await ctx.send(
        f"New bet started!\n**Description:** {description}\n"
        f"**Option 1:** {item1}\n**Option 2:** {item2}\n"
        "React with ✅ to confirm or ❌ to cancel."
    )
    await confirm_msg.add_reaction('✅')
    await confirm_msg.add_reaction('❌')

    # --- wait for admin reaction --------------------------------------------
    def check(payload: discord.RawReactionActionEvent):
        return (
            payload.message_id == confirm_msg.id
            and payload.user_id   == ctx.author.id     # <- only the admin
            and str(payload.emoji) in ('✅', '❌')
        )

    try:
        payload = await bot.wait_for('raw_reaction_add', timeout=60.0, check=check)
    except asyncio.TimeoutError:
        await ctx.send("Confirmation timed out - bet not started.")
        description = item1 = item2 = ""
        return

    if str(payload.emoji) == '✅':
        await ctx.send("confirmed")
        alert_cmd = bot.get_command('alert')
        await ctx.invoke(alert_cmd, message=(
            f"New bet has started!\n**{description}**\n"
            f"Option 1 - {item1}\nOption 2 - {item2}\n"
            "Use !info to view the current odds, and !bet [amount] to join this bet."
        ))
        accepting = True
    else:
        await ctx.send("Bet cancelled.")
        description = item1 = item2 = ""

@bot.command()
async def info(ctx):
    if(ctx.author.id not in players.keys()):
        await ctx.send("Please join the game first with !join")
        return
    if(description == ""):
        await ctx.send(f"There is no bet currently active.\nAmount in your wallet: {players[ctx.author.id]}")
        return
    status = ""
    if(accepting):
        status = "This bet is still open. Use !bet [amount] to join this bet."
    else:
        status = "This bet is now closed."
    total = amount1 + amount2
    investment = "Have not bet any engbucks"
    if(playerAmount1[ctx.author.id] > 0):
        investment = f"{playerAmount1[ctx.author.id]} on option 1"
    elif(playerAmount2[ctx.author.id] > 0):
        investment = f"{playerAmount2[ctx.author.id]} on option 2"
    await ctx.send(
    f"""
    **{description}**
    Total amount bet: {total} engbucks
        Option 1: {item1} - {amount1} engbucks bet ({math.ceil(100*amount1/(total+0.01))}%)
        Option 2: {item2} - {amount2} engbucks bet ({math.ceil(100*amount2/(total+0.01))}%)\n
    Amount you bet: {investment}
    Amount in your wallet: {players[ctx.author.id]}
    {status}
    """
    )

@bot.command()
async def bet(ctx, *, message: str):
    global description, item1, item2, amount1, amount2
    
    # --- basic validation ----------------------------------------------------
    if description == "":
        await ctx.send("There is no currently active bet.")
        return
    if not accepting:
        await ctx.send("This bet is now closed. Use !info to see the active bet.")
        return
    try:
        amount = int(message)
    except:
        await ctx.send("Please enter the amount you would like to bet with your command. Example: !bet 50")
        return
    if(ctx.author.id not in players.keys()):
        await ctx.send("Please join the game first with !join")
        return
    if(amount <= 0 and players[ctx.author.id] > 0):
        await ctx.send("Do you think you're funny? Huh? Trying to beat my game by putting in a negative bet amount? No. I am taking one of your engbucks now.")
        players[ctx.author.id] -= 1
        return
    if(amount > players[ctx.author.id]):
        await ctx.send(f"Insufficient funds, you have {players[ctx.author.id]} in your wallet.")
        return
    
    # --- confirmation embed --------------------------------------------------
    confirm_msg = await ctx.send(
        f"You would like to invest {amount} engbucks into: \n** {description}\n"
        f"**Option 1:** {item1}\n**Option 2:** {item2}**\n"
        "React with 1️⃣ to put it on option 1, 2️⃣ for option 2, or ❌ to cancel."
    )
    await confirm_msg.add_reaction('1️⃣')
    await confirm_msg.add_reaction('2️⃣')
    await confirm_msg.add_reaction('❌')

    # --- wait for player reaction --------------------------------------------
    def check(payload: discord.RawReactionActionEvent):
        return (
            payload.message_id == confirm_msg.id
            and payload.user_id   == ctx.author.id
            and str(payload.emoji) in ('1️⃣', '2️⃣', '❌')
        )

    try:
        payload = await bot.wait_for('raw_reaction_add', timeout=30.0, check=check)
    except asyncio.TimeoutError:
        await ctx.send("Confirmation timed out - amount not bet.")
        return
    
    if str(payload.emoji) == '1️⃣':
        amount1 += amount
        playerAmount1[ctx.author.id] += amount
        players[ctx.author.id] -= amount
        await ctx.send(f"Bet confirmed: **{amount} engbucks** on **{item1}**. Use !bet [amount] to increase your bet.")    
    
    elif str(payload.emoji) == '2️⃣':
        amount2 += amount
        playerAmount2[ctx.author.id] += amount
        players[ctx.author.id] -= amount
        await ctx.send(f"Bet confirmed: **{amount} engbucks** on **{item2}**. Use !bet [amount] to increase your bet.")    

    else:
        await ctx.send("Bet cancelled.")

@bot.command()
async def close(ctx):
    global accepting, amount1, amount2
    if ctx.author.id not in admin_users:
        return
    accepting = False
    alert_cmd = bot.get_command('alert')
    total = amount2 + amount1
    await ctx.invoke(alert_cmd, message=(f"Betting has now closed on **{description}** "
        f"Total amount bet: {total} engbucks\n"
        f"Option 1: {item1} - {amount1} engbucks bet ({math.ceil(100*amount1/(total+0.01))}%)\n"
        f"Option 2: {item2} - {amount2} engbucks bet ({math.ceil(100*amount2/(total+0.01))}%)"
    ))

@bot.command()
async def call(ctx):
    global description, item1, item2, accepting, amount1, amount2, playerAmount1, playerAmount2

    # --- permission check ----------------------------------------------------
    if ctx.author.id not in admin_users:
        return

    # --- basic validation ----------------------------------------------------
    if accepting == True:
        await ctx.send("Please close the bet before calling it")
        return

    # --- confirmation embed --------------------------------------------------
    total = amount1 + amount2
    confirm_msg = await ctx.send(
        f"Betting has now closed on **{description}** "
        f"Total amount bet: {total} engbucks\n"
        f"Option 1: {item1} - {amount1} engbucks bet ({math.ceil(100*amount1/(total+0.01))}%)\n"
        f"Option 2: {item2} - {amount2} engbucks bet ({math.ceil(100*amount2/(total+0.01))}%)\n"
        "Please select which bet won:"
    )
    await confirm_msg.add_reaction('1️⃣')
    await confirm_msg.add_reaction('2️⃣')
    await confirm_msg.add_reaction('❌')

    # --- wait for admin reaction --------------------------------------------
    def check(payload: discord.RawReactionActionEvent):
        return (
            payload.message_id == confirm_msg.id
            and payload.user_id   == ctx.author.id
            and str(payload.emoji) in ('1️⃣', '2️⃣', '❌')
        )

    try:
        payload = await bot.wait_for('raw_reaction_add', timeout=30.0, check=check)
    except asyncio.TimeoutError:
        await ctx.send("Confirmation timed out - amount not bet.")
        return
    
    if str(payload.emoji) == '1️⃣':
        await ctx.send("confirmed : Option 1")
        ratio = amount2 / (amount1+0.001)
        sent_count = 0
        for user_id in playerAmount1.keys():
            betAmount = playerAmount1[user_id]
            if(betAmount > 0):
                winAmount = int(betAmount*ratio)
                players[user_id] += betAmount + winAmount
                user = await bot.fetch_user(user_id)
                try:
                    await user.send(
                        f"BET CALLED ON: **{description}**. RESULT: **{item1}**\n"
                        f"You bet: {betAmount} engbucks\n"
                        f"You won! You gained {winAmount} engbucks"
                    )
                    sent_count += 1
                except discord.Forbidden:
                    await ctx.send(f"Could not DM {user.name} ({user_id}).")
            else:
                user = await bot.fetch_user(user_id)
                betAmount = playerAmount2[user_id]
                try:
                    await user.send(
                        f"BET CALLED ON: **{description}**. RESULT: **{item1}**\n"
                        f"You bet: {betAmount} engbucks\n"
                        f"You lost :("
                    )
                    sent_count += 1
                except discord.Forbidden:
                    await ctx.send(f"Could not DM {user.name} ({user_id}).")
            playerAmount1[user_id] = 0
            playerAmount2[user_id] = 0
        description = ""
        item1 = ""
        item2 = ""
        amount1 = 0
        amount2 = 0
        await ctx.send(f"Alert sent to {sent_count} users.")
    elif str(payload.emoji) == '2️⃣':
        await ctx.send("confirmed : Option 2")
        ratio = amount1 / (amount2+0.001) 
        sent_count = 0
        for user_id in playerAmount2.keys():
            betAmount = playerAmount2[user_id]
            if(betAmount > 0):
                winAmount = int(betAmount*ratio)
                players[user_id] += betAmount + winAmount
                user = await bot.fetch_user(user_id)
                try:
                    await user.send(
                        f"BET CALLED ON: **{description}**. RESULT: **{item2}**\n"
                        f"You bet: {betAmount} engbucks\n"
                        f"You won! You gained {winAmount} engbucks"
                    )
                    sent_count += 1
                except discord.Forbidden:
                    await ctx.send(f"Could not DM {user.name} ({user_id}).")
            else:
                user = await bot.fetch_user(user_id)
                betAmount = playerAmount1[user_id]
                try:
                    await user.send(
                        f"BET CALLED ON: **{description}**. RESULT: **{item2}**\n"
                        f"You bet: {betAmount} engbucks\n"
                        f"You lost :("
                    )
                    sent_count += 1
                except discord.Forbidden:
                    await ctx.send(f"Could not DM {user.name} ({user_id}).")
            playerAmount1[user_id] = 0
            playerAmount2[user_id] = 0
        description = ""
        item1 = ""
        item2 = ""
        amount1 = 0
        amount2 = 0
        await ctx.send(f"Alert sent to {sent_count} users.")
    else:
        await ctx.send("call cancelled.")


@bot.command()
async def save(ctx, file = SAVE_FILE):
    """Persist the current game state to disk (admin only)."""
    if ctx.author.id not in admin_users:
        return

    # Everything you want to keep goes in this dict:
    data = {
        "players": players,
        "playerAmount1": playerAmount1,
        "playerAmount2": playerAmount2,
        "description": description,
        "item1": item1,
        "item2": item2,
        "amount1": amount1,
        "amount2": amount2,
        "accepting": accepting,
    }

    try:
        with open(file, "w", encoding="utf-8") as fp:
            json.dump(data, fp, indent=4)
        await ctx.send(f"Game state saved to **{file}**.")
    except Exception as e:
        await ctx.send(f"Failed to save: `{e}`")


@bot.command()
async def load(ctx):
    global description, item1, item2, amount1, amount2, accepting, SAVE_FILE
    if ctx.author.id not in admin_users:
        return
    
    save_cmd = bot.get_command('save')
    await ctx.invoke(save_cmd, file="backup_"+SAVE_FILE)

    try:
        with open(SAVE_FILE, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except FileNotFoundError:
        await ctx.send("No save file found.")
        return
    except Exception as e:
        await ctx.send(f"Failed to load: `{e}`")
        return

    players.clear()
    players.update({int(k): v for k, v in data.get("players", {}).items()})

    playerAmount1.clear()
    playerAmount1.update({int(k): v for k, v in data.get("playerAmount1", {}).items()})

    playerAmount2.clear()
    playerAmount2.update({int(k): v for k, v in data.get("playerAmount2", {}).items()})

    description = data.get("description", "")
    item1       = data.get("item1", "")
    item2       = data.get("item2", "")
    amount1     = data.get("amount1", 0)
    amount2     = data.get("amount2", 0)
    accepting   = data.get("accepting", False)

    await ctx.send(f"Game state loaded from **{SAVE_FILE}**.")

@bot.command()
async def help(ctx):
    await ctx.send("Welcome to the council 5 game! This game will last the whole council. Your goal is to make as many engbucks as possible. Each player will start out with 100 engbucks and you can make more by gambling on the bets that are sent out. Each bet will be open for a short period of time where you can use the !bet [amount] command to gamble. If you gambled correctly, you will get back the amount you bet, as well as a portion of the amount bet incorrectly (proportional to how much you bet). \n**COMMANDS:**\n  !join - join the game\n  !info - get information about your wallet and the current bet\n  !bet [amount] - gamble an amount of engbucks from your wallet (you will be asked which side you bet on after)\nCommands can be sent in the #bots channel of the A-Soc rep Discord server or in the bot's DMs (recommended).")

bot.run(DISCORD_TOKEN)