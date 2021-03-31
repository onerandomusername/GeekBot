import inspect
import logging
import time
import typing
from pathlib import Path

import discord
from discord.errors import DiscordException
#from discord.utils import DISCORD_EPOCH
import pygit2
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
        await ctx.reply(f'Invite me here!\n<{self.bot.invite_link.format(self.bot.user.id)}> \n'
                        '**Warning!** I am currently not a public bot and may never be!' if not app_info.bot_public else ''
                        )

    @commands.command(name='source', aliases=['src', 'code'])
    async def source(self, ctx: commands.Context, source_item: str = None):
        '''Get a github link to the source code of a command.'''
        if source_item is None:
            await ctx.send(github_link)
            return
        cmd = self.bot.get_command(source_item)

        if cmd is None:
            raise commands.CommandError('Couldn\'t find command.')
        callback = cmd.callback
        source_lines = inspect.getsourcelines(callback)
        source_file = inspect.getsourcefile(callback)

        length, start_line = len(source_lines[0]), source_lines[1]
        end_line = start_line + length - 1
        repo = pygit2.Repository('.git')
        tree = None
        for branch in list(repo.branches.local):
            b = repo.lookup_branch(branch)
            if b.is_head():
                tree = branch
                break
        source_file = str(Path(source_file).relative_to(str(Path.cwd())))
        link = f'{github_link}/tree/{tree}/{source_file}'
        link += f'#L{start_line}-L{end_line}'
        if not ctx.channel.permissions_for(ctx.me) >= discord.Permissions(embed_links=True, attach_files=True):
            await ctx.send(link)
            return
        
        #make a fancy embed!
        e = discord.Embed()
        e.description=f'{cmd.short_doc}\n\n' \
                    f'[View on github.]({link})'
        e.title = source_item
        e.set_footer(text=f'/{source_file}')
        await ctx.send(embed=e)


def setup(bot: Bot):
    bot.add_cog(SomeCommands(bot))
