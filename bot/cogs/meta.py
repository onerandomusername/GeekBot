import inspect
import logging
import time
import typing
from pathlib import Path

import discord
import verboselogs
from bot import Bot
from constants import github_link
from discord.ext import commands

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

    @commands.command(name='source', aliases=['src','code'])
    async def source(self, ctx: commands.Context, source_item: str = None):
        if source_item is None:
            await ctx.send(github_link)
            return
        
        cmd = self.bot.get_command(source_item)

        if cmd is None:
            raise commands.CommandError('Couldn\'t find command.')
        
        source_lines = inspect.getsourcelines(cmd.callback)
        source_file = inspect.getsourcefile(cmd.callback)

        length, start_line = len(source_lines[0]), source_lines[1]
        end_line = start_line + length
        Path.cwd()
        link = f'{github_link}/tree/main/{Path(source_file).relative_to(str(Path.cwd()))}'
        link += f'#L{start_line}-L{end_line}'
        await ctx.send(link)


def setup(bot: Bot):
    bot.add_cog(SomeCommands(bot))
