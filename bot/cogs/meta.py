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
import pprint

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

            # this line needs to use a regex at some point, to find either where it defines the name, or where it defines the method
            cmd_line_POS = source_code.find(f"def {command}")

            if not cmd_line_POS >= 0:
                raise commands.CommandError("Command is not on github.")

            # find the beginning of this command's source.
            start_of_cmd = cmd_line_POS - source_code[cmd_line_POS::-1].find("\n\n")
            start_of_cmd += 1  # we checked for \n\n, this makes it the second `\n`
            line_num = source_code[:start_of_cmd].count("\n")
            split_source = source_code[start_of_cmd:].split("\n")
            # await ctx.send(
            #     "split_source", file=create_file_obj("\n".join(split_source), ext="py")
            # )
            original_indentation = " " * (
                len(split_source[0]) - len(split_source[0].lstrip())
            )
            end = line_num
            func_indent = original_indentation + " " * 4
            skip_lines = 2
            for i, line in enumerate(split_source[skip_lines:]):
                if bool(line.lstrip()) and not line.startswith(func_indent):
                    end += i + skip_lines
                    break

            # await ctx.send(f"line_num : {line_num}\nend: {end}")
            # await ctx.send(
            #     file=create_file_obj(
            #         textwrap.dedent(
            #             "\n".join(source_code.splitlines()[line_num : end + 1])
            #         ),
            #         ext="py",
            #     )
            # )
            return "{0}/{1}/{2}/tree/main/{3}#L{4}-L{5}".format(
                Github.base_link,
                Github.Me.org,
                Github.Me.repo,
                file.lstrip("/"),
                line_num + 1,
                end - 1,
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
            ctx, cmd.qualified_name, source_file, length
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
