import ast
import base64
import inspect
import logging
import textwrap
import time
import typing
from pathlib import Path

import discord
import pygit2
import verboselogs
from bot import Bot
from constants import Github
from discord.errors import DiscordException
from discord.ext import commands
from utils.file import create_file_obj

github_link = Github.Me.html_link
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

        await message.edit(
            content=f"Pong! {round(self.bot.latency * 1000)}ms\nAPI: {round((end_time - start_time) * 1000)}ms"
        )

    @commands.command(name="invite")
    async def _invite(self, ctx: commands.Context):
        """Return the bot invite, and a notice if it is not public."""
        app_info: discord.AppInfo = await self.bot.application_info()
        await ctx.reply(
            f"Invite me here!\n<{self.bot.invite_link.format(self.bot.user.id)}> \n"
            "**Warning!** I am currently not a public bot and may never be!"
            if not app_info.bot_public
            else ""
        )

    async def _get_github_source(
        self, ctx: commands.Context, command: str, file, length
    ):
        src_link = "{0}/repos/{1}/{2}/contents/{3}".format(
            Github.api_link, Github.Me.org, Github.Me.repo, file.lstrip("/")
        )
        async with self.bot.http_session.get(src_link) as resp:
            if resp.status != 200:
                raise commands.CommandError("Command Not [on github].")
            json = await resp.json()
            source_code = base64.b64decode(json["content"]).decode("utf-8")
            line_num = None
            the_ast = ast.parse(source_code)
            for node in ast.walk(the_ast):
                if isinstance(node, ast.AsyncFunctionDef) or isinstance(
                    node, ast.FunctionDef
                ):
                    if getattr(node, "name", "") == command:
                        line_num = node.lineno - len(node.decorator_list)

                        end_line_num = node.end_lineno
                        break

            if line_num is None:
                raise commands.CommandError("Command Not [on github].")

            return "{0}/{1}/{2}/tree/main/{3}#L{4}-L{5}".format(
                Github.base_link,
                Github.Me.org,
                Github.Me.repo,
                file.lstrip("/"),
                line_num,
                end_line_num,
            )

    @commands.command(name="source", aliases=["src", "code"])
    async def source(self, ctx: commands.Context, source_item: str = None):
        """Get a github link to the source code of a command."""
        if source_item is None:
            await ctx.send(github_link)
            return
        cmd = self.bot.get_command(source_item)

        if cmd is None:
            raise commands.CommandError("Couldn't find command.")
        callback = cmd.callback
        source_lines = inspect.getsourcelines(callback)
        source_file = inspect.getsourcefile(callback)
        source_file = str(Path(source_file).relative_to(str(Path.cwd())))
        length, start_line = len(source_lines[0]), source_lines[1]
        end_line = start_line + length - 1

        repo = pygit2.Repository(".git")
        tree = None
        for branch in list(repo.branches.local):
            b = repo.lookup_branch(branch)
            if b.is_head():
                tree = branch
                break
        link = f"{github_link}/tree/{tree}/{source_file}"
        link += f"#L{start_line}-L{end_line}"
        link = await self._get_github_source(
            ctx, callback.__name__, source_file, length
        )
        if not ctx.channel.permissions_for(ctx.me) >= discord.Permissions(
            embed_links=True, attach_files=True
        ):
            await ctx.send(link)
            return

        # make a fancy embed!
        e = discord.Embed()
        e.description = f"{cmd.short_doc}\n\n" f"[View on github.]({link})"
        e.title = cmd.qualified_name
        e.set_footer(text=f"/{source_file}")
        await ctx.send(embed=e)


def setup(bot: Bot):
    bot.add_cog(SomeCommands(bot))
