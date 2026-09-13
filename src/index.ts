import {
  Client,
  GatewayIntentBits,
  REST,
  Routes,
  SlashCommandBuilder,
  EmbedBuilder,
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  ActivityType,
  PresenceStatusData,
  TextChannel,
  VoiceChannel,
  GuildMember,
  Interaction,
  Message,
  VoiceState,
  User,
  Guild,
  MessageFlags,
  InteractionReplyOptions
} from 'discord.js';
import { Manager } from 'moonlink.js';
import http from 'node:http';

const { fetchUserProfile } = require('./functions/handlers/profileStyleChanger')

// graceful sigterm shutdown for render/containers
process.on('SIGTERM', () => {
  console.log('\x1b[1;33m[!] instance has received a SIGTERM and will now shut down...\x1b[0m');
  process.exit(0);
});

// env variables & settings
const CREATOR_ID = process.env.CREATOR_ID || '0';
const BOT_TOKEN = process.env.DISCORD_BOT_TOKEN || '';
const PORT = process.env.PORT || '8080';

const LAVALINK_HOST = process.env.LAVALINK_HOST || 'lava.link';
const LAVALINK_PORT = parseInt(process.env.LAVALINK_PORT || '80', 10);
const LAVALINK_PASS = process.env.LAVALINK_PASSWORD || 'youshallnotpass';
const LAVALINK_SECURE = ['true', '1', 'yes'].includes((process.env.LAVALINK_SECURE || 'false').toLowerCase());

let targetVoiceChannelId = '123456789012345678';

const vhsSettings = {
  allFeatures: true,
  vcJoining: true,
  vcLeaving: true,
  statusChanges: true,
  statusChangeDelay: false,
  needReconnection: false,
  isConnecting: false,
  blacklist: new Set<string>()
};

// afk user tracking
interface AfkData {
  reason: string;
  originalNick: string | null;
}
const afkUsers = new Map<string, AfkData>();

// client setup
const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildVoiceStates,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent
  ]
});

// moonlink.js v5 manager
const manager = new Manager({
  nodes: [
    {
      host: LAVALINK_HOST,
      port: LAVALINK_PORT,
      password: LAVALINK_PASS,
      secure: LAVALINK_SECURE,
      identifier: 'the-vhs-tape'
    }
  ],
  send: (guildId: string, sPayload: any) => {
    const guild = client.guilds.cache.get(guildId);
    if (guild) guild.shard.send(sPayload);
  }
});

