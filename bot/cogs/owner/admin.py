"""
Original Source: https://github.com/Rapptz/RoboDanny/blob/e1d5da9c87ec71b0c072798704254c4595ad4b94/cogs/admin.py

LICENSE:
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
import ast
import asyncio
import copy

# to expose to the eval command
import datetime
import importlib
import inspect
import io
import logging
import os
import re
import subprocess
import sys
import textwrap
import time
import traceback

# to expose to the eval command
from collections import Counter
from contextlib import redirect_stdout

# to expose to the eval command
from pprint import pprint
from types import FunctionType
from typing import Optional, Union

import discord
import verboselogs
from bot import Bot
from constants import MESSAGE_LIMIT
from discord.ext import commands
from utils.file import create_file_obj

log: verboselogs.VerboseLogger = logging.getLogger(__name__)


class PerformanceMocker:
    """A mock object that can also be used in await expressions."""

    def __init__(self):
        self.loop = asyncio.get_event_loop()

    def permissions_for(self, obj):
        # Lie and say we don't have permissions to embed
        # This makes it so pagination sessions just abruptly end on __init__
        # Most checks based on permission have a bypass for the owner anyway
        # So this lie will not affect the actual command invocation.
        perms = discord.Permissions.all()
        perms.administrator = False
        perms.embed_links = False
        perms.add_reactions = False
        return perms

    def __getattr__(self, attr):
        return self

    def __call__(self, *args, **kwargs):
        return self

    def __repr__(self):
        return "<PerformanceMocker>"

    def __await__(self):
        future = self.loop.create_future()
        future.set_result(self)
        return future.__await__()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return self

    def __len__(self):
        return 0

    def __bool__(self):
        return False


class GlobalChannel(commands.Converter):
    async def convert(self, ctx, argument):
        try:
            return await commands.TextChannelConverter().convert(ctx, argument)
        except commands.BadArgument:
            # Not found... so fall back to ID + global lookup
            try:
                channel_id = int(argument, base=10)
            except ValueError:
                raise commands.BadArgument(
                    f"Could not find a channel by ID {argument!r}."
                )
            else:
                channel = ctx.bot.get_channel(channel_id)
                if channel is None:
                    raise commands.BadArgument(
                        f"Could not find a channel by ID {argument!r}."
                    )
                return channel


class Admin(commands.Cog):
    """Admin-only commands that make the bot dynamic."""

    def __init__(self, bot: Bot):
        log.debug("loading cog Admin")
        self.bot = bot
        self._last_result = None
        self.sessions = set()

    async def run_process(self, command):
        try:
            process = await asyncio.create_subprocess_shell(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            result = await process.communicate()
        except NotImplementedError:
            process = subprocess.Popen(
                command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            result = await self.bot.loop.run_in_executor(None, process.communicate)

        return [output.decode() for output in result]

    def cleanup_code(self, content):
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith("```") and content.endswith("```"):
            content = "\n".join(content.split("\n")[1:-1])

        # remove `foo`
        content = content.strip("` \n").strip("`")

        # so we can copy paste code, dedent it.
        content = textwrap.dedent(content)

        return content

    async def cog_check(self, ctx):
        return await self.bot.is_owner(ctx.author)

    def get_syntax_error(self, e):
        if e.text is None:
            return f"```py\n{e.__class__.__name__}: {e}\n```"
        return f'```py\n{e.text}{"^":>{e.offset}}\n{e.__class__.__name__}: {e}```'

    @commands.command(hidden=True)
    async def load(self, ctx, *, module):
        """Loads a module."""
        try:
            self.bot.load_extension(module)
        except commands.ExtensionError as e:
            await ctx.send(f"{e.__class__.__name__}: {e}")
        else:
            await ctx.send("\N{OK HAND SIGN}")

    @commands.command(hidden=True)
    async def unload(self, ctx, *, module):
        """Unloads a module."""
        try:
            self.bot.unload_extension(module)
        except commands.ExtensionError as e:
            await ctx.send(f"{e.__class__.__name__}: {e}")
        else:
            await ctx.send("\N{OK HAND SIGN}")

    @commands.group(name="reload", hidden=True, invoke_without_command=True)
    async def _reload(self, ctx, *, module):
        """Reloads a module."""
        try:
            self.bot.reload_extension(module)
        except commands.ExtensionError as e:
            await ctx.send(f"{e.__class__.__name__}: {e}")
        else:
            await ctx.send("\N{OK HAND SIGN}")

    _GIT_PULL_REGEX = re.compile(r"\s*(?P<filename>.+?)\s*\|\s*[0-9]+\s*[+-]+")

    def find_modules_from_git(self, output):
        files = self._GIT_PULL_REGEX.findall(output)
        ret = []
        for file in files:
            root, ext = os.path.splitext(file)
            if ext != ".py":
                continue

            if root.startswith("cogs/"):
                # A submodule is a directory inside the main cog directory for
                # my purposes
                ret.append((root.count("/") - 1, root.replace("/", ".")))

        # For reload order, the submodules should be reloaded first
        ret.sort(reverse=True)
        return ret

    def reload_or_load_extension(self, module):
        try:
            self.bot.reload_extension(module)
        except commands.ExtensionNotLoaded:
            self.bot.load_extension(module)

    # @_reload.command(name='all', hidden=True)
    # async def _reload_all(self, ctx):
    #     """Reloads all modules, while pulling from git."""

    #     async with ctx.typing():
    #         stdout, stderr = await self.run_process('git pull')

    #     # progress and stuff is redirected to stderr in git pull
    #     # however, things like "fast forward" and files
    #     # along with the text "already up-to-date" are in stdout

    #     if stdout.startswith('Already up-to-date.'):
    #         return await ctx.send(stdout)

    #     modules = self.find_modules_from_git(stdout)
    #     mods_text = '\n'.join(f'{index}. `{module}`' for index, (_, module) in enumerate(modules, start=1))
    #     prompt_text = f'This will update the following modules, are you sure?\n{mods_text}'
    #     confirm = await ctx.prompt(prompt_text, reacquire=False)
    #     if not confirm:
    #         return await ctx.send('Aborting.')

    #     statuses = []
    #     for is_submodule, module in modules:
    #         if is_submodule:
    #             try:
    #                 actual_module = sys.modules[module]
    #             except KeyError:
    #                 statuses.append((ctx.tick(None), module))
    #             else:
    #                 try:
    #                     importlib.reload(actual_module)
    #                 except Exception as e:
    #                     statuses.append((ctx.tick(False), module))
    #                 else:
    #                     statuses.append((ctx.tick(True), module))
    #         else:
    #             try:
    #                 self.reload_or_load_extension(module)
    #             except commands.ExtensionError:
    #                 statuses.append((ctx.tick(False), module))
    #             else:
    #                 statuses.append((ctx.tick(True), module))

    #     await ctx.send('\n'.join(f'{status}: `{module}`' for status, module in statuses))

    @staticmethod
    def _runwith(code: str):
        """determine the meth to run the code with"""
        code = code.strip()
        if ";" in code:
            return exec
        elif "\n" in code:
            if code.count("\\\n") == code.count("\n"):
                return eval
            else:
                return exec
        elif code.count("\n"):
            return exec
        else:
            return eval

    async def _send_stdout(
        self,
        ctx: commands.Context,
        resp: str = None,
        error: Exception = None,
        runtime=None,
    ) -> discord.Message:
        """Send a nicely formatted eval response"""
        if resp is None and error is None:
            return None
            return await ctx.send(
                "No output.",
                allowed_mentions=discord.AllowedMentions(replied_user=False),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        resp_file: discord.File = None
        # for now, we're not gonna handle exceptions as files
        # unless, for some reason, it has a ``` in it
        error_file: discord.File = None
        total_len = 0
        fmt_resp: str = "```py\n{}```"
        fmt_err: str = "\nAn error occured. Unforunate.```py\n{}```"
        out = ""
        files = []

        # make a resp object
        if resp is not None:
            total_len += len(fmt_resp)
            total_len += len(resp)
            if "```" in resp:
                resp_file = True

        if error is not None:
            total_len += len(fmt_err)
            total_len += len(error)
            if "```" in error:
                error_file = True

        if total_len > MESSAGE_LIMIT or resp_file:
            log.debug("rats we gotta upload as a file")
            resp_file: discord.File = create_file_obj(resp, ext="py")
        else:
            # good job, not a file
            log.debug("sending response as plaintext")
            out += fmt_resp.format(resp) if resp is not None else ""
        out += fmt_err.format(error) if error is not None else ""

        for f in resp_file, error_file:
            if f is not None:
                files.append(f)
        return await ctx.send(
            out,
            files=files,
            allowed_mentions=discord.AllowedMentions(replied_user=False),
            reference=ctx.message.to_reference(fail_if_not_exists=False),
        )

    @commands.command(pass_context=True, hidden=True, name="eval", aliases=["e"])
    async def _eval(self, ctx: commands.Context, *, code: str):
        """Evaluates provided code. Owner only."""
        log.spam("command _eval executed.")

        env = {
            "bot": self.bot,
            "ctx": ctx,
            "channel": ctx.channel,
            "author": ctx.author,
            "guild": ctx.guild,
            "message": ctx.message,
            "pprint": pprint,
            "_": self._last_result,
        }

        env.update(globals())
        log.spam("updated globals")
        code = self.cleanup_code(code)
        log.spam(f"body: {code}")
        stdout = io.StringIO()
        result = None
        error = None
        try:
            with redirect_stdout(stdout):
                runwith = self._runwith(code)
                log.spam(runwith.__name__)
                co_code = compile(
                    code,
                    "<int eval>",
                    runwith.__name__,
                    flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT,
                )

                if inspect.CO_COROUTINE & co_code.co_flags == inspect.CO_COROUTINE:
                    awaitable = FunctionType(co_code, env)
                    result = await awaitable()
                else:
                    result = runwith(co_code, env)
        except Exception:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            error = traceback.format_exception(exc_type, exc_value, exc_traceback)
            error.pop(1)
            error = "".join(error).strip()
        try:
            await ctx.message.add_reaction("\u2705")
        except Exception:
            pass
        log.spam(f"result: {result}")
        if result is not None:
            pprint(result, stream=stdout)
        result = stdout.getvalue()
        if result.rstrip("\n") == "":
            result = None
        self._last_result = result
        msg = await self._send_stdout(ctx=ctx, resp=result, error=error)
        return msg

    @commands.command(pass_context=True, hidden=True, name="print")
    async def _print(self, ctx, *, body: str):
        """Calls eval but wraps code in pprint()"""

        await ctx.invoke(self._eval, body=f"pprint({body})")

    @commands.command(pass_context=True, hidden=True)
    async def repl(self, ctx):
        """Launches an interactive REPL session."""
        variables = {
            "ctx": ctx,
            "bot": self.bot,
            "message": ctx.message,
            "guild": ctx.guild,
            "channel": ctx.channel,
            "author": ctx.author,
            "_": None,
        }

        if ctx.channel.id in self.sessions:
            await ctx.send(
                "Already running a REPL session in this channel. Exit it with `quit`."
            )
            return

        self.sessions.add(ctx.channel.id)
        await ctx.send("Enter code to execute or evaluate. `exit()` or `quit` to exit.")

        def check(m):
            return (
                m.author.id == ctx.author.id
                and m.channel.id == ctx.channel.id
                and m.content.startswith("`")
            )

        return await self._repl(ctx, variables, check)

    async def _clean_code(self, ctx: commands.Context, cleaned: str):
        executor = exec

        stop = False
        if cleaned.count("\n") == 0:
            # single statement, potentially 'eval'
            try:
                code = compile(cleaned, "<repl session>", "eval")
            except SyntaxError:
                pass
            else:
                executor = eval
        if executor is exec:
            try:
                code = compile(cleaned, "<repl session>", "exec")
            except SyntaxError as e:
                await ctx.send(self.get_syntax_error(e))
                stop = True
        return executor, code, stop

    async def _repl(self, ctx, variables, check):
        while True:
            try:
                response = await self.bot.wait_for(
                    "message", check=check, timeout=10.0 * 60.0
                )
            except asyncio.TimeoutError:
                await ctx.send("Exiting REPL session.")
                self.sessions.remove(ctx.channel.id)
                break
            cleaned = self.cleanup_code(response.content)
            if cleaned in ("quit", "exit", "exit()"):
                await ctx.send("Exiting.")
                self.sessions.remove(ctx.channel.id)
                return

            executor, code, stop = await self._clean_code(ctx, cleaned)

            variables["message"] = response
            fmt = None
            stdout = io.StringIO()
            try:
                with redirect_stdout(stdout):
                    result = executor(code, variables)
                    if inspect.isawaitable(result):
                        result = await result
            except Exception:
                value = stdout.getvalue()
                fmt = f"```py\n{value}{traceback.format_exc()}\n```"
            else:
                value = stdout.getvalue()
                if result is not None:
                    fmt = f"```py\n{value}{result}\n```"
                    variables["_"] = result
                elif value:
                    fmt = f"```py\n{value}\n```"
            try:
                if fmt is not None:
                    if len(fmt) > MESSAGE_LIMIT:
                        await ctx.send("Content too big to be printed.")
                    else:
                        await ctx.send(fmt)
            except discord.Forbidden:
                pass
            except discord.HTTPException as e:
                await ctx.send(f"Unexpected error: `{e}`")

    @commands.command(hidden=True)
    async def sudo(
        self,
        ctx,
        channel: Optional[GlobalChannel],
        who: Union[discord.Member, discord.User],
        *,
        command: str,
    ):
        """Run a command as another user optionally in another channel."""
        msg = copy.copy(ctx.message)
        channel = channel or ctx.channel
        msg.channel = channel
        msg.author = who
        msg.content = ctx.prefix + command
        new_ctx = await self.bot.get_context(msg, cls=type(ctx))
        new_ctx._db = ctx._db
        await self.bot.invoke(new_ctx)

    @commands.command(hidden=True)
    async def do(self, ctx, times: int, *, command):
        """Repeats a command a specified number of times."""
        msg = copy.copy(ctx.message)
        msg.content = ctx.prefix + command

        new_ctx = await self.bot.get_context(msg, cls=type(ctx))
        # new_ctx._db = ctx._db

        for i in range(times):
            await new_ctx.reinvoke()

    @commands.command(hidden=True)
    async def perf(self, ctx, *, command):
        """Checks the timing of a command, attempting to suppress HTTP and DB calls."""

        msg = copy.copy(ctx.message)
        msg.content = ctx.prefix + command

        new_ctx = await self.bot.get_context(msg, cls=type(ctx))
        # new_ctx._db = PerformanceMocker()

        # Intercepts the Messageable interface a bit
        new_ctx._state = PerformanceMocker()
        new_ctx.channel = PerformanceMocker()

        if new_ctx.command is None:
            return await ctx.send("No command found")

        start = time.perf_counter()
        try:
            await new_ctx.command.invoke(new_ctx)
        except commands.CommandError:
            end = time.perf_counter()
            success = False
            try:
                await ctx.send(f"```py\n{traceback.format_exc()}\n```")
            except discord.HTTPException:
                pass
        else:
            end = time.perf_counter()
            success = True

        await ctx.send(
            f"Status: {ctx.tick(success)} Time: {(end - start) * 1000:.2f}ms"
        )


def setup(bot: Bot):
    bot.add_cog(Admin(bot))
