import asyncio
import base64
import io
import logging
import re
from base64 import b64encode
from discord.ext.commands import MissingRequiredArgument
from datetime import datetime, timedelta

import discord
import verboselogs
from bot import Bot
from config import (CLOUDAHK_PASS, CLOUDAHK_PASS_BETA, CLOUDAHK_PASS_DEV,
                    CLOUDAHK_URL, CLOUDAHK_URL_BETA, CLOUDAHK_URL_DEV,
                    CLOUDAHK_USER, CLOUDAHK_USER_BETA, CLOUDAHK_USER_DEV,
                    SNEKBOX_PASS_DEV, SNEKBOX_URL_DEV, SNEKBOX_USER_DEV)
from discord.ext import commands

log: verboselogs.VerboseLogger = logging.getLogger(__name__)

AHK_COLOR = 0x95CD95
RSS_URL = 'https://www.autohotkey.com/boards/feed'

DOCS_FORMAT = 'https://autohotkey.com/docs/{}'

class RunnableCodeConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, code = None):
        if code is None:
            if ctx.message.reference:
                try:
                    code: str = ctx.message.reference.resolved.content
                    code = code[code.find(r"`") or 0:]
                except:
                    raise MissingRequiredArgument('code')
            else:
                raise MissingRequiredArgument('code')
        elif code.startswith('https://p.ahkscript.org/'):
            url = code.replace('?p=', '?r=')
            async with self.bot.http_session.get(url) as resp:
                if resp.status == 200 and str(resp.url) == url:
                    code = await resp.text()
                else:
                    raise commands.CommandError('Failed fetching code from pastebin.')

        return code