// helper for duration formatting
function formatDuration(ms?: number | null): string {
  if (!ms || ms <= 0) return '--:--';
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

// ==========================================
// COMPONENTS V2 LAYOUT VIEWS (vhs theme)
// ==========================================

// 1. NowPlayingView (Components V2)
function createNowPlayingV2(track: any, user: User, extra: string = '', overrideCover?: string | null): InteractionReplyOptions {
  const userHandle = `@${user.username}`;
  let trackCoverUrl = 'https://placehold.co/240x240/eaeaea/969696.png?text=no+cover';

  if (overrideCover) {
    trackCoverUrl = overrideCover;
  } else if (track.info?.artworkUrl) {
    trackCoverUrl = track.info.artworkUrl;
  }

  const duration = formatDuration(track.info?.length || track.duration);

  let trackTitle = track.info?.title || track.title || 'Unknown Title';
  if ((!trackTitle || trackTitle === 'Unknown Title') && track.info?.uri?.includes('discordapp.com')) {
    trackTitle = track.info.uri.split('/').pop()?.split('?')[0] || trackTitle;
  }

  const author = track.info?.author || track.author;
  const artistName = author && author !== 'Unknown Artist' ? author : 'local asset';
  const displayPrefix = track.info?.uri?.includes('discordapp.com') ? ' (file)' : extra;

  const contentText = `- # now playing tape!${displayPrefix} - spooled by ${userHandle} 📼\n## ${trackTitle}\nartist: **${artistName}**\nduration: ${duration}`;

  return {
    flags: MessageFlags.IsComponentsV2 as any,
    components: [
      {
        type: 1, // Container Component
        accent_color: 0x111111,
        components: [
          {
            type: 10, // Text Display Component
            content: contentText
          },
          {
            type: 11, // Media Gallery Component
            items: [{ media: { url: trackCoverUrl } }]
          }
        ]
      }
    ] as any
  };
}

// 2. QueuePopup (Components V2)
function createQueuePopupV2(track: any, user: User, queueMessage: string, position?: number): InteractionReplyOptions {
  const userHandle = `@${user.username}`;
  const trackCoverUrl = track.info?.artworkUrl || track.artworkUrl || 'https://placehold.co/240x240/eaeaea/969696.png?text=no+cover';
  const duration = formatDuration(track.info?.length || track.duration);
  const indexStr = position ? `\nposition: #${position}` : '';
  const artistName = track.info?.author || track.author || 'unknown';
  const trackTitle = track.info?.title || track.title || 'Unknown Title';

  const textMetadata = `- # spooled by ${userHandle}\n${queueMessage}\n# ${trackTitle}\nartist: **${artistName}**\nduration: ${duration}${indexStr}`;

  return {
    flags: MessageFlags.IsComponentsV2 as any,
    components: [
      {
        type: 1, // Container Component
        accent_color: 0x2c2c2c,
        components: [
          {
            type: 9, // Section Component
            components: [
              {
                type: 10, // Text Display Component
                content: textMetadata
              }
            ],
            accessory: {
              type: 11, // Media Gallery Component / Thumbnail Accessory
              items: [{ media: { url: trackCoverUrl } }]
            }
          }
        ]
      }
    ] as any
  };
}

// 3. SongQueue (Components V2)
function createSongQueueV2(player: any, user: User): InteractionReplyOptions {
  const containerComponents: any[] = [];
  let currentCover = 'https://placehold.co/240x240/eaeaea/969696.png?text=no+cover';

  if (player.current) {
    const current = player.current;
    const currDuration = formatDuration(current.info?.length || current.duration);
    const currTitle = current.info?.title || current.title || 'Unknown Title';
    const currAuthor = current.info?.author || current.author || 'unknown';

    if (current.info?.artworkUrl || current.artworkUrl) {
      currentCover = current.info?.artworkUrl || current.artworkUrl;
    }

    const currentText = `## ${currTitle}\nartist: **${currAuthor}**\nduration: ${currDuration}\nposition: playing!`;

    containerComponents.push({
      type: 9, // Section Component
      components: [
        {
          type: 10,
          content: currentText
        }
      ],
      accessory: {
        type: 11,
        items: [{ media: { url: currentCover } }]
      }
    });
  }

  const queueTracks = Array.isArray(player.queue?.tracks)
    ? player.queue.tracks
    : Array.isArray(player.queue)
    ? player.queue
    : [];

  const limit = Math.min(queueTracks.length, 4);

  for (let i = 0; i < limit; i++) {
    const track = queueTracks[i];
    const positionText = i === 0 ? 'up next!' : `#${i + 1}`;
    const trackDuration = formatDuration(track.info?.length || track.duration);
    const trackTitle = track.info?.title || track.title || 'Unknown Title';
    const trackAuthor = track.info?.author || track.author || 'unknown';

    containerComponents.push({
      type: 10, // Text Display Component
      content: `## ${trackTitle}\nartist: **${trackAuthor}**\nduration: ${trackDuration}\nposition: ${positionText}`
    });
  }

  return {
    flags: MessageFlags.IsComponentsV2 as any,
    components: [
      {
        type: 1, // Container Component
        accent_color: 0x111111,
        components: containerComponents
      }
    ] as any
  };
}

// 4. LoopStatusView (Components V2)
function createLoopStatusV2(mode: 'current' | 'queue' | 'off', track: any, user: User): InteractionReplyOptions {
  const userHandle = `@${user.username}`;
  let thumbnailUrl = user.displayAvatarURL();
  let cardText = '';
  let accent = 0x111111;

  if (mode === 'current') {
    thumbnailUrl = track?.info?.artworkUrl || track?.artworkUrl || 'https://placehold.co/240x240/eaeaea/969696.png?text=no+cover';
    cardText = `- # spooled by ${userHandle}\n### tape loop: current track\nlooping current track continuously 📼`;
    accent = 0x333333;
  } else if (mode === 'queue') {
    cardText = `- # spooled by ${userHandle}\n### tape loop: full spool\nlooping entire tape queue 🔄`;
    accent = 0x222222;
  } else {
    cardText = `- # spooled by ${userHandle}\n### tape loop: off\nloop mechanism disengaged ⏹️`;
    accent = 0x111111;
  }

  return {
    flags: MessageFlags.IsComponentsV2 as any,
    components: [
      {
        type: 1, // Container Component
        accent_color: accent,
        components: [
          {
            type: 9, // Section Component
            components: [
              {
                type: 10,
                content: cardText
              }
            ],
            accessory: {
              type: 11,
              items: [{ media: { url: thumbnailUrl } }]
            }
          }
        ]
      }
    ] as any
  };
}

const statusPool: { status: PresenceStatusData; name: string }[] = [
  { status: 'online', name: 'spinning tapes in the vc 📼' },
  { status: 'idle', name: 'waiting for a deck assignment...' },
  { status: 'dnd', name: 'calibrating audio heads...' },
  { status: 'invisible', name: 'rewinding...' },
  { status: 'online', name: 'hi-fi audio mode active' }
];

// keepalive server
function startWebServer() {
  const server = http.createServer((req: http.IncomingMessage, res: http.ServerResponse) => {
    if (!client.isReady()) {
      res.writeHead(503, { 'Content-Type': 'text/plain' });
      res.end('deck offline :c');
      return;
    }
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    res.end('vhs tape deck online 📼');
  });

  server.listen(parseInt(PORT, 10), '0.0.0.0', () => {
    console.log(`\x1b[1m[https] web server has started on port ${PORT}\x1b[0m`);
  });
}

// settings dashboard builder
function generateDashboard() {
  const embed = new EmbedBuilder()
    .setTitle('vhs control panel')
    .setDescription('deck hardware parameters 📼')
    .setColor(0x111111)
    .setThumbnail(client.user?.displayAvatarURL() || null)
    .addFields(
      { name: 'all features: ', value: `state: \`${vhsSettings.allFeatures ? 'on' : 'off'}\``, inline: false },
      { name: 'vc joining', value: `state: \`${vhsSettings.vcJoining ? 'active' : 'disabled'}\``, inline: true },
      { name: 'vc leaving', value: `state: \`${vhsSettings.vcLeaving ? 'active' : 'disabled'}\``, inline: true },
      { name: 'status changes', value: `state: \`${vhsSettings.statusChanges ? 'cycling' : 'frozen'}\``, inline: true },
      { name: 'cycle frequency', value: `state: \`${vhsSettings.statusChangeDelay ? 'fast mode (1m)' : 'normal rate (2.5m)'}\``, inline: true },
      {
        name: 'blacklisted users',
        value: vhsSettings.blacklist.size > 0 ? Array.from(vhsSettings.blacklist).map((id) => `<@${id}>`).join(', ') : 'none',
        inline: false
      }
    );

  const row1 = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder()
      .setCustomId('m_all')
      .setLabel(`all: ${vhsSettings.allFeatures ? 'on' : 'off'}`)
      .setStyle(vhsSettings.allFeatures ? ButtonStyle.Primary : ButtonStyle.Secondary),
    new ButtonBuilder()
      .setCustomId('m_join')
      .setLabel(`vc join: ${vhsSettings.vcJoining ? 'on' : 'off'}`)
      .setStyle(vhsSettings.vcJoining ? ButtonStyle.Primary : ButtonStyle.Secondary)
  );

  const row2 = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder()
      .setCustomId('m_leave')
      .setLabel(`vc leave: ${vhsSettings.vcLeaving ? 'on' : 'off'}`)
      .setStyle(vhsSettings.vcLeaving ? ButtonStyle.Primary : ButtonStyle.Secondary),
    new ButtonBuilder()
      .setCustomId('m_status')
      .setLabel(`statuses: ${vhsSettings.statusChanges ? 'on' : 'off'}`)
      .setStyle(vhsSettings.statusChanges ? ButtonStyle.Primary : ButtonStyle.Secondary)
  );

  const row3 = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder()
      .setCustomId('m_delay')
      .setLabel(`cycle rate: ${vhsSettings.statusChangeDelay ? 'fast (1m)' : 'normal (2.5m)'}`)
      .setStyle(vhsSettings.statusChangeDelay ? ButtonStyle.Primary : ButtonStyle.Secondary)
  );

  return { embeds: [embed], components: [row1, row2, row3] };
}

