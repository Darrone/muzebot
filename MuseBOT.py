# TO DO: Play songs from playlist after adding them to the queue (Go to Playlist command).
#	 Incorporate the Playlist command into Play by finding a way to differentiate between regular videos and playlists.

import asyncio
import discord
import youtube_dl
import math
import random
import urllib.parse
import urllib.request
from urllib.request import urlopen
import re
from discord.ext import commands
from youtubesearchpython import SearchVideos

TOKEN = open('token.txt', 'r').read()

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

def get_duration(data):
    x = int(data) % 60
    if x < 10:
        dur = "0" + str(x)
    else:
        dur = str(int(data) % 60)
        
    return str(math.floor(int(data) / 60)) + ":" + dur

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = get_duration(data.get('duration'))

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        
        if 'entries' in data:
            # take first item from a playlist
            print(data['entries'][0])
            print(data['entries'][1])
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.song_queue = []
        self.original_list = []
        self.shuffle_flag = False
        self.now_playing = {}

    # Join Command
    @commands.command()
    async def join(self, ctx):
        """Joins a voice channel"""

        channel = ctx.author.voice.channel

        if ctx.voice_client is not None:
            return await ctx.voice_client.move_to(channel)

        await channel.connect()

    # Old Play Command
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
            return await ctx.send("**Not connected to a voice channel.**")

        ctx.voice_client.source.volume = volume / 100
        await ctx.send("**Changed volume to {}%**".format(volume))
        
    @volume.error
    async def volume_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send('**Missing volume to change to.**')


    @commands.command()
    async def stop(self, ctx):
        """Stops and disconnects the bot from voice"""
        await ctx.voice_client.disconnect()

    @commands.command()
    async def pause(self, ctx):
        """Pauses the player"""

        if ctx.voice_client is None:
            return await ctx.send("**Not connected to a voice channel.**")
        if ctx.voice_client.is_playing() is True:
            ctx.voice_client.pause()
            await ctx.send('**Audio Paused!**')
        else:
            await ctx.send('**No audio is playing.**')

# Resume: Resumes the player. 
    @commands.command()
    async def resume(self, ctx):
        """Resumes the player"""

        if ctx.voice_client is None:
            return await ctx.send("**Not connected to a voice channel.**")
        if ctx.voice_client.is_paused() is True:
            ctx.voice_client.resume()
            await ctx.send('**Resuming Player!**')
        else:
            await ctx.send('**Audio is already playing!**')

# Queue: Shows a list of songs in the queue.
    @commands.command(name="queue")
    async def display_queue(self, ctx):
        """Displays song queue"""

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

# Playing: Gives link of the current song
    @commands.command(name = "playing")
    async def display_playing(self, ctx):
        vc = ctx.voice_client
        if vc is None:
            await ctx.send("**Play a song first!**")
        elif vc.is_playing():
            message = "**Now Playing: **" + self.now_playing['link']
            await ctx.send(message)
        else:
            await ctx.send("**Nothing is playing.**")

# Shuffle: Changes the order of the song queue
    @commands.command()
    async def shuffle(self, ctx):
        """Shuffles the song queue"""
        # Has been shuffled
        if (self.shuffle_flag):
            self.song_queue = self.original_list.copy()
            self.shuffle_flag = False
            await ctx.send('**Queue Un-shuffled!**')
        # Has not been shuffled
        else:
            self.original_list = self.song_queue.copy()
            random.shuffle(self.song_queue)
            self.shuffle_flag = True
            await ctx.send('**Queue Shuffled!**')
        
