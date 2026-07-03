import asyncio
import os
import io
import random  # keeps random.choice from crashing her
import threading  # handles the background web server thread
import aiohttp # for webhook avatar
from http.server import SimpleHTTPRequestHandler, HTTPServer  # basic server classes
import discord
from discord import app_commands, ui
from discord.ext import commands, tasks
import wavelink  # this powers her speakers
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

# lavalink stuff
lava_host = os.getenv("LAVALINK_HOST", "lava.link")
lava_port = os.getenv("LAVALINK_PORT", "80")
lava_pass = os.getenv("LAVALINK_PASSWORD", "youshallnotpass")
lava_secure_env = os.getenv("LAVALINK_SECURE", "false").lower() == "true"

# settings panel (pls no touch)
# oke -kam
misoyan_settings = {
    "all_features": True,           # "nah, i'm going offline for a bit"
    "vc_joining": True,             # "cant join vc im busy"
    "vc_leaving": True,             # yeah i can hold the vc for a bit
    "status_changes": True,         # maybe i wont make a note rn...
    "status_change_delay": False,   # "wait i should do this... NO WAIT THIS IS-"
    "fih_replies": True,            # fih :3
    "need_reconnection": False,     # "i dont need to connect rn, im alr connected :sob:"
    "is_connecting": False,         # "yo im alr connecting"
    "blacklist": set()              # "i hate you, dont talk to me >:("
}

# asyncio lock to prevent the loop and events from connecting at the same time
vc_connection_lock = asyncio.Lock()

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

async def connect_external_audio_node():
    """establishes a persistent socket tunnel to the public web server cluster"""
    await bot.wait_until_ready()

    is_secure = lava_secure_env or lava_port == "443"
    protocol = "https" if is_secure else "http"
    
    nodes = [
        wavelink.Node(
            identifier="misoyan",
            uri=f"{protocol}://{lava_host}:{lava_port}",
            password=lava_pass,
        )
    ]
    
    try:
        await wavelink.Pool.connect(nodes=nodes, client=bot)
    except Exception as e:
        print(f"[!] wait my mic broke: {e}")

@bot.event
async def on_wavelink_node_ready(payload: wavelink.NodeReadyEventPayload):
    print("\n[+] yay my mic works and im connected")

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

    try:
        player: wavelink.Player = wavelink.Pool.get_node().get_player(home_channel.guild.id)
    except Exception:
        player = None

    is_disconnected = not player or not player.connected

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

                await home_channel.connect(cls=wavelink.Player)
                print("im back :3")
                misoyan_settings["need_reconnection"] = False
                
            except Exception as e:
                print(f"so uhh, my wifi broke: {e}")
                # if it throws a closing transport error, force lower the flag so it backs off completely
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
        
    bot.loop.create_task(connect_external_audio_node())

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if member.id != bot.user.id:
        return

    if after.channel is None or after.channel.id != target_voice_channel_id:
        print("wait im not in my vc anymore give me a sec")
        
        if misoyan_settings["all_features"] and misoyan_settings["vc_joining"]:
            # only trigger if we aren't already locking the engine state
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

@bot.event
async def on_wavelink_track_end(payload: wavelink.TrackEndEventPayload):
    """automatically plays the next song in line when the current one finishes"""
    player: wavelink.Player = payload.player
    
    # if the queue isn't empty, pull the next track and play it
    if not player.queue.is_empty:
        next_track = player.queue.get()
        try:
            await player.play(next_track)
            print(f"[queue] automatically transitioning to: {next_track.title}")
        except Exception as e:
            print(f"[!] auto-transition failed: {e}")
    else:
        print("[queue] queue is now empty, going silent.")

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
            await user_channel.connect(cls=wavelink.Player)
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
    
    try:
        player: wavelink.Player = wavelink.Pool.get_node().get_player(interaction.guild.id)
        if player and player.connected:
            async with vc_connection_lock:
                misoyan_settings["need_reconnection"] = False
                await player.disconnect()
                await interaction.response.send_message("i am free!! (yay :3)", ephemeral=True)
        else:
            await interaction.response.send_message("you want me to leave...? im not connected to a vc", ephemeral=True)
    except Exception:
        await interaction.response.send_message("i think my speakers malfunctioned", ephemeral=True)