// status rotation loop
function startStatusLoop() {
  const run = () => {
    if (vhsSettings.allFeatures && vhsSettings.statusChanges && client.user) {
      const target = statusPool[Math.floor(Math.random() * statusPool.length)];
      client.user.setPresence({
        status: target.status,
        activities: [{ name: target.name, type: ActivityType.Custom }]
      });
    }
    const interval = vhsSettings.statusChangeDelay ? 60000 : 150000;
    setTimeout(run, interval);
  };
  run();
}

// voice sentinel loop
setInterval(async () => {
  if (!vhsSettings.allFeatures || !vhsSettings.vcJoining) return;
  if (vhsSettings.isConnecting) return;

  const channel = client.channels.cache.get(targetVoiceChannelId) as VoiceChannel;
  if (!channel || !channel.isVoiceBased()) return;

  const player = manager.players.get(channel.guild.id);
  const isDisconnected = !player || !player.connected;

  if (isDisconnected || vhsSettings.needReconnection) {
    vhsSettings.needReconnection = false;
    vhsSettings.isConnecting = true;
    console.log('\x1b[1;38;2;88;101;242m[discord - vc]\x1b[0m analog connection dropped. reseating deck.');

    try {
      if (player) player.destroy();
      const newPlayer = manager.players.create({
        guildId: channel.guild.id,
        voiceChannelId: channel.id,
        textChannelId: channel.id,
        autoPlay: true
      });
      await newPlayer.connect();
      console.log('\x1b[1;38;2;88;101;242m[discord - vc]\x1b[0m deck connection reestablished');
    } catch (e) {
      console.log(`\x1b[1;38;2;88;101;242m[discord - vc]\x1b[0m \x1b[31merror reseating deck: \x1b[1;4;31m${e}\x1b[0m`);
    } finally {
      vhsSettings.isConnecting = false;
    }
  }
}, 15000);

