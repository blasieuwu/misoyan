import asyncio
import os
import io
import re
import random  # keeps random.choice from crashing her
import threading  # handles the background web server thread
import aiohttp # for webhook avatar
from http.server import SimpleHTTPRequestHandler, HTTPServer  # basic server classes
import discord
from discord import app_commands, ui
from discord.ext import commands, tasks
import yt_dlp  # 🛠️ no more lavalink nodes!
from mutagen.mp3 import MP3 # for the file cover art embedding
from mutagen.id3 import ID3

# make bot can read the word "misoyan"
intents = discord.Intents.default()
intents.message_content = True 
intents.voice_states = True     # spy on vc

# blasie's id
creator_id = int(os.environ.get("CREATOR_ID", 0))

# compiler needs this
bot = commands.Bot(
    command_prefix="!", 
    intents=intents,
    heartbeat_timeout=60.0,    # gives her a full minute to recover if discord drops a gateway packet
    ws_close_timeout=10.0      # cleans up dead sockets fast so she can immediately re-handshake
)

# global settings
target_voice_channel_id = 123456789012345678  # default home channel
bot_token = os.environ.get("DISCORD_BOT_TOKEN")
render_port = os.environ.get("PORT")      # reads render's network port variable

# settings panel (pls no touch)
# oke -kam
misoyan_settings = {
    "all_features": True,           # "nah, i'm going offline for a bit"
    "vc_joining": True,             # "cant join vc im busy"
    "vc_leaving": True,             # yeah i can hold the vc for a bit
    "status_changes": True,         # maybe i wont make a note rn...
    "status_change_delay": False,   # "wait i should do this... NO WAIT THIS IS-"
    "fih_replies": False,            # fih :3 (changed to false cuz shes annoying)
    "need_reconnection": False,     # "i dont need to connect rn, im alr connected :sob:"
    "is_connecting": False,         # "yo im alr connecting"
    "blacklist": set()              # "i hate you, dont talk to me >:("
}

# asyncio lock to prevent the loop and events from connecting at the same time
vc_connection_lock = asyncio.Lock()

# custom class to manage queue state without wavelink
class MisoyanPlayer:
    def __init__(self):
        self.queue = []
        self.history = []
        self.current = None
        self.loop_mode = "off"  # "off", "current", "queue"

class Track:
    def __init__(self, title, author, length, uri, artwork=None):
        self.title = title
        self.author = author
        self.length = length  # in milliseconds
        self.uri = uri
        self.artwork = artwork

# active guild players store
guild_players = {}

def get_player(guild_id) -> MisoyanPlayer:
    if guild_id not in guild_players:
        guild_players[guild_id] = MisoyanPlayer()
    return guild_players[guild_id]

# clanker has emotions | format: (status, discord note)
status_pool = [
    (discord.Status.online, discord.CustomActivity(name="hanging out in the vc :3")),
    (discord.Status.idle, discord.CustomActivity(name="waiting for someone to join :c")),
    (discord.Status.dnd, discord.CustomActivity(name="learning new stuff...")),
    (discord.Status.invisible, discord.CustomActivity(name="lurking...")),
    (discord.Status.online, discord.CustomActivity(name="yapping in yappanese bleh")),
    (discord.Status.idle, discord.CustomActivity(name="waiting for someone to call my name :c")),
    (discord.Status.dnd, discord.CustomActivity(name="please do the fih")),
    (discord.Status.invisible, discord.CustomActivity(name="sleeping... zzz")),
    (discord.Status.dnd, discord.CustomActivity(name="planning next stream")),
    (discord.Status.idle, discord.CustomActivity(name="bored as hell")),
    (discord.Status.online, discord.CustomActivity(name="hanging out on stream")),
    (discord.Status.dnd, discord.CustomActivity(name="i'm lurking in your walls :3"))
]

# misoyan can now say more things
reply_list = [
    "fih fih fih",
    "who pinged",
    "you like fih?",
    "did someone call my name?",
    "fih :3",
    "please do the fih",
    "i loveeee fih",
    "hi, my name is misoyan and I AM A FIH",
    "hello :D",
    "the fih gods are watching us",
    "https://tenor.com/view/spinning-fish-gif-11746948154213447163",
    "https://tenor.com/view/upside-down-spinning-fish-long-sticker-gif-14191013706827067344",
    "https://tenor.com/view/pog-gif-14149886028736974766",
    "https://tenor.com/view/silly-cat-doodle-fish-nibble-cat-eating-fish-gif-15126373179558858541",
    "https://tenor.com/view/screaming-fish-fish-fish-finger-gif-9883040399517041611",
    "https://tenor.com/view/kiracord-fish-gif-22855500",
    "https://tenor.com/view/cat-cat-pufferfish-pufferfish-cat-fish-catfish-gif-9997139051265883971",
    "praise fih",
    "killer fish from san diego",
    "fih party",
    "spinning fish",
    "me and fih :3",
    "🐟", 
    "im in your walls :D"
]

os.makedirs("cache", exist_ok=True)

# ffmpeg options for smooth audio playback pipelines
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# yt-dlp extractor options profile
ytdl = yt_dlp.YoutubeDL({
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0'
})

