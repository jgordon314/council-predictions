import os
import discord
from discord.ext import commands
import asyncio
import math
import traceback
from dotenv import load_dotenv
import json

SAVE_FILE = "players.json"
BACKUP_FILE = "backup_" + SAVE_FILE

load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_KEY')

# Set up Discord intents
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

players = {}
# ADMINS can be a single ID or a comma-separated list of IDs
admin_users = [int(x) for x in os.getenv('ADMINS', '').split(',') if x.strip()]
playerAmount1 = {}
playerAmount2 = {}

# Players currently looking at an unanswered !bet confirmation
pending_bets = set()

accepting = False
description = ""
item1 = ""
item2 = ""
amount1 = 0
amount2 = 0

# Shown when a command is used with missing or invalid arguments
USAGE = {
    "bet": "!bet [amount]   e.g. !bet 50",
    "start": "!start [description, option 1, option 2]",
    "alert": "!alert [message]",
}


# --- persistence -------------------------------------------------------------
def persist(file=SAVE_FILE):
    """Write the current game state to disk. Returns an error string, or None on success."""
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
        return None
    except Exception as e:
        print(f"Failed to save game state to {file}: {e}")
        return str(e)


def load_state(file=SAVE_FILE):
    """Load game state from disk. Returns an error string, or None on success."""
    global description, item1, item2, amount1, amount2, accepting
    try:
        with open(file, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except FileNotFoundError:
        return "No save file found."
    except Exception as e:
        return f"Failed to load: `{e}`"

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
    return None


# --- helpers -----------------------------------------------------------------
async def require_admin(ctx):
    """Return True if the author is an admin; otherwise tell them and return False."""
    if ctx.author.id in admin_users:
        return True
    await ctx.send("That's an admin command.")
    return False


async def get_user(user_id):
    """Look a user up in the cache first, only asking Discord if they aren't cached."""
    return bot.get_user(user_id) or await bot.fetch_user(user_id)


async def send_chunked(ctx, header, lines, limit=2000):
    """Send header + lines, split across as many messages as needed to stay under Discord's limit."""
    chunk = header
    for line in lines:
        if len(chunk) + len(line) + 1 > limit:
            await ctx.send(chunk)
            chunk = ""
        chunk += ("\n" if chunk else "") + line
    if chunk:
        await ctx.send(chunk)


async def dm_users(ctx, messages):
    """DM each user their message ({user_id: text}). Returns how many were sent.
    A failure for one user never stops the others; failures are reported to ctx at the end."""
    sent_count = 0
    failures = []
    for user_id, text in messages.items():
        user = None
        try:
            user = await get_user(user_id)
            await user.send(text)
            sent_count += 1
        except discord.HTTPException as e:   # covers Forbidden (DMs off) and NotFound (deleted account)
            name = user.name if user else "unknown user"
            failures.append(f"{name} ({user_id}): {e.__class__.__name__}")
    if failures:
        await send_chunked(ctx, "Could not DM:", failures)
    return sent_count


def bet_summary():
    total = amount1 + amount2
    return (
        f"Total amount bet: {total} engbucks\n"
        f"Option 1: {item1} - {amount1} engbucks bet ({math.ceil(100*amount1/(total+0.01))}%)\n"
        f"Option 2: {item2} - {amount2} engbucks bet ({math.ceil(100*amount2/(total+0.01))}%)"
    )


# --- events ------------------------------------------------------------------
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        # Only answer in DMs so we don't reply to other bots' commands in shared channels
        if isinstance(ctx.channel, discord.DMChannel):
            await ctx.send("Unknown command. Use !help to see the list of commands.")
        return
    if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
        usage = USAGE.get(ctx.command.name, f"!{ctx.command.name}")
        await ctx.send(f"Usage: `{usage}`")
        return
    print(f"Error in command {ctx.command}:")
    traceback.print_exception(type(error), error, error.__traceback__)
    await ctx.send("Something went wrong running that command.")


# --- player commands ---------------------------------------------------------
@bot.command()
async def join(ctx):
    user_id = ctx.author.id
    if user_id not in players.keys():
        players[user_id] = 100
        playerAmount1[user_id] = 0
        playerAmount2[user_id] = 0
        persist()
        message = f'{ctx.author.name}, you have joined the game!'
    else:
        message = f'{ctx.author.name}, you are already in the game!'
    try:
        await ctx.author.send(message)
        await ctx.message.add_reaction('🪿')
    except discord.Forbidden:
        await ctx.send(f"{message} (I couldn't DM you. Please check your privacy settings.)")


@bot.command()
async def info(ctx):
    if(ctx.author.id not in players.keys()):
        await ctx.send("Please join the game first with !join")
        return
    if(description == ""):
        await ctx.send(f"There is no bet currently active.\nAmount in your wallet: {players[ctx.author.id]}")
        return
    if(accepting):
        status = "This bet is still open. Use !bet [amount] to join this bet."
    else:
        status = "This bet is now closed."
    bets = []
    if(playerAmount1[ctx.author.id] > 0):
        bets.append(f"{playerAmount1[ctx.author.id]} on option 1")
    if(playerAmount2[ctx.author.id] > 0):
        bets.append(f"{playerAmount2[ctx.author.id]} on option 2")
    investment = ", ".join(bets) if bets else "Have not bet any engbucks"
    await ctx.send(
        f"**{description}**\n"
        f"{bet_summary()}\n\n"
        f"Amount you bet: {investment}\n"
        f"Amount in your wallet: {players[ctx.author.id]}\n"
        f"{status}"
    )


@bot.command()
async def bet(ctx, *, message: str):
    global amount1, amount2
    user_id = ctx.author.id

    # --- basic validation ----------------------------------------------------
    if description == "":
        await ctx.send("There is no currently active bet.")
        return
    if not accepting:
        await ctx.send("This bet is now closed. Use !info to see the active bet.")
        return
    try:
        amount = int(message)
    except ValueError:
        await ctx.send("Please enter the amount you would like to bet with your command. Example: !bet 50")
        return
    if(user_id not in players.keys()):
        await ctx.send("Please join the game first with !join")
        return
    if(amount <= 0):
        await ctx.send("You need to bet at least 1 engbuck.")
        return
    if(amount > players[user_id]):
        await ctx.send(f"Insufficient funds, you have {players[user_id]} in your wallet.")
        return
    if user_id in pending_bets:
        await ctx.send("You already have a bet waiting for confirmation. React to that one first.")
        return

    # Players may only back one side: if they've already bet, lock them to that side
    if playerAmount1[user_id] > 0:
        options = ('1️⃣', '❌')
        prompt = f"React with 1️⃣ to add it to your bet on option 1 ({item1}), or ❌ to cancel."
    elif playerAmount2[user_id] > 0:
        options = ('2️⃣', '❌')
        prompt = f"React with 2️⃣ to add it to your bet on option 2 ({item2}), or ❌ to cancel."
    else:
        options = ('1️⃣', '2️⃣', '❌')
        prompt = "React with 1️⃣ to put it on option 1, 2️⃣ for option 2, or ❌ to cancel."

    # --- confirmation --------------------------------------------------------
    pending_bets.add(user_id)
    try:
        confirm_msg = await ctx.send(
            f"You would like to invest {amount} engbucks into: \n**{description}**\n"
            f"**Option 1:** {item1}\n**Option 2:** {item2}\n"
            f"{prompt}"
        )
        for emoji in options:
            await confirm_msg.add_reaction(emoji)

        def check(payload: discord.RawReactionActionEvent):
            return (
                payload.message_id == confirm_msg.id
                and payload.user_id   == user_id
                and str(payload.emoji) in options
            )

        try:
            payload = await bot.wait_for('raw_reaction_add', timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send("Confirmation timed out - amount not bet.")
            return

        choice = str(payload.emoji)
        if choice == '❌':
            await ctx.send("Bet cancelled.")
            return

        # Things may have changed while we were waiting for the reaction
        if not accepting or description == "":
            await ctx.send("Betting closed before you confirmed - amount not bet.")
            return
        if amount > players[user_id]:
            await ctx.send(f"Insufficient funds, you have {players[user_id]} in your wallet.")
            return

        players[user_id] -= amount
        if choice == '1️⃣':
            amount1 += amount
            playerAmount1[user_id] += amount
            chosen = item1
        else:
            amount2 += amount
            playerAmount2[user_id] += amount
            chosen = item2
        await ctx.send(f"Bet confirmed: **{amount} engbucks** on **{chosen}**. Use !bet [amount] to increase your bet.")
    finally:
        pending_bets.discard(user_id)


# --- admin commands ----------------------------------------------------------
@bot.command()
async def player_info(ctx):
    if not await require_admin(ctx):
        return
    if not players:
        await ctx.send("No users have joined yet.")
        return
    ids = list(players.keys())
    # Look everyone up at once instead of one at a time
    users = await asyncio.gather(*(get_user(uid) for uid in ids), return_exceptions=True)
    user_info = []
    for user_id, user in zip(ids, users):
        name = "unknown user" if isinstance(user, Exception) else user.name
        user_info.append(f"{name} ({user_id}) - {players[user_id]}")
    await send_chunked(ctx, f"Joined users ({len(ids)}):", user_info)


@bot.command()
async def alert(ctx, *, message: str):
    if not await require_admin(ctx):
        return
    if players.keys():
        sent_count = await dm_users(ctx, {user_id: message for user_id in players.keys()})
        await ctx.send(f"Alert sent to {sent_count} users.")
    else:
        await ctx.send("No users have joined yet.")


@bot.command()
async def start(ctx, *, message: str):
    global description, item1, item2, accepting

    if not await require_admin(ctx):
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

    # --- confirmation --------------------------------------------------------
    confirm_msg = await ctx.send(
        f"New bet started!\n**Description:** {description}\n"
        f"**Option 1:** {item1}\n**Option 2:** {item2}\n"
        "React with ✅ to confirm or ❌ to cancel."
    )
    await confirm_msg.add_reaction('✅')
    await confirm_msg.add_reaction('❌')

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
        accepting = True
        alert_cmd = bot.get_command('alert')
        await ctx.invoke(alert_cmd, message=(
            f"New bet has started!\n**{description}**\n"
            f"Option 1 - {item1}\nOption 2 - {item2}\n"
            "Use !info to view the current odds, and !bet [amount] to join this bet."
        ))
    else:
        await ctx.send("Bet cancelled.")
        description = item1 = item2 = ""


@bot.command()
async def close(ctx):
    global accepting
    if not await require_admin(ctx):
        return
    if description == "":
        await ctx.send("There is no currently active bet.")
        return
    if not accepting:
        await ctx.send("This bet is already closed. Use !call to call the result.")
        return
    accepting = False
    persist()
    alert_cmd = bot.get_command('alert')
    await ctx.invoke(alert_cmd, message=f"Betting has now closed on **{description}**\n{bet_summary()}")


async def payout(ctx, winner):
    """Pay out the current bet. winner is 1 or 2."""
    global description, item1, item2, amount1, amount2

    win_name = item1 if winner == 1 else item2
    win_bets, lose_bets = (playerAmount1, playerAmount2) if winner == 1 else (playerAmount2, playerAmount1)
    win_pool, lose_pool = (amount1, amount2) if winner == 1 else (amount2, amount1)
    refund = win_pool == 0   # nobody picked the winner: give everyone their money back

    results = {}
    for user_id in players.keys():
        won = win_bets.get(user_id, 0)
        lost = lose_bets.get(user_id, 0)
        if won == 0 and lost == 0:
            continue
        if refund:
            players[user_id] += won + lost
            results[user_id] = f"Nobody bet on the winning option, so your {won + lost} engbucks have been refunded."
        else:
            winAmount = int(won * lose_pool / win_pool)
            players[user_id] += won + winAmount
            if won > 0:
                results[user_id] = f"You bet: {won} engbucks\nYou won! You gained {winAmount} engbucks"
            else:
                results[user_id] = f"You bet: {lost} engbucks\nYou lost :("
                # Losers never drop to 0 - they always keep at least 1 engbuck
                if players[user_id] < 1:
                    players[user_id] = 1
                    results[user_id] += "\nYou've been given 1 engbuck so you can keep playing."

    for user_id in players.keys():
        playerAmount1[user_id] = 0
        playerAmount2[user_id] = 0
    called_description = description
    description = item1 = item2 = ""
    amount1 = amount2 = 0
    persist()

    sent_count = await dm_users(ctx, {
        user_id: f"BET CALLED ON: **{called_description}**. RESULT: **{win_name}**\n{result}"
        for user_id, result in results.items()
    })
    if refund:
        await ctx.send("Nobody bet on the winning option - all bets were refunded.")
    await ctx.send(f"Alert sent to {sent_count} users.")


@bot.command()
async def call(ctx):
    if not await require_admin(ctx):
        return

    # --- basic validation ----------------------------------------------------
    if description == "":
        await ctx.send("There is no currently active bet.")
        return
    if accepting:
        await ctx.send("Please close the bet before calling it")
        return

    # --- confirmation --------------------------------------------------------
    confirm_msg = await ctx.send(
        f"Calling the result of **{description}**\n{bet_summary()}\n"
        "Please select which bet won:"
    )
    await confirm_msg.add_reaction('1️⃣')
    await confirm_msg.add_reaction('2️⃣')
    await confirm_msg.add_reaction('❌')

    def check(payload: discord.RawReactionActionEvent):
        return (
            payload.message_id == confirm_msg.id
            and payload.user_id   == ctx.author.id
            and str(payload.emoji) in ('1️⃣', '2️⃣', '❌')
        )

    try:
        payload = await bot.wait_for('raw_reaction_add', timeout=30.0, check=check)
    except asyncio.TimeoutError:
        await ctx.send("Confirmation timed out - bet not called.")
        return

    if description == "":   # someone else called it while we were waiting
        await ctx.send("This bet has already been called.")
        return

    if str(payload.emoji) == '1️⃣':
        await ctx.send("confirmed : Option 1")
        await payout(ctx, 1)
    elif str(payload.emoji) == '2️⃣':
        await ctx.send("confirmed : Option 2")
        await payout(ctx, 2)
    else:
        await ctx.send("call cancelled.")


@bot.command()
async def save(ctx):
    """Persist the current game state to disk (admin only)."""
    if not await require_admin(ctx):
        return
    error = persist()
    if error:
        await ctx.send(f"Failed to save: `{error}`")
    else:
        await ctx.send(f"Game state saved to **{SAVE_FILE}**.")


@bot.command()
async def load(ctx):
    """Reload the game state from disk, backing up the current state first (admin only)."""
    if not await require_admin(ctx):
        return

    error = persist(BACKUP_FILE)
    if error:
        await ctx.send(f"Could not back up the current state, load aborted: `{error}`")
        return

    error = load_state()
    if error:
        await ctx.send(error)
        return
    await ctx.send(f"Game state loaded from **{SAVE_FILE}** (previous state backed up to **{BACKUP_FILE}**).")


@bot.command()
async def help(ctx):
    await ctx.send("Welcome to the council 5 game! This game will last the whole council. Your goal is to make as many engbucks as possible. Each player will start out with 100 engbucks and you can make more by gambling on the bets that are sent out. Each bet will be open for a short period of time where you can use the !bet [amount] command to gamble. If you gambled correctly, you will get back the amount you bet, as well as a portion of the amount bet incorrectly (proportional to how much you bet). \n**COMMANDS:**\n  !join - join the game\n  !info - get information about your wallet and the current bet\n  !bet [amount] - gamble an amount of engbucks from your wallet (you will be asked which side you bet on after)\nCommands can be sent in the #bots channel of the A-Soc rep Discord server or in the bot's DMs (recommended).")
    if ctx.author.id in admin_users:
        await ctx.send("Admin commands:\n  !start [description, option 1, option 2] - start a new bet\n  !close - close the current bet\n  !call - call the result of the current bet\n  !alert [message] - send a message to all players\n  !player_info - list all players and their wallets\n  !save - save the game state to disk (also happens automatically)\n  !load - reload the game state from disk (the current state is backed up first)")


# Restore the previous game automatically on startup
if os.path.exists(SAVE_FILE):
    load_error = load_state()
    print(load_error or f"Loaded game state from {SAVE_FILE}")

bot.run(DISCORD_TOKEN)