# Play: Search and Play in same function
    @commands.command()
    async def play(self, ctx, *, search):
        """ !play "search" then pick number (ex: 1) or !play 'url' """

        if "youtube.com" in search:
            # Play from URL
            async with ctx.typing():
                result = ytdl.extract_info(search, download=False)
                
                duration = get_duration(result['duration'])
                search_list = [
                                {"link": search,
                                 "title": result['title'],
                                 "duration": duration
                                }]
            choice = 0
        else:
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
                await ctx.send("**No song chosen!**")
                await sent_queue.delete()
                if response:
                    await response.delete()
                return

            choice = int(response.content) - 1
            await sent_queue.delete()
            await response.delete()
            
        # Queue and playing songs
        vc = ctx.voice_client
        if not vc.is_playing():
            async with ctx.typing():
                player = await YTDLSource.from_url(search_list[choice]['link'], loop=self.bot.loop, stream=True)
                vc.play(player, after=lambda e: print('Player error: %s' % e) if e else play_next(ctx))
            await ctx.send('**Now Playing:** {} ({})'.format(player.title, player.duration))
            self.now_playing = search_list[choice].copy()
        else:
            self.song_queue.append(search_list[choice])
            # To make sure that the original list has members in it so that both queues function normally.
            self.original_list.append(search_list[choice])
            
            await ctx.send('**Song Queued:** {} ({})'.format(search_list[choice]['title'], search_list[choice]['duration']))

        def play_next(ctx):
            # Check if queue is not empty
            if len(self.song_queue) >= 1:
                # See if there is nothing in queue
                if len(self.song_queue) <= 0:
                    asyncio.run_coroutine_threadsafe(ctx.send("**No more songs in queue.**"), self.bot.loop)
                    return

                result = asyncio.run_coroutine_threadsafe(YTDLSource.from_url(self.song_queue[0]['link'], loop=self.bot.loop, stream=True), self.bot.loop)
                player = result.result()
                try:
                    vc.play(player, after=lambda e: play_next(ctx))
                    asyncio.run_coroutine_threadsafe(ctx.send('**Now Playing:** {} ({})'.format(player.title, player.duration)), self.bot.loop)
                    self.now_playing = self.song_queue[0].copy()
                    
                    #To make sure that songs that are removed from queue are also removed from original list.
                    for i in range(len(self.original_list)):
                        if self.original_list[i]['link'] == self.now_playing['link']:
                            self.original_list.pop(i)
                            break
                    
                    del self.song_queue[0]
                except:
                    print("Something Bad Happened!")
                    pass

    @play.before_invoke
    async def ensure_voice(self, ctx):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("**Connect to a voice channel first.**")
                raise commands.CommandError("`Author not connected to a voice channel.`")

#Skip: Stopping the voice_client is functionally equivalent to a skip
    @commands.command()
    async def skip(self, ctx):
        vc = ctx.voice_client
        if vc is None:
            await ctx.send("**Play a song first!**")
        elif vc.is_playing():
            vc.stop()
            await ctx.send("**Skipped Track:** {}".format(self.now_playing['title']))
        else:
            await ctx.send("**Nothing to skip.**")

#Remove: Removes a track from the queue
    @commands.command()
    async def remove(self, ctx, *, choice):
        vc = ctx.voice_client
        if vc is None:
            await ctx.send("**Play a song first!**")
        elif ((int(choice) < 1) or (int(choice) > len(self.song_queue))):
            await ctx.send("**Invalid choice!**")
        else:
            for i in range(len(self.original_list)):
                if self.original_list[i]['link'] == self.song_queue[int(choice) - 1]['link']:
                    self.original_list.pop(i)
                    break
            await ctx.send("**Removed Track: {}**".format(self.song_queue[int(choice) - 1]['title']))
            self.song_queue.pop(int(choice) - 1)

#Test: Temp function used for testing
    @commands.command()
    async def test(self, ctx):
        print(self.song_queue)

#Playlist: Test for getting playlist links

    @commands.command()
    async def playlist(self, ctx, *, url):
        page_elements = urlopen(url).readlines()
        playlist_entries = []
    
	# I know this can be a lot more efficient, but we'll figure this out later
        for i in page_elements:
            line = str(i, 'utf-8')
            if 'watch?v=' in line: 
                temp = [x[:19] for x in line.split("/") if x.find('watch?v=') != -1]
                [playlist_entries.append("https://www.youtube.com/" + y) for y in temp if ("https://www.youtube.com/" + y) not in playlist_entries]
                
                for i in playlist_entries:
                    print(i)
                    playlist_song = ytdl.extract_info(i, download=False)
                    duration = get_duration(playlist_song['duration'])
                    self.song_queue.append(
                                {"link": i,
                                 "title": playlist_song['title'],
                                 "duration": duration
                                })

	# Everything here is a temporary solution to playing videos from the playlist without calling the Play command.
	# This should be removed after we figure out how to incorporate this into the Play command. 
                if ctx.voice_client is None:
                    if ctx.author.voice:
                        await ctx.author.voice.channel.connect()
                
                vc = ctx.voice_client
                if not vc.is_playing():
                    async with ctx.typing():
                        player = await YTDLSource.from_url(self.song_queue[0]['link'], loop=self.bot.loop, stream=True)
                        vc.play(player, after=lambda e: print('Player error: %s' % e) if e else play_next(ctx))
                    await ctx.send('**Now Playing:** {} ({})'.format(player.title, player.duration))
                    self.now_playing = self.song_queue[0].copy()
                      
bot = commands.Bot(command_prefix=commands.when_mentioned_or("!"),
                   description='Hi I am MuseBOT, Use me as you please UwU')

@bot.event
async def on_ready():
    print('Logged in as {0} ({0.id})'.format(bot.user))
    print('------')

bot.add_cog(Music(bot))
bot.run(TOKEN)