// event handlers
client.on('ready', async () => {
  console.log(`\x1b[1;38;2;88;101;242m[discord - sign-in]\x1b[0m signed in as \x1b[1m${client.user?.tag}\x1b[0m`);
  console.log('\x1b[1;4;30;42mrunning the-vhs-tape@v2.0.0\x1b[0m')
  startWebServer();
  manager.init(client.user!.id);

  console.log(`\x1b[1;38;2;88;101;242m[discord - sign-in]\x1b[0m starting status rotation.`)
  startStatusLoop();

  // apply the custom name style
  setImmediate(() => {
    fetchUserProfile(client).catch((error: any) => {
      console.error(`Failed to apply display name style. | Error: ${error}`)
    });
  });

  // register slash commands (including the new audio filter option!)
  const commands = [
    new SlashCommandBuilder().setName('afk').setDescription("tell people you're busy").addStringOption((o) => o.setName('reason').setDescription("why you're away")),
    new SlashCommandBuilder().setName('ping').setDescription("check vhs head tracking latency"),
    new SlashCommandBuilder().setName('join').setDescription('summons the vhs tape player'),
    new SlashCommandBuilder().setName('leave').setDescription('ejects the vhs tape player'),
    new SlashCommandBuilder().setName('play').setDescription('spool up a track').addStringOption((o) => o.setName('search').setDescription('the title or link').setRequired(true)).addStringOption((o) => o.setName('timing').setDescription('queue priority').addChoices({ name: 'add to queue (default)', value: 'queue' }, { name: 'play next', value: 'next' }, { name: 'replace current track', value: 'replace' })),
    new SlashCommandBuilder().setName('now-playing').setDescription('see what track is currently playing'),
    new SlashCommandBuilder().setName('playback').setDescription('pause or resume the tape playback'),
    new SlashCommandBuilder().setName('skip').setDescription("fast forward to the next track"),
    new SlashCommandBuilder().setName('previous').setDescription('rewind to the previous track'),
    new SlashCommandBuilder().setName('replay').setDescription('restart the current track from the beginning'),
    new SlashCommandBuilder().setName('queue').setDescription('see what tracks are lined up next'),
    new SlashCommandBuilder().setName('loop').setDescription('change the loop mode for the player').addStringOption((o) => o.setName('mode').setDescription('loop target').setRequired(true).addChoices({ name: 'current song', value: 'current' }, { name: 'queue', value: 'queue' }, { name: 'off', value: 'off' })),
    new SlashCommandBuilder().setName('filter').setDescription('adjust analog tape tracking filters').addStringOption((o) => o.setName('type').setDescription('filter preset').setRequired(true).addChoices({ name: 'vaporwave', value: 'vaporwave' }, { name: 'nightcore', value: 'nightcore' }, { name: 'clear', value: 'clear' })),
    new SlashCommandBuilder().setName('status').setDescription('deck internal diagnostics'),
    new SlashCommandBuilder().setName('timer').setDescription('set a reminder timer').addStringOption((o) => o.setName('duration').setDescription('ex: 1h 30m').setRequired(true)).addStringOption((o) => o.setName('message').setDescription('what to remind you of')),
    new SlashCommandBuilder().setName('suicide').setDescription('[blasie-only] cuts power to the process.'),
    new SlashCommandBuilder().setName('say').setDescription('[admin/owner] broadcast text through the deck').addStringOption((o) => o.setName('message').setDescription('text to send').setRequired(true)),
    new SlashCommandBuilder().setName('settings').setDescription('[admin/owner] configure hardware settings'),
    new SlashCommandBuilder().setName('restrict').setDescription("[admin/owner] block a user from touching the deck").addUserOption((o) => o.setName('target').setDescription('target user').setRequired(true)),
    new SlashCommandBuilder().setName('webhook').setDescription('[blasie-only] create an operational webhook').addStringOption((o) => o.setName('message').setDescription('webhook name')),
  ];

  const rest = new REST().setToken(BOT_TOKEN);
  try {
    await rest.put(Routes.applicationCommands(client.user!.id), { body: commands });
    console.log('\x1b[1;38;2;88;101;242m[discord - commands]\x1b[0m commands synchronized successfully.');
  } catch (e) {
    console.error('failed to sync commands:', e);
  }
});

