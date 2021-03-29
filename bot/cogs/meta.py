import logging
import time
import typing

import discord
import verboselogs
# if typing.TYPE_CHECKING:
from bot import Bot
from discord.ext import commands  # Again, we need this imported

log: verboselogs.VerboseLogger = logging.getLogger(__name__)


class SomeCommands(commands.Cog):
    """A couple of simple commands."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context):
        """Get the bot's current websocket and API latency."""
        start_time = time.time()
        message = await ctx.send("Ping!")
        end_time = time.time()

        await message.edit(content=f"Pong! {round(self.bot.latency * 1000)}ms\nAPI: {round((end_time - start_time) * 1000)}ms")

    @commands.command(name="invite")
    async def _invite(self, ctx: commands.Context):
        """Return the bot invite, and a notice if it is not public."""
        app_info: discord.AppInfo = await self.bot.application_info()
        ctx.reply(f'Invite me here!\n<{self.bot.invite_link.format(self.bot.user.id)}> \n'
                  '**Warning!** I am currently not a public bot and may never be!' if not app_info.bot_public else ''
                  )


def setup(bot: Bot):
    bot.add_cog(SomeCommands(bot))