class CloudAHK(commands.Cog):
    '''Commands for the AutoHotkey guild.'''

    def __init__(self, bot: Bot):
        self.bot = bot

    def parse_date(self, date_str):
        date_str = date_str.strip()
        return datetime.strptime(date_str[:-3] + date_str[-2:], "%Y-%m-%dT%H:%M:%S%z")


    async def cloudahk_call(self, ctx: commands.Context, code, lang='ahk', version='stable', img : bool =False):
        '''Call to CloudAHK to run %code% written in %lang%. Replies to invoking user with stdout/runtime of code. '''

        log.debug(f'Running cloudahk: {version} version')

        if version == 'dev':
            url, user, passwd = CLOUDAHK_URL_DEV, CLOUDAHK_USER_DEV, CLOUDAHK_PASS_DEV
        elif version == 'beta':
            url, user, passwd = (
                CLOUDAHK_URL_BETA, CLOUDAHK_USER_BETA, CLOUDAHK_PASS_BETA)
        elif version == 'snekbox':
            url, user, passwd = (
                SNEKBOX_URL_DEV, SNEKBOX_USER_DEV, SNEKBOX_PASS_DEV)
        else:
            url, user, passwd = (CLOUDAHK_URL, CLOUDAHK_USER, CLOUDAHK_PASS)

        token = '{0}:{1}'.format(user, passwd)

        encoded = b64encode(bytes(token, 'utf-8')).decode('utf-8')
        headers = {'Authorization': 'Basic ' + encoded}

        # remove first line with backticks and highlighting lang
        if re.match('^```.*\n', code):
            code = code[code.find('\n') + 1:]

        # strip backticks on both sides
        code = code.strip('`').strip()

        # call cloudahk with 20 in timeout
        if version != 'snekbox':
            async with self.bot.http_session.post('{0}/{1}{2}'.format(url, lang, '/run' if version != 'snekbox' else ''), data=code, headers=headers, timeout=20) as resp:
                if resp.status == 200:
                    result = await resp.json()
                else:
                    raise commands.CommandError(f'{resp.status}. Something went wrong.')
        else:
            payload = {'input': code}
            async with self.bot.http_session.post(f'{url}/eval', json=payload, headers=headers, timeout=20) as resp:
                if resp.status == 200:
                    result = await resp.json()
                else:
                    raise commands.CommandError('Something went wrong.')

        stdout = result['stdout'].strip()

        try:
            time = result['time']
        except KeyError:
            time = result['returncode']

        try:
            language = result['language']
        except KeyError:
            language = lang

        file = None
        encoded_stdout = stdout.encode('utf-8') 

        if len(stdout) < (1800 - stdout.count('```')*4/3) and stdout.count('\n') < 20 and stdout.count('\r') < 20:
            # upload as plaintext
            stdout = stdout.replace('```', '`\u200b``')
            valid_response = ' `No Output.`\n' if stdout == '' else '\n```{1}\n{0}\n```'.format(
                stdout, language)

        elif len(encoded_stdout) < (800000):  # limited to 8mb
            
            if img: #png
                file_name = 'img.png'
                fp = io.BytesIO(base64.b64decode(stdout.encode('ascii')))
                file2 = discord.File(fp, file_name)
            fp = io.BytesIO(encoded_stdout)
            file_name = 'results.txt'
            file1 = discord.File(fp, file_name)
            valid_response = ' Results too large. See attached file(s).\n'

        else:
            raise commands.CommandError('Output greater than 8mb.')

        out = '{}{}{}{}\n{}'.format(
            ctx.author.mention,
            f'\nLanguage: `{language}`',
            valid_response,
            '`Processing time: {}`'.format(
                'Timed out' if time is None else '{0:.1f} seconds'.format(time)),
            f'*CloudAHK Backend Variant: `{version}`*'
        )

        try:
            try:
                await ctx.send(content=out, files=[file2,file1], reference=ctx.message)
            except UnboundLocalError:
                    try:
                        await ctx.send(content=out, files=[file1], reference=ctx.message)
                    except UnboundLocalError:
                        await ctx.send(content=out, reference=ctx.message)
        except discord.HTTPException:
            await ctx.send(content=out, file=file)

        return stdout, time

    @commands.group(name='ahk', invoke_without_command=True)
    @commands.cooldown(rate=5.0, per=25.0, type=commands.BucketType.user)
    async def ahk(self, ctx, *, code: RunnableCodeConverter = None):
        '''Run AHK code through CloudAHK. Example: `ahk print("hello world!")`'''

        stdout, time = await self.cloudahk_call(ctx, code, version='stable')

        # # logging for security purposes and checking for abuse
        # with open('ahk_eval/{0}_{1}_{2}'.format(ctx.guild.id, ctx.author.id, ctx.message.id), 'w', encoding='utf-8-sig') as f:
        #     f.write('{0}\n\nCODE:\n{1}\n\nPROCESSING TIME: {2}\n\nSTDOUT:\n{3}\n'.format(
        #         ctx.stamp, code, time, stdout))

    @commands.command(name='dev2')
    @commands.is_owner()
    @commands.cooldown(rate=5.0, per=25.0, type=commands.BucketType.user)
    async def ahk2(self, ctx, *, code: RunnableCodeConverter):
        '''Run AHK code through CloudAHK. Example: `ahk print("hello world!")`'''

        stdout, time = await self.cloudahk_call(ctx, code, lang='ahk2', version='dev')

        # logging for security purposes and checking for abuse
        # with open('ahk_eval/{0}_{1}_{2}'.format(ctx.guild.id, ctx.author.id, ctx.message.id), 'w', encoding='utf-8-sig') as f:
        #     f.write('{0}\n\nCODE:\n{1}\n\nPROCESSING TIME: {2}\n\nSTDOUT:\n{3}\n'.format(
        #         ctx.stamp, code, time, stdout))

    @ahk.command()
    @commands.is_owner()
    @commands.cooldown(rate=5.0, per=25.0, type=commands.BucketType.user)
    async def num(self, ctx, num: int = 1, *, code: RunnableCodeConverter):
        '''Run AHK code through CloudAHK Stable multiple times for stress testing. Example: `ahk print("hello world!")`'''
        if num > 10:
            raise Exception
        for i in range(num):
            asyncio.create_task(ctx.invoke(
                self.bot.get_command('ahk'), code=code))
        return

    @commands.group(name='beta', invoke_without_command=True)
    @commands.cooldown(rate=5.0, per=25.0, type=commands.BucketType.user)
    async def cloud_beta(self, ctx, *, code: RunnableCodeConverter):
        '''Run AHK code through CloudAHK. Example: `ahk print("hello world!")`'''

        stdout, time = await self.cloudahk_call(ctx, code, version='beta')


    @cloud_beta.command(name='img')
    async def cloud_beta_img(self, ctx, *, code: RunnableCodeConverter):

        stdout, time = await self.cloudahk_call(ctx, code, version='beta', img=True)


    @commands.group(name='snek', invoke_without_command=True)
    @commands.cooldown(rate=5.0, per=25.0, type=commands.BucketType.user)
    async def cloud_snek(self, ctx, *, code: RunnableCodeConverter):
        '''Run AHK code through snek. Example: `python print("hello world!")`'''

        stdout, time = await self.cloudahk_call(ctx, code, version='snekbox', lang='eval')

    @commands.group(name='dev', invoke_without_command=True)
    @commands.is_owner()
    @commands.cooldown(rate=5.0, per=25.0, type=commands.BucketType.user)
    async def cloud_dev(self, ctx, *, code: RunnableCodeConverter):
        '''Run AHK code through CloudAHK. Example: `ahk print("hello world!")`'''

        stdout, time = await self.cloudahk_call(ctx, code, version='dev')

        # logging for security purposes and checking for abuse
        # with open('ahk_dev_eval/{0}_{1}_{2}'.format(ctx.guild.id, ctx.author.id, ctx.message.id), 'w', encoding='utf-8-sig') as f:
        #     f.write('{0}\n\nCODE:\n{1}\n\nPROCESSING TIME: {2}\n\nSTDOUT:\n{3}\n'.format(
        #         ctx.stamp, code, time, stdout))

    @cloud_dev.command()
    @commands.is_owner()
    @commands.cooldown(rate=5.0, per=25.0, type=commands.BucketType.user)
    async def num(self, ctx, num: int = 1, *, code: RunnableCodeConverter):
        '''Run AHK code through CloudAHK Dev multiple times for stress testing. Example: `ahk print("hello world!")`'''
        if num > 10:
            raise Exception
        for i in range(num):
            asyncio.create_task(ctx.invoke(
                self.bot.get_command('dev'), code=code))
        return

    @cloud_dev.command()
    @commands.is_owner()
    @commands.cooldown(rate=5.0, per=25.0, type=commands.BucketType.user)
    async def all(self, ctx, num: int = 1, *, code: RunnableCodeConverter):
        '''Run AHK code through CloudAHK Dev multiple times for stress testing. Example: `ahk print("hello world!")`'''
        if num > 5:
            raise Exception
        for i in range(num):
            asyncio.create_task(ctx.invoke(
                self.bot.get_command('ahk'), code=code))
            asyncio.create_task(ctx.invoke(
                self.bot.get_command('beta'), code=code))
            asyncio.create_task(ctx.invoke(
                self.bot.get_command('dev'), code=code))

        return

    @commands.command(hidden=True)
    @commands.cooldown(rate=1.0, per=5.0, type=commands.BucketType.user)
    async def rlx(self, ctx, *, code: RunnableCodeConverter):
        '''Compile and run Relax code through CloudAHK. Example: `rlx define i32 Main() {return 20}`'''

        await self.cloudahk_call(ctx, code, lang='rlx', version='beta')


def setup(bot: Bot):
    bot.add_cog(CloudAHK(bot))
