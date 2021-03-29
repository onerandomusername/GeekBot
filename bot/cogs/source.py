# -*- coding: utf-8 -*-

from discord.ext import commands
import discord
from bot import Bot

class Source(commands.Cog):
    """Collection of source commands for de bot."""

    def __init__(self, bot: Bot):
        self.bot = bot
    
    @commands.command(name='source', aliases=['src','code'])
    async def source(self, ctx: commands.Context):
        await ctx.send(self.bot.github_link)

def setup(bot):
    bot.add_cog(Source(bot))
