import asyncio
import discord
import youtube_dl
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

    # Join Command
    @commands.command()
    async def join(self, ctx, *, channel: discord.VoiceChannel):
        """Joins a voice channel"""

        if ctx.voice_client is not None:
            return await ctx.voice_client.move_to(channel)

        await channel.connect()

    @join.error
    async def join_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send('Need to specify channel to join')

    # Play Command
    @commands.command()
    async def play(self, ctx, *, url):
        """Streams from a url"""

        print(url)
        print(type(url))
        #global search_list
        #if length of url == 1 && search_list is not empty:
        #   url = search_list[int(url)]
        async with ctx.typing():
            player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
            ctx.voice_client.play(player, after=lambda e: print('Player error: %s' % e) if e else None)

        await ctx.send('Now playing: {}'.format(player.title))

    @play.error
    async def play_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send('Missing Youtube URL')

    #IMPLEMENTATION 1
    #def play_next(ctx, source):
    #    vc = get(self.bot.voice_clients, guild=ctx.guild)
    #    if len(self.song_list) >= 1:
    #        del self.song_list[0]
    #        vc.play(discord.FFmpegPCMAudio(source=source, after=lambda e: play_next(ctx))
    #    else:
    #        asyncio.sleep(90) #wait 1 minute and 30 seconds
    #        if not vc.is_playing():
    #            asyncio.run_coroutine_threadsafe(vc.disconnect(ctx), self.bot.loop)
    #            asyncio.run_coroutine_threadsafe(ctx.send("No more songs in queue."))


    #IMPLEMENTATION 2 (APPARENTLY WORKS BETTER)
    # async def audio_player_task():
    #     while True: 
    #         play_next_song.clear()
    #         current = await songs.get()
    #         current.start()
    #         await play_next_song.wait()
    
    # def toggle_next():
    #     bot.loop.call_soon_threadsafe(play_next_song.set)
    
    
    # @client.command(pass_context=True)
    # async def play(ctx, url):

    ## MOST LIKELY REDUNDANT SECTION
    #     if not client.is_voice_connected(ctx.message.server):
    #         voice = await client.join_voice_channel(ctx.message.author.voice_channel)
    #     else:
    #         voice = client.voice_client_in(ctx.message.server)
    ## -- END OF SECTION --

    #     player = await voice.create_ytdl_player(url, after=toggle_next)
    #     await songs.put(player)

    #Volume Change
    @commands.command()
    async def volume(self, ctx, volume: int):
        """Changes the player's volume"""

        if ctx.voice_client is None:
            return await ctx.send("Not connected to a voice channel.")

        ctx.voice_client.source.volume = volume / 100
        await ctx.send("Changed volume to {}%".format(volume))
        
    @volume.error
    async def volume_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send('Missing volume to change to')

    # stop Command
    @commands.command()
    async def stop(self, ctx):
        """Stops and disconnects the bot from voice"""
        await ctx.voice_client.disconnect()

    ### Added ### 
    @commands.command()
    async def pause(self, ctx):
        """Pauses the player"""

        if ctx.voice_client is None:
            return await ctx.send("Not connected to a voice channel.")

        if ctx.voice_client.is_playing() is True:
            ctx.voice_client.pause()
            await ctx.send('Audio Paused!')
        else:
            await ctx.send('No audio is playing.')

    # Resume Command
    @commands.command()
    async def resume(self, ctx):
        """Resumes the player"""

        if ctx.voice_client is None:
            return await ctx.send("Not connected to a voice channel.")

        if ctx.voice_client.is_paused() is True:
            ctx.voice_client.resume()
            await ctx.send('Resuming Player!')
        else:
            await ctx.send('Audio is already playing!')
# NEW STUFF
    # Search Command
    # TODO: Incorporate this into Play Command s.t. non url arg calls this
    @commands.command() 
    async def search(self, ctx, *, search):
        global search_list
        query = SearchVideos(search, offset = 1, mode = "dict", max_results = 5)
        query_string = "```Choose a video:"
        for i in query.result()['search_result']:
           query_string += "\n[" 
           query_string += str(i['index'] + 1)
           query_string += "] - " 
           query_string += i['title']
           search_list.append(i['link'])
           print(i['link'])
           print(type(i['link']))

        await ctx.send(query_string + "```")

    @commands.command()
    async def choose(self, ctx, *, choice):
        #global search_list
        print(int(choice))
        print(search_list[int(choice)])
        async with ctx.typing():
            player = await YTDLSource.from_url(search_list[int(choice)], loop=self.bot.loop, stream=True)
            ctx.voice_client.play(player, after=lambda e: print('Player error: %s' % e) if e else None)

        await ctx.send('Now playing: {}'.format(player.title))

    @commands.command()
    async def test(self, ctx, *, url):
        global search_list
        print(search_list)
        print(type(url) == type(search_list[0]))

    @play.before_invoke
    async def ensure_voice(self, ctx):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()

bot = commands.Bot(command_prefix=commands.when_mentioned_or("!"),
                   description='Relatively simple music bot example')

## FROM IMPLEMENTATION 2
# bot.loop.create_task(audio_player_task())

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send('Unknown Command')

@bot.event
async def on_ready():
    print('Logged in as {0} ({0.id})'.format(bot.user))
    print('------')

bot.add_cog(Music(bot))
bot.run(TOKEN)
