#! /opt/python-3.9.2/bin/python3.9

import asyncio
import logging

# import logging.handlers
import os
import socket
import sys
import warnings
from collections import defaultdict
from contextlib import suppress
from os import getenv
from typing import Dict, List, Optional

import aiohttp
import asyncpraw
import coloredlogs
import discord
import verboselogs
from discord.ext import commands
from dotenv import load_dotenv

from config import DESCRIPTION, LOG_LEVEL, TOKEN

EXTENSIONS = (
    "cogs.owner.admin",
    "cogs.cloudahk",
    "cogs.meta",
    "utils.error_handling",
)


def setup_logger():  # -> logging.getLogger:
    # init first log file
    # if not os.path.isfile('logs/log.log'):
    #    open('logs/log.log', 'w+')

    verboselogs.install()
    log: verboselogs.VerboseLogger = logging.getLogger(__name__)
    # set logging levels for various libs
    logging.getLogger("discord").setLevel(logging.INFO)
    logging.getLogger("websockets").setLevel(logging.INFO)
    logging.getLogger("asyncpg").setLevel(logging.INFO)
    logging.getLogger("asyncio").setLevel(logging.INFO)
    logging.getLogger("aiotrace").setLevel(logging.INFO)

    # we want our logging formatted like this everywhere
    # fmt = logging.Formatter(
    #     "{asctime} [{levelname}] {name}: {message}",
    #     datefmt="%Y-%m-%d %H:%M:%S",
    #     style="{",
    # )
    coloredlogs.install(
        level=verboselogs.SPAM, fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    log.success("Logger Configured.")
    # log.setFormatter(fmt)
    # stream = ColorStreamHandler(sys.stdout)
    # stream.setFormatter(fmt)
    # stream.setLevel(logging.DEBUG)

    # file = logging.handlers.TimedRotatingFileHandler(
    #     'logs/log.log', when='midnight', encoding='utf-8-sig')
    # file.setFormatter(fmt)
    # file.setLevel(logging.INFO)

    # get the __main__ log and add handlers
    root = logging.getLogger()
    root.setLevel(LOG_LEVEL)
    # root.addHandler(file)
    return log

    logging.basicConfig(
        level=LOG_LEVEL,
        format="{asctime} [{levelname}] {name}: {message}",
        datefmt="%Y-%m-%d %H:%M:%S",
        style="{",
    )
    return logging.getLogger(__name__)


class Bot(commands.AutoShardedBot):
    """A custom implemetation of `commands.AutoShardedBot`"""

    # http_session: aiohttp.ClientSession

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.http_session: Optional[aiohttp.ClientSession] = None
        self.closing_tasks: List[asyncio.Task] = []
        self.invite_link = "https://discord.com/api/oauth2/authorize?client_id={}&permissions=379968&scope=bot"

    async def create_http_pool(self) -> None:
        aiohttp_log: verboselogs.VerboseLogger = logging.getLogger("aiotrace")

        async def on_request_end(self, session, end):
            resp = end.response
            aiohttp_log.info(
                "[%s %s] %s %s (%s)",
                str(resp.status),
                resp.reason,
                end.method.upper(),
                end.url,
                resp.content_type,
            )

        trace_config = aiohttp.TraceConfig()
        trace_config.on_request_end.append(on_request_end)

        log.info("setting up http")
        self.http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5),
            trace_configs=[trace_config],
        )
        log.debug(self.http_session)
        log.info("http set up")

    def load_extensions(self) -> None:
        """Load all enabled extensions."""
        for extension in EXTENSIONS:
            try:
                self.load_extension(extension)
            except Exception:
                log.error(f"Unable to load {extension}.")
            log.success(f"Cog loaded: {extension}.")
        log.info("Extensions loaded!")

    async def close(self) -> None:
        """Close the Discord connection and the aiohttp session"""
        # Done before super().close() to allow tasks finish before the HTTP session closes.
        await self.change_presence(
            activity=discord.Game(
                name="shutting down", status=discord.Status.do_not_disturb
            )
        )
        for ext in list(EXTENSIONS):
            with suppress(Exception):
                self.unload_extension(ext)

        for cog in list(self.cogs):
            with suppress(Exception):
                self.remove_cog(cog)

        # Wait until all tasks that have to be completed before bot is closing is done
        log.info("Waiting for tasks before closing.")

        await asyncio.gather(*self.closing_tasks)

        if self.http_session:
            await self.http_session.close()

        await self.change_presence(status=discord.Status.offline)
        await asyncio.sleep(1)
        # Now actually do full close of bot
        await super().close()

    async def on_error(self, event_method, *args, **kwargs):
        """A global error handler"""
        log.error(event_method)
        if isinstance(event_method, (commands.CheckFailure, commands.CommandNotFound)):
            return

    async def on_ready(self):
        log.info("Ready! %s", self.user)


if __name__ == "__main__":
    log = setup_logger()
    intents = discord.Intents.all()
    allowed_mentions = discord.AllowedMentions(
        everyone=False,
        users=True,
        roles=False,
        replied_user=False,
    )
    bot = Bot(
        command_prefix="=",
        description=DESCRIPTION,
        allowed_mentions=allowed_mentions,
        intents=intents,
    )
    loop = asyncio.get_event_loop()
    loop.run_until_complete(bot.create_http_pool())
    bot.load_extensions()
    loop.run_until_complete(bot.login(TOKEN))
    try:
        loop.run_until_complete(bot.connect())
    except KeyboardInterrupt:
        loop.run_until_complete(bot.close())
        # cancel all tasks lingering
    finally:
        loop.close()
    # restart whenever we exit mwahahahah
    # os.execl(sys.executable, sys.executable, *sys.argv)
