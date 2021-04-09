import ast
import base64
import inspect
import logging
import textwrap
import time
import typing
from io import BytesIO
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


class Meta(commands.Cog):
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

    def _get_get_source(self, func, json, branch=None):
        source_code = base64.b64decode(json["content"]).decode("utf-8")
        line_num = None
        the_ast = ast.parse(source_code)
        for node in ast.walk(the_ast):
            if isinstance(node, ast.AsyncFunctionDef) or isinstance(
                node, ast.FunctionDef
            ):
                if getattr(node, "name", "") == func:
                    line_num = node.lineno - len(node.decorator_list)

                    end_line_num = node.end_lineno
                    break

        if line_num is None:
            return None, branch, None, None
        if branch is None:
            branch = json["url"].split("?ref=", 1)[1]
        path = json["path"].lstrip("/")
        return (
            "{0}/{1}/{2}/tree/{6}/{3}#L{4}-L{5}".format(
                Github.base_link,
                Github.Me.org,
                Github.Me.repo,
                path,
                line_num,
                end_line_num,
                branch,
            ),
            branch,
            ast.get_docstring(node),
            path,
        )

    async def _get_source(self, func: str, file, branch=None):
        src_link_no_branch = "{0}/repos/{1}/{2}/contents/{3}".format(
            Github.api_link, Github.Me.org, Github.Me.repo, file.lstrip("/")
        )
        # try the master branch
        async with self.bot.http_session.get(f"{src_link_no_branch}") as resp:
            if resp.status != 404 and resp.status != 200:
                raise commands.CommandError("Command Not [on github].")
            json = await resp.json()

        link, found_branch, docstring, path = self._get_get_source(func, json)
        if link is None and branch is not None and found_branch != branch:
            async with self.bot.http_session.get(
                f"{src_link_no_branch}?ref={branch}"
            ) as resp:
                if resp.status != 200:
                    raise commands.CommandError("Command Not [on github].")
                json = await resp.json()
            link, found_branch, docstring, _ = self._get_get_source(func, json, branch)
        if link is None:
            raise commands.CommandError("Command Not [on github].")
        return link, docstring, found_branch

    @commands.command(name="source", aliases=["src", "code"])
    async def source(self, ctx: commands.Context, source_item: str = None):
        """Get a github link to the source code of a command."""
        if source_item is None:
            await ctx.send(github_link)
            return

        # send a typing event while we get from github
        # normally this would be an async with,
        # but no reason to do so since it shouldn't take very long to do this code,
        # therefore no reason to make it with.
        # if its been long enough that it has to fire again we've errorer or send a response
        await ctx.trigger_typing()

        cmd = self.bot.get_command(source_item)

        if cmd is None:
            raise commands.CommandError("Couldn't find command.")
        callback = cmd.callback
        source_file = str(
            Path(inspect.getsourcefile(callback)).relative_to(str(Path.cwd()))
        )

        # determine the current branch
        # this is used to get which branch we should look in on the repo if we can't find the command on the main/master branch
        repo = pygit2.Repository(".git")
        for branch in list(repo.branches.local):
            b = repo.lookup_branch(branch)
            if b.is_head():
                break

        link, doc_string, branch = await self._get_source(
            callback.__name__, source_file, branch
        )

        # check for image permissions and if we don't have them then just send the link and be lazy.
        if not ctx.channel.permissions_for(ctx.me) >= discord.Permissions(
            embed_links=True, attach_files=True
        ):
            await ctx.send(link)
            return

        # make a fancy embed!
        e = discord.Embed()
        e.description = f"{doc_string}\n\n" f""
        e.title = cmd.qualified_name
        thumb = discord.File(
            BytesIO(await self.bot.user.avatar_url_as(format="png").read()),
            filename="thumb.png",
        )
        e.set_thumbnail(url="attachment://thumb.png")
        e.set_footer(text=f"/{source_file}")
        e.add_field(
            name="Source Code",
            value=f"[Open in Github]({link}) {self.bot.get_emoji(828722619925790720)}",
            inline=True,
        )
        if branch not in ["main", "master"]:
            e.add_field(
                name="Branch",
                value=branch,
            )
        await ctx.send(embed=e, file=thumb)


def setup(bot: Bot):
    bot.add_cog(Meta(bot))