def play_next_audio(vc, guild_id):
    """handles song transition workflows and queue loops natively without wavelink"""
    player = get_player(guild_id)
    if vc is None or not vc.is_connected():
        return

    # handle looping tracks logic context
    if player.loop_mode == "current" and player.current:
        track = player.current
    elif player.queue:
        if player.loop_mode == "queue" and player.current:
            player.queue.append(player.current)
        
        track = player.queue.pop(0)
        if player.current:
            player.history.append(player.current)
        player.current = track
    else:
        if player.current:
            player.history.append(player.current)
        player.current = None
        print("[queue] queue is now empty, going silent.")
        return

    try:
        source = discord.FFmpegPCMAudio(track.uri, **FFMPEG_OPTIONS)
        vc.play(source, after=lambda e: bot.loop.call_soon_threadsafe(play_next_audio, vc, guild_id))
        print(f"[queue] automatically transitioning to: {track.title}")
    except Exception as e:
        print(f"[!] auto-transition failed: {e}")

class FullSystemControlPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.update_panel_layout()

    def update_panel_layout(self):
        """paints the visual styles across both button rows based on your boolean settings"""
        self.children[0].label = f"all: {'on' if misoyan_settings['all_features'] else 'off'}"
        self.children[0].style = discord.ButtonStyle.blurple if misoyan_settings["all_features"] else discord.ButtonStyle.grey

        self.children[1].label = f"voicelines: {'on' if misoyan_settings['fih_replies'] else 'off'}"
        self.children[1].style = discord.ButtonStyle.blurple if misoyan_settings["fih_replies"] else discord.ButtonStyle.gray

        self.children[2].label = f"vc join: {'on' if misoyan_settings['vc_joining'] else 'off'}"
        self.children[2].style = discord.ButtonStyle.blurple if misoyan_settings["vc_joining"] else discord.ButtonStyle.grey

        self.children[3].label = f"vc leave: {'on' if misoyan_settings['vc_leaving'] else 'off'}"
        self.children[3].style = discord.ButtonStyle.blurple if misoyan_settings["vc_leaving"] else discord.ButtonStyle.grey

        self.children[4].label = f"statuses: {'on' if misoyan_settings['status_changes'] else 'off'}"
        self.children[4].style = discord.ButtonStyle.blurple if misoyan_settings["status_changes"] else discord.ButtonStyle.gray

        self.children[5].label = f"cycle rate: {'fast (1m)' if misoyan_settings['status_change_delay'] else 'normal (2.5m)'}"
        self.children[5].style = discord.ButtonStyle.blurple if misoyan_settings["status_change_delay"] else discord.ButtonStyle.grey

    def generate_dashboard_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="the command block",
            description="my internal organs :3",
            color=0xffcc80
        )
        embed.set_thumbnail(url=bot.user.display_avatar.url)
        
        embed.add_field(name="all features: ", value=f"state: `{'on' if misoyan_settings['all_features'] else 'off'}`", inline=False)
        embed.add_field(name="vc joining", value=f"state: `{'active' if misoyan_settings['vc_joining'] else 'disabled'}`", inline=True)
        embed.add_field(name="vc leaving", value=f"state: `{'active' if misoyan_settings['vc_leaving'] else 'disabled'}`", inline=True)
        embed.add_field(name="voicelines", value=f"state: `{'listening' if misoyan_settings['fih_replies'] else 'muted'}`", inline=True)
        embed.add_field(name="status changes", value=f"state: `{'cycling' if misoyan_settings['status_changes'] else 'frozen'}`", inline=True)
        embed.add_field(name="cycle frequency", value=f"state: `{'fast layout mode (1m)' if misoyan_settings['status_change_delay'] else 'normal engine rate (2.5m)'}`", inline=True)
        
        blacklist_mentions = ", ".join([f"<@{uid}>" for uid in misoyan_settings["blacklist"]]) if misoyan_settings["blacklist"] else "none"
        embed.add_field(name="blacklisted people", value=blacklist_mentions, inline=False)
        return embed

    @discord.ui.button(custom_id="m_all", row=0)
    async def m_all(self, interaction: discord.Interaction, btn: discord.ui.Button):
        misoyan_settings["all_features"] = not misoyan_settings["all_features"]
        self.update_panel_layout()
        await interaction.response.edit_message(embed=self.generate_dashboard_embed(), view=self)

    @discord.ui.button(custom_id="m_fih", row=0)
    async def m_fih(self, interaction: discord.Interaction, btn: discord.ui.Button):
        misoyan_settings["fih_replies"] = not misoyan_settings["fih_replies"]
        self.update_panel_layout()
        await interaction.response.edit_message(embed=self.generate_dashboard_embed(), view=self)

    @discord.ui.button(custom_id="m_join", row=1)
    async def m_join(self, interaction: discord.Interaction, btn: discord.ui.Button):
        misoyan_settings["vc_joining"] = not misoyan_settings["vc_joining"]
        self.update_panel_layout()
        await interaction.response.edit_message(embed=self.generate_dashboard_embed(), view=self)

    @discord.ui.button(custom_id="m_leave", row=1)
    async def m_leave(self, interaction: discord.Interaction, btn: discord.ui.Button):
        misoyan_settings["vc_leaving"] = not misoyan_settings["vc_leaving"]
        self.update_panel_layout()
        await interaction.response.edit_message(embed=self.generate_dashboard_embed(), view=self)

    @discord.ui.button(custom_id="m_status", row=2)
    async def m_status(self, interaction: discord.Interaction, btn: discord.ui.Button):
        misoyan_settings["status_changes"] = not misoyan_settings["status_changes"]
        self.update_panel_layout()
        await interaction.response.edit_message(embed=self.generate_dashboard_embed(), view=self)

    @discord.ui.button(custom_id="m_delay", row=2)
    async def m_delay(self, interaction: discord.Interaction, btn: discord.ui.Button):
        misoyan_settings["status_change_delay"] = not misoyan_settings["status_change_delay"]
        self.update_panel_layout()
        await interaction.response.edit_message(embed=self.generate_dashboard_embed(), view=self)

