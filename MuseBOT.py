import asyncio
import discord
import youtube_dl
import math
import urllib.parse, urllib.request, re

from discord.ext import commands
from youtubesearchpython import SearchVideos

TOKEN = open('token.txt', 'r').read()

search_list = []

#song_list = asyncio.Queue()
#play_next_song = asyncio.Event()

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0' # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = self.get_duration(data)

    def get_duration(self, data):
        x = int(data.get('duration')) % 60
        if x < 10:
            dur = "0" + str(x)
        else:
            dur = str(int(data.get('duration')) % 60)
            
        return str(math.floor(int(data.get('duration')) / 60)) + ":" + dur

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.song_queue = []

    # Join Command
    @commands.command()
    async def join(self, ctx):
        """Joins a voice channel"""

        channel = ctx.author.voice.channel

        if ctx.voice_client is not None:
            return await ctx.voice_client.move_to(channel)

        await channel.connect()

    # # Play Command
    # @commands.command()
    # async def play(self, ctx, *, url):
    #     """Streams from a url"""

    #     print(url)
    #     print(type(url))
    #     #global search_list
    #     #if length of url == 1 && search_list is not empty:
    #     #   url = search_list[int(url)]
    #     async with ctx.typing():
    #         player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
    #         ctx.voice_client.play(player, after=lambda e: print('Player error: %s' % e) if e else None)

    #     await ctx.send('Now playing: {}'.format(player.title))

    @commands.command()
    async def volume(self, ctx, volume: int):
        """Changes the player's volume"""

        if ctx.voice_client is None:
            return await ctx.send("`Not connected to a voice channel.`")

        ctx.voice_client.source.volume = volume / 100
        await ctx.send("`Changed volume to {}%`".format(volume))
        
    @volume.error
    async def volume_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send('`Missing volume to change to`')

    @commands.command()
    async def stop(self, ctx):
        """Stops and disconnects the bot from voice"""
        await ctx.voice_client.disconnect()

    @commands.command()
    async def pause(self, ctx):
        """Pauses the player"""

        if ctx.voice_client is None:
            return await ctx.send("`Not connected to a voice channel.`")

        if ctx.voice_client.is_playing() is True:
            ctx.voice_client.pause()
            await ctx.send('`Audio Paused!`')
        else:
            await ctx.send('`No audio is playing.`')

    @commands.command()
    async def resume(self, ctx):
        """Resumes the player"""

        if ctx.voice_client is None:
            return await ctx.send("`Not connected to a voice channel.`")

        if ctx.voice_client.is_paused() is True:
            ctx.voice_client.resume()
            await ctx.send('`Resuming Player!`')
        else:
            await ctx.send('`Audio is already playing!`')
    
    @commands.command(name="queue")
    async def display_queue(self, ctx):
        if not self.song_queue:
            await ctx.send("```Queue is empty.```")
        else:
            query_string = "```Video Queue:"
            i = 1
            for x in self.song_queue:
                query_string += "\n[" 
                query_string += str(i)
                query_string += "] - " 
                query_string += x['title']
                query_string += " ("
                query_string += x['duration']
                query_string += ")"
                i += 1
            await ctx.send(query_string + "```")


# Search and Play in same function

    @commands.command()
    async def play(self, ctx, *, search):
        """ !play "search" then pick number (ex: 1) """
        # Search youtube
        search_list = []
        async with ctx.typing():
            query = SearchVideos(search, offset = 1, mode = "dict", max_results = 5)
            query_string = "```Choose a video:"
            for i in query.result()['search_result']:
                query_string += "\n[" 
                query_string += str(i['index'] + 1)
                query_string += "] - " 
                query_string += i['title']
                query_string += " ("
                query_string += i['duration']
                query_string += ")"
                info = {
                        "link": i['link'],
                        "title": i['title'],
                        "duration": i['duration']
                       }
                search_list.append(info)

        sent_queue = await ctx.send(query_string + "```")

        # waiting for user response
        def check(m):
            return m.author.id == ctx.author.id and int(m.content) <= 5 and int(m.content) >= 1

        try:
            response = await self.bot.wait_for('message', check=check, timeout=30)
        except asyncio.TimeoutError:
            await ctx.send("`No song chosen!`")
            await sent_queue.delete()
            if response:
                await response.delete()
            return

        choice = int(response.content) - 1
        
        # Queue and playing songs
        vc = ctx.voice_client
        self.song_queue.append(search_list[choice])
        if not vc.is_playing():
            async with ctx.typing():
                player = await YTDLSource.from_url(search_list[choice]['link'], loop=self.bot.loop, stream=True)
                vc.play(player, after=lambda e: print('Player error: %s' % e) if e else play_next(ctx))
            await ctx.send('`Now playing: {} ({})`'.format(player.title, player.duration))
        else:
            #await ctx.send('Song Queued:')
            display = query.result()['search_result']
            await ctx.send('`Song Queued: {} ({})`'.format(display[choice]['title'], display[choice]['duration']))

        await sent_queue.delete()
        await response.delete()

        def play_next(ctx):

            # Check if queue is not empty
            if len(self.song_queue) >= 1:
                del self.song_queue[0]
                # After deleting see if there is nothing in queue
                if len(self.song_queue) <= 0:
                    asyncio.run_coroutine_threadsafe(ctx.send("`No more songs in queue.`"), self.bot.loop)
                    return

                result = asyncio.run_coroutine_threadsafe(YTDLSource.from_url(self.song_queue[0]['link'], loop=self.bot.loop, stream=True), self.bot.loop)
                player = result.result()
                try:
                    vc.play(player, after=lambda e: play_next(ctx))
                    asyncio.run_coroutine_threadsafe(ctx.send('`Now playing: {} ({})`'.format(player.title, player.duration)), self.bot.loop)
                except:
                    print("Something Bad Happened!")
                    pass

    @play.before_invoke
    async def ensure_voice(self, ctx):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("`You are not connected to a voice channel.`")
                raise commands.CommandError("`Author not connected to a voice channel.`")

bot = commands.Bot(command_prefix=commands.when_mentioned_or("!"),
                   description='Hi I am MuseBOT, Use me as you please UwU')

# @bot.event
# async def on_command_error(ctx, error):
#     if isinstance(error, commands.CommandNotFound):
#         await ctx.send('Unknown Command')

@bot.event
async def on_ready():
    print('Logged in as {0} ({0.id})'.format(bot.user))
    print('------')

bot.add_cog(Music(bot))
bot.run(TOKEN)