client.on('raw', (data: any) => {
  manager.packetUpdate(data);
});

manager.on('nodeCreate', (node: any) => {
  console.log(`\x1b[1;32m[vhs] deck '${node.identifier}' is powered on and tracking!\x1b[0m`);
});

client.on('voiceStateUpdate', (oldState: VoiceState, newState: VoiceState) => {
  if (oldState.member?.id !== client.user?.id) return;

  if (oldState.channelId === targetVoiceChannelId && newState.channelId !== targetVoiceChannelId) {
    console.log('\x1b[1;38;2;88;101;242m[discord - vc]\x1b[0m analog connection lost. attempting to reseat tape.');

    if (vhsSettings.allFeatures && vhsSettings.vcJoining && !vhsSettings.isConnecting) {
      vhsSettings.needReconnection = true;
    }
  }
});

client.on('messageCreate', async (message: Message) => {
  if (message.author.bot) return;

  // afk check remains intact
  if (afkUsers.has(message.author.id)) {
    const data = afkUsers.get(message.author.id)!;
    afkUsers.delete(message.author.id);
    try {
      await message.member?.setNickname(data.originalNick);
    } catch {}
    if (message.channel && 'send' in message.channel) {
      await (message.channel as TextChannel).send(`welcome back, ${message.author}. you're no longer afk.`);
      console.log(`\x1b[1;38;2;88;101;242m[discord - messages]\x1b[0m user ${message.author} is no longer afk.`);
    }
  }

  for (const [, user] of message.mentions.users) {
    if (afkUsers.has(user.id)) {
      const data = afkUsers.get(user.id)!;
      if (message.channel && 'send' in message.channel) {
        await (message.channel as TextChannel).send(`hey, ${user.username} is currently afk.\n~> reason: '*${data.reason}*'`);
        console.log(`\x1b[1;38;2;88;101;242m[discord - messages]\x1b[0m afk user ${user.username} was mentioned.`);
      }
    }
  }
});