@tasks.loop(seconds=15)
async def native_voice_sentinel_loop():
    """automatically monitors, isolates, and heals crashes silently without spamming dead transport pipes"""
    if not misoyan_settings["all_features"] or not misoyan_settings["vc_joining"]:
        return

    if misoyan_settings["is_connecting"] or vc_connection_lock.locked():
        return

    global target_voice_channel_id
    home_channel = bot.get_channel(target_voice_channel_id)
    if not home_channel or not isinstance(home_channel, discord.VoiceChannel):
        return

    vc = home_channel.guild.voice_client
    is_disconnected = not vc or not vc.is_connected()

    if is_disconnected or misoyan_settings["need_reconnection"]:
        async with vc_connection_lock:
            print("wait im reconnecting pls wait for me")
            misoyan_settings["is_connecting"] = True
            
            try:
                if home_channel.guild.voice_client:
                    try:
                        await home_channel.guild.voice_client.disconnect(force=True)
                        await asyncio.sleep(1.5)
                    except Exception:
                        pass

                await home_channel.connect()
                print("im back :3")
                misoyan_settings["need_reconnection"] = False
                
            except Exception as e:
                print(f"so uhh, my wifi broke: {e}")
                if "closing transport" in str(e).lower() or "timeout" in str(e).lower():
                    misoyan_settings["need_reconnection"] = False
                await asyncio.sleep(8.0)
            finally:
                misoyan_settings["is_connecting"] = False

@tasks.loop(minutes=2.5)
async def cycle_status_loop():
    await bot.wait_until_ready()
    if not misoyan_settings["all_features"] or not misoyan_settings["status_changes"]:
        return

    current_interval = cycle_status_loop.minutes
    if misoyan_settings["status_change_delay"] and current_interval != 1.0:
        cycle_status_loop.change_interval(minutes=1.0)
    elif not misoyan_settings["status_change_delay"] and current_interval != 2.5:
        cycle_status_loop.change_interval(minutes=2.5)

    selected_status, selected_note = random.choice(status_pool)
    try:
        await bot.change_presence(status=selected_status, activity=selected_note)
    except Exception as e:
        print(f"yeah i couldnt change my discord status: {e}")

@bot.event
async def on_ready():
    print(f"ah, time to go on discord | {bot.user.name}")
    
    try:
        synced = await bot.tree.sync()
        print(f"i got {len(synced)} commands ready :o")
    except Exception as e:
        print(f"wait where did my commands go- | {e}")
        
    if not cycle_status_loop.is_running():
        cycle_status_loop.start()
        print("time to pick a status i guess.")
        
    if not native_voice_sentinel_loop.is_running():
        native_voice_sentinel_loop.start()
        print("time to set up my speakers for music")

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if member.id != bot.user.id:
        return

    if after.channel is None or after.channel.id != target_voice_channel_id:
        print("wait im not in my vc anymore give me a sec")
        
        if misoyan_settings["all_features"] and misoyan_settings["vc_joining"]:
            if not misoyan_settings["is_connecting"] and not vc_connection_lock.locked():
                misoyan_settings["need_reconnection"] = True

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if not misoyan_settings["all_features"] or message.author.id in misoyan_settings["blacklist"]:
        return
        
    if not misoyan_settings["fih_replies"]:
        return

    if "misoyan" in message.content.lower() or bot.user.mentioned_in(message):
        try:
            selected_reply = random.choice(reply_list)
            await message.reply(selected_reply, allowed_mentions=discord.AllowedMentions.none())
        except Exception as e:
            print(f"my chat broke: {e}")

# slash commands
@bot.tree.command(name="ping", description="check misoyan's reflexes")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"i'm not playing ping pong. (`{latency}ms`)")

@bot.tree.command(name="join", description="i wanna join the vc :3")
async def join(interaction: discord.Interaction):
    if not misoyan_settings["all_features"] or not misoyan_settings["vc_joining"]:
        await interaction.response.send_message("nah, too busy rn (disabled)", ephemeral=True)
        return

    global target_voice_channel_id
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("get in a voice channel you dummy!", ephemeral=True)
        return
    
    user_channel = interaction.user.voice.channel
    await interaction.response.defer() 
    target_voice_channel_id = user_channel.id
    
    if vc_connection_lock.locked():
        await interaction.followup.send("wait, i'm already trying to adjust my voice cords... hold on!", ephemeral=True)
        return

    async with vc_connection_lock:
        try:
            misoyan_settings["is_connecting"] = True
            print(f"connecting to vc: {user_channel.name}")
            await user_channel.connect()
            misoyan_settings["need_reconnection"] = False
            await interaction.followup.send("im in your vc now :D")
        except Exception as e:
            print(f"shit i failed to join: {e}")
            await interaction.followup.send(f"so i may have failed to connect...: {e}", ephemeral=True)
        finally:
            misoyan_settings["is_connecting"] = False

