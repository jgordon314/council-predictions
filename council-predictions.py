import os
import discord
from discord.ext import commands

# Load environment variables
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# Initialize the bot
bot = commands.Bot(command_prefix='!')

# Initialize the user list
user_list = []

# List of admin user IDs
admin_users = [123456789012345678]

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

@bot.command()
async def join(ctx):
    user_id = ctx.author.id
    if user_id not in user_list:
        user_list.append(user_id)
        await ctx.send(f'{ctx.author.name}, you have joined the list!')
    else:
        await ctx.send(f'{ctx.author.name}, you are already on the list!')

@bot.command()
async def joined_users(ctx):
    if ctx.author.id in admin_users:
        if user_list:
            names = []
            for user_id in user_list:
                user = await bot.fetch_user(user_id)
                names.append(user.name)
            await ctx.send("Joined users:\n" + "\n".join(names))
        else:
            await ctx.send("No users have joined yet.")
    else:
        await ctx.send("You do not have permission to use this command.")

bot.run(DISCORD_TOKEN)