// slash command handler
client.on('interactionCreate', async (interaction: Interaction) => {
  if (interaction.isButton()) {
    if (!['m_all', 'm_fih', 'm_join', 'm_leave', 'm_status', 'm_delay'].includes(interaction.customId)) return;

    if (interaction.customId === 'm_all') vhsSettings.allFeatures = !vhsSettings.allFeatures;
    if (interaction.customId === 'm_join') vhsSettings.vcJoining = !vhsSettings.vcJoining;
    if (interaction.customId === 'm_leave') vhsSettings.vcLeaving = !vhsSettings.vcLeaving;
    if (interaction.customId === 'm_status') vhsSettings.statusChanges = !vhsSettings.statusChanges;
    if (interaction.customId === 'm_delay') vhsSettings.statusChangeDelay = !vhsSettings.statusChangeDelay;

    await interaction.update(generateDashboard());
    return;
  }

  if (!interaction.isChatInputCommand()) return;

  const { commandName, options, member, guild, user } = interaction;

  if (commandName === 'play') {
    if (!vhsSettings.allFeatures) return interaction.reply({ content: 'deck power is off (disabled).', ephemeral: true });
    if (vhsSettings.blacklist.has(user.id)) return interaction.reply({ content: "hands off the tape deck.", ephemeral: true });

    const voiceChannel = (member as GuildMember)?.voice?.channel;
    if (!voiceChannel) return interaction.reply({ content: 'plug into a voice channel first.', ephemeral: true });

    const query = options.getString('search', true);
    const timing = options.getString('timing') || 'queue';

    await interaction.deferReply();

    let player = manager.players.get(guild!.id);
    if (!player || !player.connected) {
      player = manager.players.create({
        guildId: guild!.id,
        voiceChannelId: voiceChannel.id,
        textChannelId: interaction.channelId,
        autoPlay: true
      });
      await player.connect();
      targetVoiceChannelId = voiceChannel.id;
    }

    const res = await manager.search({ query, source: 'youtube' });
    if (!res || !res.tracks.length) {
      return interaction.followUp({ content: "static. couldn't find anything to track.", ephemeral: true });
    }

    const track = res.tracks[0];

    if (!player.playing && !player.paused) {
      player.queue.add(track);
      player.play();
      console.log(`\x1b[1;38;2;10;15;35m[moonlink.js]\x1b[0m now playing ${player.current?.title}`);
      return interaction.followUp(createNowPlayingV2(track, user));
    }

    if (timing === 'replace') {
      player.queue.add(track);
      player.skip();
      console.log(`\x1b[1;38;2;10;15;35m[moonlink.js]\x1b[0m track replaced, now playing ${player.current?.title}`);
      return interaction.followUp(createNowPlayingV2(track, user, ' (replaced)'));
    } else {
      player.queue.add(track);
      const queueTracks = player.queue?.tracks || player.queue || [];
      const queueMsg = `spooled into queue! (at index #${queueTracks.length})`;
      return interaction.followUp(createQueuePopupV2(track, user, queueMsg, queueTracks.length));
    }
  }

  // new hardware filter logic using moonlink v5 built-ins
  if (commandName === 'filter') {
    const player = manager.players.get(guild!.id);
    if (!player) return interaction.reply({ content: 'deck is empty.', ephemeral: true });

    const filterType = options.getString('type', true);
    
    if (filterType === 'vaporwave') {
      player.filters.setTimescale({ speed: 0.85, pitch: 0.8, rate: 1.0 });
      player.filters.setTremolo({ frequency: 4.0, depth: 0.3 });
    } else if (filterType === 'nightcore') {
      player.filters.setTimescale({ speed: 1.25, pitch: 1.25, rate: 1.0 });
      player.filters.setTremolo(); // clears the tremolo if it was active
    } else {
      player.filters.clear();
    }
    
    player.filters.apply();
    await interaction.reply(`📼 tracking adjusted: **${filterType}** applied.`);
  }

  if (commandName === 'status') {
    const player = manager.players.get(guild!.id);
    const activeVcs = player && player.connected ? 1 : 0;

    const embed = new EmbedBuilder()
      .setTitle("vhs deck internal diagnostics")
      .setColor(0x111111)
      .setThumbnail(client.user?.displayAvatarURL() || null)
      .addFields(
        { name: 'head tracking latency:', value: `\`${client.ws.ping}ms\``, inline: false },
        { name: "connected servers:", value: `\`${client.guilds.cache.size}\``, inline: false },
        { name: "active outputs:", value: `\`${activeVcs}\``, inline: false }
      )
      .setFooter({ text: 'made by [@blasieuwu](https://blasieuwu.neocities.org)' });

    await interaction.reply({ embeds: [embed] });
  }

  if (commandName === 'suicide') {
    if (user.id !== CREATOR_ID) return interaction.reply({ content: "unauthorized.", ephemeral: true });
    await interaction.reply('ejecting tape and cutting power...');
    process.exit(0);
  }

    if (commandName === 'afk') {
    const reason = options.getString('reason') || 'busy :3';
    const guildMember = member as GuildMember;
    const originalNick = guildMember?.nickname || user.username;

    afkUsers.set(user.id, { reason, originalNick });

    try {
      let newNick = `[afk] ${originalNick}`;
      if (newNick.length > 32) newNick = newNick.slice(0, 32);
      await guildMember.setNickname(newNick);
    } catch {}

    await interaction.reply({ content: `ok, you're afk with reason: '*${reason}*'`, ephemeral: true });
  }

  if (commandName === 'ping') {
    await interaction.reply(`i'm not playing ping pong. (\`${client.ws.ping}ms\`)`);
  }

  if (commandName === 'join') {
    if (!vhsSettings.allFeatures || !vhsSettings.vcJoining) {
      return interaction.reply({ content: 'nah, too busy rn (disabled)', ephemeral: true });
    }

    const voiceChannel = (member as GuildMember)?.voice?.channel;
    if (!voiceChannel) {
      return interaction.reply({ content: 'get in a voice channel you dummy!', ephemeral: true });
    }

    targetVoiceChannelId = voiceChannel.id;
    await interaction.deferReply();

    let player = manager.players.get(guild!.id);
    if (!player) {
      player = manager.players.create({
        guildId: guild!.id,
        voiceChannelId: voiceChannel.id,
        textChannelId: interaction.channelId,
        autoPlay: true
      });
    }

    await player.connect();
    vhsSettings.needReconnection = false;
    await interaction.followUp('the vhs player is ready');
  }

  if (commandName === 'leave') {
    if (!vhsSettings.allFeatures || !vhsSettings.vcLeaving) {
      return interaction.reply({ content: 'you are not making me leave lmaooo (disabled)', ephemeral: true });
    }

    const player = manager.players.get(guild!.id);
    if (player && player.connected) {
      player.destroy();
      vhsSettings.needReconnection = false;
      await interaction.reply({ content: 'i am free!! (yay :3)', ephemeral: true });
    } else {
      await interaction.reply({ content: 'you want me to leave...? im not connected to a vc', ephemeral: true });
    }
  }

  if (commandName === 'now-playing') {
    const player = manager.players.get(guild!.id);
    if (!player || !player.current) {
      return interaction.reply({ content: 'nothing is currently playing!', ephemeral: true });
    }
    const v2Payload = createNowPlayingV2(player.current, user);
    return interaction.reply(v2Payload);
  }

  if (commandName === 'playback') {
    const player = manager.players.get(guild!.id);
    if (!player) return interaction.reply({ content: "i'm not even in a vc right now?", ephemeral: true });

    if (!player.paused) {
      await player.pause();
      await interaction.reply("oh, ok i'll hold the music.");
    } else {
      await player.resume();
      await interaction.reply('alr lemme continue playing it');
    }
  }

  if (commandName === 'skip') {
    const player = manager.players.get(guild!.id);
    if (!player || !player.current) return interaction.reply({ content: 'nothing is playing right now!', ephemeral: true });

    await player.skip();
    await interaction.reply('track skipped! next track coming up...');
  }

  if (commandName === 'loop') {
    const player = manager.players.get(guild!.id);
    if (!player) return interaction.reply({ content: "there's no active player running in this server!", ephemeral: true });

    const mode = options.getString('mode', true) as 'current' | 'queue' | 'off';
    if (mode === 'current') player.setLoop('track');
    else if (mode === 'queue') player.setLoop('queue');
    else player.setLoop('off');

    const v2Payload = createLoopStatusV2(mode, player.current, user);
    await interaction.reply(v2Payload);
  }

  if (commandName === 'queue') {
    const player = manager.players.get(guild!.id);
  
    // safely extract the array or fallback to empty array
    const queueTracks = Array.isArray(player?.queue?.tracks)
      ? player.queue.tracks
      : (Array.isArray(player?.queue) ? player.queue : []);

    if (!player || (!player.current && queueTracks.length === 0)) {
      return interaction.reply({ content: 'the queue is completely empty!', ephemeral: true });
    }

    const v2Payload = createSongQueueV2(player, user);
    await interaction.reply(v2Payload as any);
  }

  if (commandName === 'timer') {
    const duration = options.getString('duration', true);
    const msg = options.getString('message');

    let seconds = 0;
    const matches = duration.matchAll(/(\d+)\s*([hmsHMS])/g);
    for (const match of matches) {
      const val = parseInt(match[1], 10);
      const unit = match[2].toLowerCase();
      if (unit === 'h') seconds += val * 3600;
      if (unit === 'm') seconds += val * 60;
      if (unit === 's') seconds += val;
    }

    if (seconds <= 0) return interaction.reply({ content: 'sonion did you not read the format 😭🙏', ephemeral: true });
    if (seconds > 86400) return interaction.reply({ content: 'no im not doing this for 24+ hours', ephemeral: true });

    let confirm = `ok, your timer's set for **${duration}**!`;
    if (msg) confirm += `\n~> **note:** ${msg}`;
    await interaction.reply(confirm);

    setTimeout(async () => {
      let reminder = `ring ring banana phone (${user})`;
      if (msg) reminder += `\n~> **reminder:** ${msg}`;
      await interaction.followUp(reminder);
    }, seconds * 1000);
  }

  if (commandName === 'say') {
    const isCreator = user.id === CREATOR_ID;
    const isOwner = guild && user.id === guild.ownerId;
    const isAdmin = (member as GuildMember)?.permissions.has('Administrator');

    if (!isCreator && !isOwner && !isAdmin) {
      return interaction.reply({ content: "you're not blasie or an admin here, get away", ephemeral: true });
    }

    const message = options.getString('message', true);
    await interaction.reply({ content: 'im in your walls :)', ephemeral: true });
    if (interaction.channel && 'send' in interaction.channel) {
      await (interaction.channel as TextChannel).send(message);
    }
  }

  if (commandName === 'settings') {
    const isCreator = user.id === CREATOR_ID;
    const isOwner = guild && user.id === guild.ownerId;
    const isAdmin = (member as GuildMember)?.permissions.has('Administrator');

    if (!isCreator && !isOwner && !isAdmin) {
      return interaction.reply({ content: 'yeah no, shoo.', ephemeral: true });
    }

    await interaction.reply({ ...generateDashboard(), ephemeral: true });
  }

  if (commandName === 'restrict') {
    const isCreator = user.id === CREATOR_ID;
    const isOwner = guild && user.id === guild.ownerId;
    const isAdmin = (member as GuildMember)?.permissions.has('Administrator');

    if (!isCreator && !isOwner && !isAdmin) {
      return interaction.reply({ content: "you're not blasie or an admin here, get away", ephemeral: true });
    }

    const target = options.getUser('target', true);
    if (target.id === CREATOR_ID) {
      return interaction.reply({ content: "you can't lock up my creator, dummy!!", ephemeral: true });
    }

    if (vhsSettings.blacklist.has(target.id)) {
      vhsSettings.blacklist.delete(target.id);
      await interaction.reply({ content: `yay! ${target} is now allowed to speak to me again :3`, ephemeral: true });
    } else {
      vhsSettings.blacklist.add(target.id);
      await interaction.reply({ content: `get lost! ${target} has been blacklisted.`, ephemeral: true });
    }
  }

  if (commandName === 'webhook') {
    if (user.id !== CREATOR_ID) return interaction.reply({ content: "you're not blasie, get away", ephemeral: true });

    const name = options.getString('message') || 'a webhook';
    if (interaction.channel && 'createWebhook' in interaction.channel) {
      try {
        const webhook = await (interaction.channel as TextChannel).createWebhook({
          name,
          reason: 'created by blasie using the-vhs-tape'
        });
        await interaction.reply({ content: `done! your webhook url is: ||${webhook.url}|| | name: ${webhook.name}`, ephemeral: true });
      } catch {
        await interaction.reply({ content: "i don't have permission or it failed :p", ephemeral: true });
      }
    }
  }
});

if (process.env.NODE_ENV === 'test') {
  console.log('ci syntax test passed, skipping login!');
  process.exit(0);
}

client.login(BOT_TOKEN);