class NowPlayingView(ui.LayoutView):
    def __init__(self, track, user, extra: str = ""):
        super().__init__()

        user_handle = f"@{user.name}"

        # pull custom file metadata safely from track extras if they exist
        track_extras = getattr(track, "extras", {}) or {}
        is_file = track_extras.get("is_file", False)
        has_cover = track_extras.get("has_cover", False)
        # fallback directly to track.title or a generic string instead of checking local scopes
        filename = track_extras.get("filename", track.title or "attachment")

        # 1. get the track cover
        if is_file and has_cover:
            track_cover_url = "attachment://cover.png"
        elif hasattr(track, 'artwork') and track.artwork:
            track_cover_url = track.artwork
        else:
            track_cover_url = "https://cdn.discordapp.com/attachments/1454299112181600299/1520232653503201331/-sIJRmHN.jpg?ex=6a40727d&is=6a3f20fd&hm=56a9548e90f38e4f26adc02dfddd5d28542fd0a928eb8578ecc564aac0976882&"

        # 2. get the track length
        if track.length:
            minutes = int((track.length // 1000) // 60)
            seconds = int((track.length // 1000) % 60)
            duration = f"{minutes}:{seconds:02d}"
        else:
            duration = "--:--"

        # 3. make the components
        display_prefix = " (file)" if is_file else extra
        now_playing = ui.TextDisplay(f"-# now playing!{display_prefix} - requested by {user_handle} :3")
        cover_art = ui.MediaGallery(discord.MediaGalleryItem(track_cover_url))

        # 4. dynamically change the text configuration if it's an uploaded file
        if is_file:
            track_title_text = filename
            artist_name = track.author if (track.author and track.author != "Unknown Artist") else "local asset"
        else:
            track_title_text = track.title
            artist_name = track.author or "unknown"

        track_metadata = ui.TextDisplay(f"## {track_title_text}\nArtist: **{artist_name}**\nDuration: {duration}")

        # 5. make the actual container/embed
        container = ui.Container(
            now_playing,
            cover_art,
            track_metadata,
            accent_color=discord.Color.from_str("#e6ba81")
        )

        self.add_item(container)

class QueuePopup(ui.LayoutView):
    def __init__(self, track, user, queue_message, position: int = None):
        super().__init__()

        user_handle = f"@{user.name}"

        # 1. get the track cover
        if hasattr(track, 'artwork') and track.artwork:
            track_cover_url = track.artwork
        else:
            track_cover_url = "https://cdn.discordapp.com/attachments/1454299112181600299/1520232653503201331/-sIJRmHN.jpg?ex=6a40727d&is=6a3f20fd&hm=56a9548e90f38e4f26adc02dfddd5d28542fd0a928eb8578ecc564aac0976882&" # a cool sky picture placeholder

        # 2. get the track length
        if track.length:
            minutes = int((track.length // 1000) // 60)
            seconds = int((track.length // 1000) % 60)
            duration = f"{minutes}:{seconds:02d}"
        else:
            duration = "--:--"

        # 3. artist and bottom text and queue position
        index = ""
        if position:
            index = f"Position: #{position}"
        artist_name = track.author or "unknown"
        text_metadata = f"-# requested by {user_handle} :3\n{queue_message}\n# {track.title}\nArtist: **{artist_name}**\nDuration: {duration}\n{index}"

        # 4. make the view and container
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
        node = wavelink.Pool.get_node()
        player: wavelink.Player = node.get_player(interaction.guild.id)

        if not player or not player.connected:
            async with vc_connection_lock:
                misoyan_settings["is_connecting"] = True
                print(f"[/play] connecting to vc: {user_channel.name}")
                player = await user_channel.connect(cls=wavelink.Player)
                global target_voice_channel_id
                target_voice_channel_id = user_channel.id
                misoyan_settings["need_reconnection"] = False
                await asyncio.sleep(1.5)

        cleaned_search = search
        for automated_prefix in ["ytsearch:", "ytmsearch:", "scsearch:", "youtube_music:"]:
            if cleaned_search.lower().startswith(automated_prefix):
                cleaned_search = cleaned_search[len(automated_prefix):].strip()

        print(f"wait, im searching for '{cleaned_search}' rn gimme a sec")
        search_results = await wavelink.Playable.search(cleaned_search)
        
        if not search_results:
            await interaction.followup.send(f"so... there's no song named *{search}*. you sure that exists?")
            return

        if hasattr(search_results, "tracks"):
            tracks = search_results.tracks
        elif isinstance(search_results, list):
            tracks = search_results
        else:
            tracks = [search_results]

        if not tracks:
            await interaction.followup.send(f"so i searched for *{search}*, but it has no songs... D:")
            return

        track = tracks[0]
        
        # if nothing's playing
        if not player.playing:
            await player.play(track)
            embed = NowPlayingView(track, interaction.user) 
            await interaction.followup.send(view=embed)
            return

        # if a song's playing
        if timing == "replace":
            player.queue.put_at(0, track)

            await player.skip()
            
            embed = NowPlayingView(track, interaction.user, " (replaced)")
            await interaction.followup.send(view=embed)
            print(f"[music] replaced active track with '{track.title}'")

        elif timing == "next":
            # put it at position 0 in the queue array layer so it fires next
            player.queue.put_at(0, track)
            embed = QueuePopup(track, interaction.user, "playing next!")
            await interaction.followup.send(view=embed)
            print(f"[music] forced '{track.title}' to play next")

        else: # "queue" (default action profile)
            # standard placement at the end of the line array
            player.queue.put(track)
            pos_number = int(len(player.queue))
            embed = QueuePopup(track, interaction.user, "added to queue!", pos_number)
            await interaction.followup.send(view=embed)
            print(f"[music] appended '{track.title}' to back of queue")

    except Exception as e:
        print(f"[!] my speakers nooo- | {e}")
        await interaction.followup.send(f"so my speakers... uhh: `{e}`", ephemeral=True)
    finally:
        misoyan_settings["is_connecting"] = False

@bot.tree.command(name="skip", description="skip this track if it's bad bleh")
async def skip(interaction: discord.Interaction):
    if not misoyan_settings["all_features"]:
        await interaction.response.send_message("my speakers are off rn (disabled)", ephemeral=True)
        return

    if interaction.user.id in misoyan_settings["blacklist"]:
        await interaction.response.send_message("hey, don't touch that.", ephemeral=True)
        return

    try:
        node = wavelink.Pool.get_node()
        player: wavelink.Player = node.get_player(interaction.guild.id)

        if not player or not player.connected:
            await interaction.response.send_message("i'm not even in a vc to skip anything?", ephemeral=True)
            return

        if not player.playing:
            await interaction.response.send_message("there's nothing playing right now anyway!", ephemeral=True)
            return

        # skip the current song
        await player.skip()
        await interaction.response.send_message("track skipped! next track coming up...")
        print(f"[music] skip command triggered by {interaction.user.name}")

    except Exception as e:
        print(f"[!] failed to skip: {e}")
        await interaction.response.send_message(f"uhh my controls jammed: `{e}`", ephemeral=True)

@bot.tree.command(name="previous", description="play the previous song if you like it :3")
async def previous_track(interaction: discord.Interaction):
    try:
        node = wavelink.Pool.get_node()
        player: wavelink.Player = node.get_player(interaction.guild.id)

        if not player or not player.connected:
            await interaction.response.send_message("i'm not in a vc!", ephemeral=True)
            return

        # history needs to have at least 2 tracks if something is currently playing,
        # because index -1 is the current/just-finished track. 
        if len(player.queue.history) < 2:
            await interaction.response.send_message("hmph, you think i can play nothing?", ephemeral=True)
            return

        # pop the current song out of history so we can access the real historical track behind it
        player.queue.history.pop() # removes the current track record
        real_previous = player.queue.history.pop() # grabs the actual last song
        
        await player.play(real_previous)
        await interaction.response.send_message(f"rewinding back to: **{real_previous.title}**")
        print(f"[music] backtracked to '{real_previous.title}' via {interaction.user.name}")

    except Exception as e:
        await interaction.response.send_message(f"couldn't go back: `{e}`", ephemeral=True)

@bot.tree.command(name="replay", description="restart the current song from the beginning")
async def replay_track(interaction: discord.Interaction):
    try:
        node = wavelink.Pool.get_node()
        player: wavelink.Player = node.get_player(interaction.guild.id)

        if not player or not player.connected or not player.current:
            await interaction.response.send_message("tsk, seriously?")
            return

        # seek back to the absolute beginning (0 milliseconds)
        await player.seek(0)
        await interaction.response.send_message(f"replaying **{player.current.title}**")
        print(f"[music] replayed current track via {interaction.user.name}")

    except Exception as e:
        await interaction.response.send_message(f"couldn't replay: `{e}`", ephemeral=True)

class SongQueue(ui.LayoutView):
    def __init__(self, player, user):
        super().__init__()

        queue_sections = []

        # 1. current track header block
        if player.current:
            current_track = player.current
            
            # handle current track artwork/fallback
            if hasattr(current_track, 'artwork') and current_track.artwork:
                current_cover = current_track.artwork
            else:
                current_cover = "https://cdn.discordapp.com/attachments/1454299112181600299/1520232653503201331/-sIJRmHN.jpg?ex=6a40727d&is=6a3f20fd&hm=56a9548e90f38e4f26adc02dfddd5d28542fd0a928eb8578ecc564aac0976882&"

            # handle current track duration calculation
            if current_track.length:
                curr_min = int((current_track.length // 1000) // 60)
                curr_sec = int((current_track.length // 1000) % 60)
                curr_duration = f"{curr_min}:{curr_sec:02d}"
            else:
                curr_duration = "97:663? (unknown)"

            current_text = f"## {current_track.title}\nArtist: **{current_track.author or 'unknown'}**\nDuration: {curr_duration}\nPosition: playing!"
            
            # append as an individual section with a right-aligned thumbnail accessory
            queue_sections.append(
                ui.Section(
                    ui.TextDisplay(current_text),
                    accessory=ui.Thumbnail(current_cover)
                )
            )

        # 2. queue items loop block (caps at 4 items to keep the card compact)
        for i, track in enumerate(player.queue):
            if i >= 4:
                break
                
            position_text = "up next!" if i == 0 else f"#{i + 1}"
            
            # handle upcoming track artwork/fallback (using a 240x240 grey placeholder box if missing)
            if hasattr(track, 'artwork') and track.artwork:
                track_cover = track.artwork
            else:
                track_cover = "https://placehold.co/240x240/eaeaea/969696.png?text=240+x+240"

            # handle upcoming track duration calculation
            if track.length:
                t_min = int((track.length // 1000) // 60)
                t_sec = int((track.length // 1000) % 60)
                track_duration = f"{t_min}:{t_sec:02d}"
            else:
                track_duration = "97:663? (unknown)"

            track_text = f"## {track.title}\nArtist: **{track.author or 'unknown'}**\nDuration: {track_duration}\nPosition: {position_text}"
            
            # wrap each distinct track index into its own section layout block
            queue_sections.append(
                ui.Section(
                    ui.TextDisplay(track_text),
                    accessory=ui.Thumbnail(track_cover)
                )
            )

        # 3. assemble everything inside the dark master container
        container = ui.Container(
            *queue_sections,
            accent_color=discord.Color.from_str("#2C2C2C")
        )

        # 4. register it directly via the LayoutView framework pipeline
        self.add_item(container)

@bot.tree.command(name="queue", description="see what songs are lined up next")
async def view_queue(interaction: discord.Interaction):
    node = wavelink.Pool.get_node()
    player: wavelink.Player = node.get_player(interaction.guild.id)

    if not player or (not player.current and len(player.queue) == 0):
        await interaction.response.send_message("the queue is completely empty!", ephemeral=True)
        return

    # initialize the proper View class instance
    view_embed = SongQueue(player, interaction.user)
    
    # pass the view instance directly here!
    await interaction.response.send_message(view=view_embed)

class FilePlayingView(ui.LayoutView):
    def __init__(self, track, user: discord.User, attachment: discord.Attachment, has_cover: bool = False):
        super().__init__()

        user_handle = f"@{user.name}"

        # 1. duration evaluation block
        if track.length and track.length > 0:
            minutes = int((track.length // 1000) // 60)
            seconds = int((track.length // 1000) % 60)
            duration_text = f"{minutes}:{seconds:02d}"
        else:
            duration_text = "93:663? wait what-"

        # 2. top layout section details
        top_text = f"-# now playing! (file) - requested by {user_handle} :3\n## {attachment.filename}\nduration: {duration_text}"
        
        # if the command attached a cover image file to the payload, display it
        if has_cover:
            display_thumbnail = "attachment://cover.png"
        elif hasattr(track, 'artwork') and track.artwork:
            display_thumbnail = track.artwork
        else:
            display_thumbnail = user.display_avatar.url

        top_section = ui.Section(
            ui.TextDisplay(top_text),
            accessory=ui.Thumbnail(display_thumbnail)
        )

        # 3. conditional tracking with a native separator line
        has_title = track.title and not track.title.startswith("http") and track.title != attachment.filename
        has_author = track.author and track.author != "Unknown Artist" and track.author != ""

        # compile our list of component pieces dynamically
        layout_components = [top_section]

        if has_title or has_author:
            meta_title = track.title if has_title else "unknown title"
            meta_artist = track.author if has_author else "unknown artist"
            bottom_text = f"## {meta_title}\nartist: **{meta_artist}**"
            
            # append the layout rule/divider first, then stack the metadata section
            layout_components.append(ui.Separator()) 
            layout_components.append(ui.TextDisplay(bottom_text))

        # 4. drop the array into the single cozy master container block
        container = ui.Container(
            *layout_components,
            accent_color=discord.Color.from_str("#F9C788")
        )

        self.add_item(container)

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

    # validate that it's actually a readable audio format
    valid_extensions = [".mp3", ".wav", ".ogg", ".flac", ".m4a"]
    if not any(attachment.filename.lower().endswith(ext) for ext in valid_extensions):
        await interaction.response.send_message("you sure this is an audio file? doesnt look like it", ephemeral=True)
        return

    user_channel = interaction.user.voice.channel
    await interaction.response.defer()

    try:
        node = wavelink.Pool.get_node()
        player: wavelink.Player = node.get_player(interaction.guild.id)

        if not player or not player.connected:
            misoyan_settings["is_connecting"] = True  # lock sentinel out during manual file upload plays
            print(f"[play-file] connecting to vc: {user_channel.name}")
            player = await user_channel.connect(cls=wavelink.Player)
            global target_voice_channel_id
            target_voice_channel_id = user_channel.id
            misoyan_settings["need_reconnection"] = False
            await asyncio.sleep(1.5)

        # fetch playable node data from attachment url
        tracks = await wavelink.Playable.search(attachment.url)
        
        if not tracks:
            await interaction.followup.send("so my speakers couldnt play that... you sure its a real audio file?")
            return

        track = tracks[0]
        
        # --- metadata extraction block ---
        cover_io_data = None  # switch to storing raw stream bytes first!
        if attachment.filename.lower().endswith(".mp3"):
            try:
                file_bytes = await attachment.read()
                audio_stream = io.BytesIO(file_bytes)
                audio = MP3(audio_stream, ID3=ID3)
                
                for key in audio.tags.keys():
                    if key.startswith('APIC'):
                        apic_frame = audio.tags[key]
                        img_io = io.BytesIO(apic_frame.data)
                        img_io.seek(0)
                        cover_io_data = img_io  # assign the data stream here
                        break
            except Exception as metadata_error:
                print(f"[!] couldn't rip metadata tags from track: {metadata_error}")

        # assemble the discord file out here where ruff can see it being checked!
        cover_file = discord.File(cover_io_data, filename="cover.png") if cover_io_data else None
        
        # 💡 NEW: assign custom file variables straight to track extras so NowPlayingView is smart enough to find them later!
        track.extras = {
            "is_file": True,
            "filename": attachment.filename,
            "has_cover": bool(cover_file)
        }
        # ----------------------------------

        # branch 1: if absolutely nothing is currently playing on the node
        if not player.playing:
            await player.play(track)
            
            # brief millisecond breath to populate player states before displaying card
            await asyncio.sleep(0.5)
            
            view_embed = FilePlayingView(track, interaction.user, attachment, has_cover=bool(cover_file)) 
            
            if cover_file:
                await interaction.followup.send(view=view_embed, file=cover_file)
            else:
                await interaction.followup.send(view=view_embed)
            return

        # branch 2: if a song is playing, respect your timing choices
        if timing == "replace":
            # 1. append the fresh file track directly to the front of the queue
            player.queue.put_at_front(track)
            
            # 2. force an immediate skip task to kill the active stream smoothly
            await player.skip(force=True)
            
            # wait briefly for the skipped stream to cycle out and bind metadata
            await asyncio.sleep(0.5)
            
            view_embed = FilePlayingView(track, interaction.user, attachment, has_cover=bool(cover_file))
            
            if cover_file:
                await interaction.followup.send(view=view_embed, file=cover_file)
            else:
                await interaction.followup.send(view=view_embed)
            print(f"[music - play-file] replaced active track with file: '{attachment.filename}'")

        elif timing == "next":
            # slide it into position 0 in the track list array so it hits the player next
            player.queue.put_at(0, track)
            embed = QueuePopup(track, interaction.user, "playing next (file)!")
            await interaction.followup.send(view=embed)
            print(f"[music - play-file] forced file '{attachment.filename}' to play next")

        else: # "queue" (default)
            # append straight to the end of the line container
            player.queue.put(track)
            pos_number = int(len(player.queue))
            embed = QueuePopup(track, interaction.user, "added file to queue!", pos_number)
            await interaction.followup.send(view=embed)
            print(f"[music - play-file] appended file '{attachment.filename}' to back of queue")

    except Exception as e:
        print(f"[!] so my speakers broke...: {e}")
        await interaction.followup.send(f"yeah my speaker broken lmaoo: `{e}`", ephemeral=True)
    finally:
        misoyan_settings["is_connecting"] = False  # release lock safely

@bot.tree.command(name="status", description="check out my internal self :D")
async def systemstatus(interaction: discord.Interaction):
    total_guilds = len(bot.guilds)
    latency = round(bot.latency * 1000)
    
    try:
        current_vc_connections = 1 if wavelink.Pool.get_node().get_player(interaction.guild.id) else 0
    except Exception:
        current_vc_connections = 0
        
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
    # check if user is blasie OR the guild owner OR has administrator permissions
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
    await interaction.response.send_message(embed=view.generate_dashboard_embed(), view=view, ephemeral=True)

@bot.tree.command(name="restrict", description="[admin/owner] don't end up in this list.")
@app_commands.describe(target="the specific person you want to modify settings for")
async def restrict_user(interaction: discord.Interaction, target: discord.User):
    is_creator = interaction.user.id == creator_id
    is_server_owner = interaction.guild and interaction.user.id == interaction.guild.owner_id
    is_admin = interaction.guild and interaction.user.guild_permissions.administrator

    if not (is_creator or is_server_owner or is_admin):
        await interaction.response.send_message("shoo, before you get blacklisted", ephemeral=True)
        return
        
    # prevent server owners or admins from accidentally blacklisting you
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
        
    # check if it's actually ran in a regular text channel
    if isinstance(interaction.channel, discord.TextChannel):
        try:
            webhook_avatar_url = "https://cdn.discordapp.com/attachments/1454299112181600299/1520232653503201331/-sIJRmHN.jpg?ex=6a40727d&is=6a3f20fd&hm=56a9548e90f38e4f26adc02dfddd5d28542fd0a928eb8578ecc564aac0976882&"
            avatar_image = None
            
            # get the image
            async with aiohttp.ClientSession() as session:
                async with session.get(webhook_avatar_url) as response:
                    if response.status == 200:
                        avatar_image = await response.read()

            
            # lets create the webhook
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
    node = wavelink.Pool.get_node()
    player: wavelink.Player = node.get_player(interaction.guild.id)
    
    if not player or not player.current:
        await interaction.response.send_message("you seriously wanna see the void? nothing's playing...")
        return

    current_track = player.current
    
    # check if the track uri points to a discord file attachment stream
    is_file_attachment = False
    if current_track.uri and "discordapp.com/attachments/" in current_track.uri:
        is_file_attachment = True

    # pass the check flag straight down into the updated view configuration
    embed = NowPlayingView(current_track, interaction.user, has_cover=is_file_attachment)
    await interaction.response.send_message(view=embed)

class LoopStatusView(ui.LayoutView):
    def __init__(self, mode: str, track, user: discord.User):
        super().__init__()
        
        user_handle = f"@{user.name}"
        
        # determine which image to use for the right-side thumbnail based on your rules
        if mode == "current":
            if track and hasattr(track, 'artwork') and track.artwork:
                thumbnail_url = track.artwork
            else:
                # fallback picture placeholder if the track lacks artwork
                thumbnail_url = "https://cdn.discordapp.com/attachments/1454299112181600299/1520232653503201331/-sIJRmHN.jpg?ex=6a40727d&is=6a3f20fd&hm=56a9548e90f38e4f26adc02dfddd5d28542fd0a928eb8578ecc564aac0976882&"
            
            card_text = f"-# requested by {user_handle}\n### loop: current song\nthe current song will now loop forever :3"
            accent = discord.Color.from_str("#5C9F05") # matching your active playing aesthetic
            
        elif mode == "queue":
            thumbnail_url = user.display_avatar.url
            card_text = f"-# requested by {user_handle}\n### loop: queue\nthe entire queue will now loop :o"
            accent = discord.Color.from_str("#85C2F0")
            
        else: # off
            thumbnail_url = user.display_avatar.url
            card_text = f"-# requested by {user_handle}\n### loop: off\nloop has been turned off :P"
            accent = discord.Color.from_str("#FF0000")

        # assemble the clean card layout matching image_188ed5.png
        container = ui.Container(
            ui.Section(
                ui.TextDisplay(card_text),
                accessory=ui.Thumbnail(thumbnail_url)
            ),
            accent_color=accent
        )
        
        self.add_item(container)

# slash command implementation for your bot.py tree
@bot.tree.command(name="loop", description="change the loop mode for the player")
@app_commands.choices(mode=[
    app_commands.Choice(name="current song", value="current"),
    app_commands.Choice(name="queue", value="queue"),
    app_commands.Choice(name="off", value="off")
])
async def loop_cmd(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    node = wavelink.Pool.get_node()
    player: wavelink.Player = node.get_player(interaction.guild.id)

    if not player:
        await interaction.response.send_message("there's no active player running in this server!", ephemeral=True)
        return

    # using wavelink.QueueMode enums for loops
    if mode.value == "current":
        player.queue.mode = wavelink.QueueMode.loop
    elif mode.value == "queue":
        player.queue.mode = wavelink.QueueMode.loop_all
    else: # off
        player.queue.mode = wavelink.QueueMode.normal

    # build and send the corresponding card layout using layoutview natively
    view_embed = LoopStatusView(mode.value, player.current, interaction.user)
    await interaction.response.send_message(view=view_embed)

# "just make sure we're not getting silenced"
# SONNNNNNNNNNNNNNNNNNNNNN😭😭😭 -kam
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