@bot.tree.command(name="leave", description="pls let me go :c")
async def leave(interaction: discord.Interaction):
    if not misoyan_settings["all_features"] or not misoyan_settings["vc_leaving"]:
        await interaction.response.send_message("you are not making me leave lmaooo (disabled)", ephemeral=True)
        return
    
    vc = interaction.guild.voice_client
    if vc and vc.is_connected():
        async with vc_connection_lock:
            misoyan_settings["need_reconnection"] = False
            await vc.disconnect()
            await interaction.response.send_message("i am free!! (yay :3)", ephemeral=True)
    else:
        await interaction.response.send_message("you want me to leave...? im not connected to a vc", ephemeral=True)

class NowPlayingView(ui.LayoutView):
    def __init__(self, track, user, extra: str = "", override_cover: str = None):
        super().__init__()

        user_handle = f"@{user.name}"

        if override_cover:
            track_cover_url = override_cover
        elif hasattr(track, 'artwork') and track.artwork:
            track_cover_url = track.artwork
        else:
            track_cover_url = "./whoops-it-failed.png"

        if track.length:
            minutes = int((track.length // 1000) // 60)
            seconds = int((track.length // 1000) % 60)
            duration = f"{minutes}:{seconds:02d}"
        else:
            duration = "--:--"

        track_title = track.title
        if (not track_title or track_title == "Unknown Title") and track.uri and "discordapp.com" in track.uri:
            track_title = track.uri.split("/")[-1].split("?")[0]

        artist_name = track.author if (track.author and track.author != "Unknown Artist") else "local asset"

        display_prefix = " (file)" if (track.uri and "discordapp.com" in track.uri) else extra
        now_playing = ui.TextDisplay(f"-# now playing!{display_prefix} - requested by {user_handle} :3")
        cover_art = ui.MediaGallery(discord.MediaGalleryItem(track_cover_url))
        track_metadata = ui.TextDisplay(f"## {track_title}\nArtist: **{artist_name}**\nDuration: {duration}")

        container = ui.Container(
            now_playing,
            cover_art,
            track_metadata,
            accent_color=discord.Color.from_str("#e6ba81")
        )
        self.add_item(container)

class FilePlayingView(ui.LayoutView):
    def __init__(self, track, user: discord.User, attachment: discord.Attachment, guild: discord.Guild = None, has_cover: bool = False):
        super().__init__()

        user_handle = f"@{user.name}"

        if track.length and track.length > 0:
            minutes = int((track.length // 1000) // 60)
            seconds = int((track.length // 1000) % 60)
            duration_text = f"{minutes}:{seconds:02d}"
        else:
            duration_text = "00:00"

        top_text = f"-# now playing! (file) - requested by {user_handle} :3\n## {attachment.filename}\nduration: {duration_text}"
        
        if has_cover:
            render_url = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
            guild_id = guild.id if guild else (attachment.guild.id if hasattr(attachment, "guild") else "default")
            display_thumbnail = f"{render_url}/cache/{guild_id}_cover.png" if render_url else user.display_avatar.url
        elif hasattr(track, 'artwork') and track.artwork:
            display_thumbnail = track.artwork
        else:
            display_thumbnail = user.display_avatar.url

        top_section = ui.Section(
            ui.TextDisplay(top_text),
            accessory=ui.Thumbnail(display_thumbnail)
        )

        has_title = track.title and not track.title.startswith("http") and track.title != attachment.filename
        has_author = track.author and track.author != "Unknown Artist" and track.author != ""

        layout_components = [top_section]

        if has_title or has_author:
            meta_title = track.title if has_title else "unknown title"
            meta_artist = track.author if has_author else "unknown artist"
            bottom_text = f"## {meta_title}\nartist: **{meta_artist}**"
            
            layout_components.append(ui.Separator()) 
            layout_components.append(ui.TextDisplay(bottom_text))

        container = ui.Container(
            *layout_components,
            accent_color=discord.Color.from_str("#F9C788")
        )
        self.add_item(container)

class QueuePopup(ui.LayoutView):
    def __init__(self, track, user, queue_message, position: int = None):
        super().__init__()

        user_handle = f"@{user.name}"

        if hasattr(track, 'artwork') and track.artwork:
            track_cover_url = track.artwork
        else:
            track_cover_url = "./whoops-it-failed.png"

        if track.length:
            minutes = int((track.length // 1000) // 60)
            seconds = int((track.length // 1000) % 60)
            duration = f"{minutes}:{seconds:02d}"
        else:
            duration = "--:--"

        index = ""
        if position:
            index = f"Position: #{position}"
        artist_name = track.author or "unknown"
        text_metadata = f"-# requested by {user_handle} :3\n{queue_message}\n# {track.title}\nArtist: **{artist_name}**\nDuration: {duration}\n{index}"

        section = ui.Section(ui.TextDisplay(text_metadata), accessory=ui.Thumbnail(track_cover_url))
        container = ui.Container(section, accent_color=discord.Color.from_str('#5C9F05'))

        self.add_item(container)

@bot.tree.command(name="play", description="use my speakers :3")
@app_commands.describe(
    search="the title or link of the track",
    timing="how to prioritize this track in the queue layout"
)
@app_commands.choices(timing=[
    app_commands.Choice(name="add to queue (default)", value="queue"),
    app_commands.Choice(name="play next", value="next"),
    app_commands.Choice(name="replace current track", value="replace")
])
async def play(interaction: discord.Interaction, search: str, timing: str = "queue"):
    if not misoyan_settings["all_features"]:
        await interaction.response.send_message("my speakers are off rn (disabled)", ephemeral=True)
        return

    if interaction.user.id in misoyan_settings["blacklist"]:
        await interaction.response.send_message("hey, don't touch that.", ephemeral=True)
        return

    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("join a voice channel first, you dummy! i need an audience. :c", ephemeral=True)
        return

    user_channel = interaction.user.voice.channel
    await interaction.response.defer()

    try:
        vc = interaction.guild.voice_client
        if not vc or not vc.is_connected():
            async with vc_connection_lock:
                misoyan_settings["is_connecting"] = True
                print(f"[/play] connecting to vc: {user_channel.name}")
                vc = await user_channel.connect()
                global target_voice_channel_id
                target_voice_channel_id = user_channel.id
                misoyan_settings["need_reconnection"] = False
                await asyncio.sleep(1.5)

        player = get_player(interaction.guild.id)
        
        print(f"wait, im searching for '{search}' rn gimme a sec")
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search, download=False))
        
        if 'entries' in data:
            data = data['entries'][0]

        track_url = data['url']
        track_title = data.get('title', 'Unknown Title')
        track_author = data.get('uploader', 'Unknown Artist')
        track_len = int(data.get('duration', 0) * 1000)
        track_art = data.get('thumbnail', None)

        track = Track(track_title, track_author, track_len, track_url, track_art)
        
        if not vc.is_playing() and not vc.is_paused():
            player.current = track
            source = discord.FFmpegPCMAudio(track.url, **FFMPEG_OPTIONS)
            vc.play(source, after=lambda e: bot.loop.call_soon_threadsafe(play_next_audio, vc, interaction.guild.id))
            
            embed = NowPlayingView(track, interaction.user) 
            await interaction.followup.send(view=embed)
            return

        if timing == "replace":
            player.queue.insert(0, track)
            vc.stop()
            embed = NowPlayingView(track, interaction.user, " (replaced)")
            await interaction.followup.send(view=embed)

        elif timing == "next":
            player.queue.insert(0, track)
            embed = QueuePopup(track, interaction.user, "playing next!")
            await interaction.followup.send(view=embed)

        else:
            player.queue.append(track)
            embed = QueuePopup(track, interaction.user, "added to queue!", len(player.queue))
            await interaction.followup.send(view=embed)

    except Exception as e:
        print(f"[!] my speakers nooo- | {e}")
        await interaction.followup.send(f"so my speakers... uhh: `{e}`", ephemeral=True)
    finally:
        misoyan_settings["is_connecting"] = False

@bot.tree.command(name="playback", description="pause or unpause the current music playback")
async def playback(interaction: discord.Interaction):
    if not misoyan_settings["all_features"]:
        await interaction.response.send_message("my speakers are off rn (disabled)", ephemeral=True)
        return

    if interaction.user.id in misoyan_settings["blacklist"]:
        await interaction.response.send_message("hey, don't touch that.", ephemeral=True)
        return

    vc = interaction.guild.voice_client
    if not vc or not vc.is_connected():
        await interaction.response.send_message("i'm not even in a vc right now?", ephemeral=True)
        return

    if vc.is_playing():
        vc.pause()
        await interaction.response.send_message("oh, ok i'll hold the music.")
    elif vc.is_paused():
        vc.resume()
        await interaction.response.send_message("alr lemme continue playing it")
    else:
        await interaction.response.send_message("so what, you want me to freeze time?", ephemeral=True)

@bot.tree.command(name="skip", description="skip this track if it's bad bleh")
async def skip(interaction: discord.Interaction):
    if not misoyan_settings["all_features"]:
        await interaction.response.send_message("my speakers are off rn (disabled)", ephemeral=True)
        return

    if interaction.user.id in misoyan_settings["blacklist"]:
        await interaction.response.send_message("hey, don't touch that.", ephemeral=True)
        return

    vc = interaction.guild.voice_client
    if not vc or not vc.is_connected():
        await interaction.response.send_message("i'm not even in a vc to skip anything?", ephemeral=True)
        return

    if not vc.is_playing() and not vc.is_paused():
        await interaction.response.send_message("there's nothing playing right now anyway!", ephemeral=True)
        return

    vc.stop()
    await interaction.response.send_message("track skipped! next track coming up...")

@bot.tree.command(name="previous", description="play the previous song if you like it :3")
async def previous_track(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc or not vc.is_connected():
        await interaction.response.send_message("i'm not in a vc!", ephemeral=True)
        return

    player = get_player(interaction.guild.id)
    if not player.history:
        await interaction.response.send_message("hmph, you think i can play nothing?", ephemeral=True)
        return

    real_previous = player.history.pop()
    if player.current:
        player.queue.insert(0, player.current)
        
    player.current = real_previous
    vc.stop()
    
    source = discord.FFmpegPCMAudio(real_previous.uri, **FFMPEG_OPTIONS)
    vc.play(source, after=lambda e: bot.loop.call_soon_threadsafe(play_next_audio, vc, interaction.guild.id))
    await interaction.response.send_message(f"rewinding back to: **{real_previous.title}**")

@bot.tree.command(name="replay", description="restart the current song from the beginning")
async def replay_track(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    player = get_player(interaction.guild.id)
    
    if not vc or not vc.is_connected() or not player.current:
        await interaction.response.send_message("tsk, seriously?")
        return

    track = player.current
    vc.stop()
    
    source = discord.FFmpegPCMAudio(track.uri, **FFMPEG_OPTIONS)
    vc.play(source, after=lambda e: bot.loop.call_soon_threadsafe(play_next_audio, vc, interaction.guild.id))
    await interaction.response.send_message(f"replaying **{track.title}**")

class SongQueue(ui.LayoutView):
    def __init__(self, player, user):
        super().__init__()

        queue_sections = []

        if player.current:
            current_track = player.current
            current_cover = current_track.artwork if current_track.artwork else "./whoops-it-failed.png"

            if current_track.length:
                curr_min = int((current_track.length // 1000) // 60)
                curr_sec = int((current_track.length // 1000) % 60)
                curr_duration = f"{curr_min}:{curr_sec:02d}"
            else:
                curr_duration = "97:663? (unknown)"

            current_text = f"## {current_track.title}\nArtist: **{current_track.author or 'unknown'}**\nDuration: {curr_duration}\nPosition: playing!"
            
            queue_sections.append(
                ui.Section(ui.TextDisplay(current_text), accessory=ui.Thumbnail(current_cover))
            )

        for i, track in enumerate(player.queue):
            if i >= 4:
                break
                
            position_text = "up next!" if i == 0 else f"#{i + 1}"
            track_cover = track.artwork if track.artwork else "https://placehold.co/240x240/eaeaea/969696.png?text=240+x+240"

            if track.length:
                t_min = int((track.length // 1000) // 60)
                t_sec = int((track.length // 1000) % 60)
                track_duration = f"{t_min}:{t_sec:02d}"
            else:
                track_duration = "97:663? (unknown)"

            track_text = f"## {track.title}\nArtist: **{track.author or 'unknown'}**\nDuration: {track_duration}\nPosition: {position_text}"
            
            queue_sections.append(
                ui.Section(ui.TextDisplay(track_text), accessory=ui.Thumbnail(track_cover))
            )

        container = ui.Container(*queue_sections, accent_color=discord.Color.from_str("#2C2C2C"))
        self.add_item(container)

@bot.tree.command(name="queue", description="see what songs are lined up next")
async def view_queue(interaction: discord.Interaction):
    player = get_player(interaction.guild.id)

    if not player.current and len(player.queue) == 0:
        await interaction.response.send_message("the queue is completely empty!", ephemeral=True)
        return

    view_embed = SongQueue(player, interaction.user)
    await interaction.response.send_message(view=view_embed)

@bot.tree.command(name="play-file", description="give me your audio file :)")
@app_commands.describe(
    attachment="drag and drop or select an audio file (.mp3, .wav, .ogg, etc.) from your device",
    timing="how to prioritize this track in the queue layout"
)
@app_commands.choices(timing=[
    app_commands.Choice(name="add to queue (default)", value="queue"),
    app_commands.Choice(name="play next", value="next"),
    app_commands.Choice(name="replace current track", value="replace")
])
async def play_file(interaction: discord.Interaction, attachment: discord.Attachment, timing: str = "queue"):
    if not misoyan_settings["all_features"]:
        await interaction.response.send_message("my speakers are off, mb (disabled)", ephemeral=True)
        return

    if interaction.user.id in misoyan_settings["blacklist"]:
        await interaction.response.send_message("no, i'm not playing that for you.", ephemeral=True)
        return

    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("join a voice channel first, you dummy! i need an audience. :c", ephemeral=True)
        return

    valid_extensions = [".mp3", ".wav", ".ogg", ".flac", ".m4a"]
    if not any(attachment.filename.lower().endswith(ext) for ext in valid_extensions):
        await interaction.response.send_message("you sure this is an audio file? doesnt look like it", ephemeral=True)
        return

    user_channel = interaction.user.voice.channel
    await interaction.response.defer()

    try:
        vc = interaction.guild.voice_client
        if not vc or not vc.is_connected():
            misoyan_settings["is_connecting"] = True
            print(f"[play-file] connecting to vc: {user_channel.name}")
            vc = await user_channel.connect()
            global target_voice_channel_id
            target_voice_channel_id = user_channel.id
            misoyan_settings["need_reconnection"] = False
            await asyncio.sleep(1.5)

        player = get_player(interaction.guild.id)

        # --- metadata extraction block ---
        has_extracted_cover = False
        if attachment.filename.lower().endswith(".mp3"):
            try:
                file_bytes = await attachment.read()
                audio_stream = io.BytesIO(file_bytes)
                audio = MP3(audio_stream, ID3=ID3)
                
                for key in audio.tags.keys():
                    if key.startswith('APIC'):
                        apic_frame = audio.tags[key]
                        with open(f"cache/{interaction.guild.id}_cover.png", "wb") as f:
                            f.write(apic_frame.data)
                        has_extracted_cover = True
                        break
            except Exception as metadata_error:
                print(f"[!] couldn't rip metadata tags from track: {metadata_error}")

        track = Track(attachment.filename, "local asset", 0, attachment.url)

        if not vc.is_playing() and not vc.is_paused():
            player.current = track
            source = discord.FFmpegPCMAudio(track.uri, **FFMPEG_OPTIONS)
            vc.play(source, after=lambda e: bot.loop.call_soon_threadsafe(play_next_audio, vc, interaction.guild.id))
            
            view_embed = FilePlayingView(track, interaction.user, attachment, guild=interaction.guild, has_cover=has_extracted_cover) 
            await interaction.followup.send(view=view_embed)
            return

        if timing == "replace":
            player.queue.insert(0, track)
            vc.stop()
            view_embed = FilePlayingView(track, interaction.user, attachment, guild=interaction.guild, has_cover=has_extracted_cover)
            await interaction.followup.send(view=view_embed)

        elif timing == "next":
            player.queue.insert(0, track)
            embed = QueuePopup(track, interaction.user, "playing next (file)!")
            await interaction.followup.send(view=embed)

        else:
            player.queue.append(track)
            embed = QueuePopup(track, interaction.user, "added file to queue!", len(player.queue))
            await interaction.followup.send(view=embed)

    except Exception as e:
        print(f"[!] so my speakers broke...: {e}")
        await interaction.followup.send(f"yeah my speaker broken lmaoo: `{e}`", ephemeral=True)
    finally:
        misoyan_settings["is_connecting"] = False

@bot.tree.command(name="status", description="check out my internal self :D")
async def systemstatus(interaction: discord.Interaction):
    total_guilds = len(bot.guilds)
    latency = round(bot.latency * 1000)
    
    vc = interaction.guild.voice_client
    current_vc_connections = 1 if vc and vc.is_connected() else 0
    bot_thumbnail = bot.user.display_avatar.url
    
    embed = discord.Embed(
        title="misoyan's internal brain :3",
        description="very simple stuff",
        color=0x2b2d31
    )

    embed.set_thumbnail(url=bot_thumbnail)
    embed.add_field(name="reflex times: ", value=f"`{latency}ms`", inline=False)
    embed.add_field(name="servers i'm in: ", value=f"`{total_guilds} servers`", inline=False)
    embed.add_field(name="vcs i'm in right now: ", value=f"`{current_vc_connections} active vcs`", inline=False)
    
    embed.set_footer(text="created by blasie :3")   
    await interaction.response.send_message(embed=embed)

def parse_time(time_str: str) -> int:
    total_seconds = 0
    matches = re.findall(r'(\d+)\s*([hmsHMS])', time_str)
    
    for value, unit in matches:
        value = int(value)
        unit = unit.lower()
        if unit == 'h':
            total_seconds += value * 3600
        elif unit == 'm':
            total_seconds += value * 60
        elif unit == 's':
            total_seconds += value
            
    return total_seconds

@bot.tree.command(name="timer", description="set a timer")
@app_commands.describe(
    duration="how long for (ex: 1h 30m or 45s)",
    message="what to remind you of"
)
async def timer(interaction: discord.Interaction, duration: str, message: str = None):
    seconds = parse_time(duration)
    if seconds <= 0:
        return await interaction.response.send_message("sonion did you not read the format 😭🙏", ephemeral=True)
    if seconds > 86400:
        return await interaction.response.send_message("no im not doing this for 24+ hours", ephemeral=True)

    confirm_text = f"ok, your timer's set for **{duration}**!"
    if message:
        confirm_text += f"\n~> **note:** {message}"

    await interaction.response.send_message(confirm_text)
    await asyncio.sleep(seconds)
    
    reminder_text = f"ring ring banana phone ({interaction.user.mention})"
    if message:
        reminder_text += f"\n~> **reminder:** {message}"
        
    await interaction.followup.send(reminder_text)

@bot.tree.command(name="suicide", description="[blasie-only] completely kills misoyan.")
async def systemshutdown(interaction: discord.Interaction):
    if interaction.user.id != creator_id:
        await interaction.response.send_message("you're not blasie, get away", ephemeral=True)
        return
        
    await interaction.response.send_message("OUCH D:")
    await bot.close()

@bot.tree.command(name="say", description="[admin/owner] make misoyan speak :D")
@app_commands.describe(message="the exact text you want misoyan to broadcast")
async def systemsay(interaction: discord.Interaction, message: str):
    is_creator = interaction.user.id == creator_id
    is_server_owner = interaction.guild and interaction.user.id == interaction.guild.owner_id
    is_admin = interaction.guild and interaction.user.guild_permissions.administrator

    if not (is_creator or is_server_owner or is_admin):
        await interaction.response.send_message("you're not blasie or an admin here, get away", ephemeral=True)
        return
        
    await interaction.response.send_message("im in your walls :)", ephemeral=True)
    try:
        await interaction.channel.send(message)
    except Exception as e:
        print(f"failed to execute /say: {e}")

@bot.tree.command(name="settings", description="[admin/owner] change my internal organs :3")
async def control_panel(interaction: discord.Interaction):
    is_creator = interaction.user.id == creator_id
    is_server_owner = interaction.guild and interaction.user.id == interaction.guild.owner_id
    is_admin = interaction.guild and interaction.user.guild_permissions.administrator

    if not (is_creator or is_server_owner or is_admin):
        await interaction.response.send_message("yeah no, shoo.", ephemeral=True)
        return
        
    view = FullSystemControlPanel()
    await interaction.response.edit_message(embed=view.generate_dashboard_embed(), view=view)

@bot.tree.command(name="restrict", description="[admin/owner] don't end up in this list.")
@app_commands.describe(target="the specific person you want to modify settings for")
async def restrict_user(interaction: discord.Interaction, target: discord.User):
    is_creator = interaction.user.id == creator_id
    is_server_owner = interaction.guild and interaction.user.id == interaction.guild.owner_id
    is_admin = interaction.guild and interaction.user.guild_permissions.administrator

    if not (is_creator or is_server_owner or is_admin):
        await interaction.response.send_message("shoo, before you get blacklisted", ephemeral=True)
        return
        
    if target.id == creator_id:
        await interaction.response.send_message("hmph, very funny. can't do that tho.", ephemeral=True)
        return
        
    if target.id in misoyan_settings["blacklist"]:
        misoyan_settings["blacklist"].remove(target.id)
        await interaction.response.send_message(f"unblacklisted. **{target.name}** can now talk to misoyan again.", ephemeral=True)
    else:
        misoyan_settings["blacklist"].add(target.id)
        await interaction.response.send_message(f"blacklisted. **{target.name}** has been blocked by misoyan.", ephemeral=True)

@bot.tree.command(name="webhook", description="[blasie-only] create a new webhook :o")
@app_commands.describe(message="atleast give it a name :P")
async def create_webhook(interaction: discord.Interaction, message: str = "a webhook - misoyan"):
    if interaction.user.id != creator_id:
        await interaction.response.send_message("you're not blasie, get away", ephemeral=True)
        return
        
    if isinstance(interaction.channel, discord.TextChannel):
        try:
            webhook_avatar_url = "./whoops-it-failed.png"
            avatar_image = None
            
            async with aiohttp.ClientSession() as session:
                async with session.get(webhook_avatar_url) as response:
                    if response.status == 200:
                        avatar_image = await response.read()

            webhook = await interaction.channel.create_webhook(
                name = message,
                reason = "created by blasie using misoyan :o",
                avatar = avatar_image
            )

            await interaction.response.send_message(f"done! your webhook url is: ||{webhook.url}|| | name: {webhook.name}", ephemeral = True)

        except discord.Forbidden:
            await interaction.response.send_message("i don't have the 'manage webhooks' permission :p", ephemeral = True)
        except discord.HTTPException:
            await interaction.response.send_message("so it may have failed... ehe :)", ephemeral = True)
    else:
        await interaction.response.send_message("hmph, you can't do that (text channels only)", ephemeral = True)

@bot.tree.command(name="now-playing", description="view the current song :p")
async def now_playing(interaction: discord.Interaction):
    player = get_player(interaction.guild.id)
    
    if not player.current:
        await interaction.response.send_message("you seriously wanna see the void? nothing's playing...")
        return

    current_track = player.current
    cover_url_override = None

    local_image_file = f"cache/{interaction.guild.id}_cover.png"
    if current_track.uri and "discordapp.com/attachments/" in current_track.uri and os.path.exists(local_image_file):
        render_url = os.environ.get("RENDER_EXTERNAL_URL")
        if render_url:
            render_url = render_url.rstrip("/")
            cover_url_override = f"{render_url}/{local_image_file}"

    embed = NowPlayingView(current_track, interaction.user, override_cover=cover_url_override)
    await interaction.response.send_message(view=embed)
    
class LoopStatusView(ui.LayoutView):
    def __init__(self, mode: str, track, user: discord.User):
        super().__init__()
        
        user_handle = f"@{user.name}"
        
        if mode == "current":
            if track and hasattr(track, 'artwork') and track.artwork:
                thumbnail_url = track.artwork
            else:
                thumbnail_url = "./whoops-it-failed.png"
            
            card_text = f"-# requested by {user_handle}\n### loop: current song\nthe current song will now loop forever :3"
            accent = discord.Color.from_str("#5C9F05")
            
        elif mode == "queue":
            thumbnail_url = user.display_avatar.url
            card_text = f"-# requested by {user_handle}\n### loop: queue\nthe entire queue will now loop :o"
            accent = discord.Color.from_str("#85C2F0")
            
        else: # off
            thumbnail_url = user.display_avatar.url
            card_text = f"-# requested by {user_handle}\n### loop: off\nloop has been turned off :P"
            accent = discord.Color.from_str("#FF0000")

        container = ui.Container(
            ui.Section(ui.TextDisplay(card_text), accessory=ui.Thumbnail(thumbnail_url)),
            accent_color=accent
        )
        self.add_item(container)

@bot.tree.command(name="loop", description="change the loop mode for the player")
@app_commands.choices(mode=[
    app_commands.Choice(name="current song", value="current"),
    app_commands.Choice(name="queue", value="queue"),
    app_commands.Choice(name="off", value="off")
])
async def loop_cmd(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    player = get_player(interaction.guild.id)
    player.loop_mode = mode.value

    view_embed = LoopStatusView(mode.value, player.current, interaction.user)
    await interaction.response.send_message(view=view_embed)

def run_dummy_server(port):
    try:
        server_address = ('0.0.0.0', int(port))
        httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
        print(f"ok i managed to do it :D | port: {port}")
        httpd.serve_forever()
    except Exception as e:
        print(f"so i kinda failed to start the web server...: {e}")

if __name__ == "__main__":
    if render_port:
        threading.Thread(target=run_dummy_server, args=(render_port,), daemon=True).start()

    if bot_token:
        bot.run(bot_token)
    else:
        print("you forgot my token you dummy!")
