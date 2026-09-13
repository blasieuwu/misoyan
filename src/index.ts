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
  VoiceState
} from 'discord.js';
import { Manager } from 'moonlink.js';
import http from 'node:http';

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

const misoyanSettings = {
  allFeatures: true,
  vcJoining: true,
  vcLeaving: true,
  statusChanges: true,
  statusChangeDelay: false,
  fihReplies: false,
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
      identifier: 'misoyan'
    }
  ],
  send: (guildId: string, sPayload: any) => {
    const guild = client.guilds.cache.get(guildId);
    if (guild) guild.shard.send(sPayload);
  }
});

// reply list
const replyList = [
  'fih fih fih',
  'who pinged',
  'you like fih?',
  'did someone call my name?',
  'fih :3',
  'please do the fih',
  'i loveeee fih',
  'hello :d',
  'the fih gods are watching us',
  'https://tenor.com/view/spinning-fish-gif-11746948154213447163',
  'https://tenor.com/view/upside-down-spinning-fish-long-sticker-gif-14191013706827067344',
  'https://tenor.com/view/pog-gif-14149886028736974766',
  'https://tenor.com/view/silly-cat-doodle-fish-nibble-cat-eating-fish-gif-15126373179558858541',
  'https://tenor.com/view/screaming-fish-fish-fish-finger-gif-9883040399517041611',
  'https://tenor.com/view/kiracord-fish-gif-22855500',
  'https://tenor.com/view/cat-cat-pufferfish-pufferfish-cat-fish-catfish-gif-9997139051265883971',
  'praise fih',
  'killer fish from san diego',
  'fih party',
  'spinning fish',
  'me and fih :3',
  '🐟',
  'im in your walls :d'
];

// status pool
const statusPool: { status: PresenceStatusData; name: string }[] = [
  { status: 'online', name: 'hanging out in the vc :3' },
  { status: 'idle', name: 'waiting for someone to join :c' },
  { status: 'dnd', name: 'learning new stuff...' },
  { status: 'invisible', name: 'lurking...' },
  { status: 'online', name: 'yapping in yappanese bleh' },
  { status: 'idle', name: 'waiting for someone to call my name :c' },
  { status: 'dnd', name: 'please do the fih' },
  { status: 'invisible', name: 'sleeping... zzz' },
  { status: 'dnd', name: 'planning next stream' },
  { status: 'idle', name: 'bored as hell' },
  { status: 'online', name: 'hanging out on stream' },
  { status: 'dnd', name: "i'm lurking in your walls :3" }
];

// keepalive server
function startWebServer() {
  const server = http.createServer((req: http.IncomingMessage, res: http.ServerResponse) => {
    if (!client.isReady()) {
      res.writeHead(503, { 'Content-Type': 'text/plain' });
      res.end('bot is offline or unready :c');
      return;
    }
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    res.end('fih fih fih :3');
  });

  server.listen(parseInt(PORT, 10), '0.0.0.0', () => {
    console.log(`\x1b[1m[https] web server has started on port ${PORT}\x1b[0m`);
  });
}

// settings dashboard builder
function generateDashboard() {
  const embed = new EmbedBuilder()
    .setTitle('the command block')
    .setDescription('my internal organs :3')
    .setColor(0xffcc80)
    .setThumbnail(client.user?.displayAvatarURL() || null)
    .addFields(
      { name: 'all features: ', value: `state: \`${misoyanSettings.allFeatures ? 'on' : 'off'}\``, inline: false },
      { name: 'vc joining', value: `state: \`${misoyanSettings.vcJoining ? 'active' : 'disabled'}\``, inline: true },
      { name: 'vc leaving', value: `state: \`${misoyanSettings.vcLeaving ? 'active' : 'disabled'}\``, inline: true },
      { name: 'voicelines', value: `state: \`${misoyanSettings.fihReplies ? 'listening' : 'muted'}\``, inline: true },
      { name: 'status changes', value: `state: \`${misoyanSettings.statusChanges ? 'cycling' : 'frozen'}\``, inline: true },
      { name: 'cycle frequency', value: `state: \`${misoyanSettings.statusChangeDelay ? 'fast layout mode (1m)' : 'normal engine rate (2.5m)'}\``, inline: true },
      {
        name: 'blacklisted people',
        value: misoyanSettings.blacklist.size > 0 ? Array.from(misoyanSettings.blacklist).map((id) => `<@${id}>`).join(', ') : 'none',
        inline: false
      }
    );

  const row1 = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder()
      .setCustomId('m_all')
      .setLabel(`all: ${misoyanSettings.allFeatures ? 'on' : 'off'}`)
      .setStyle(misoyanSettings.allFeatures ? ButtonStyle.Primary : ButtonStyle.Secondary),
    new ButtonBuilder()
      .setCustomId('m_fih')
      .setLabel(`voicelines: ${misoyanSettings.fihReplies ? 'on' : 'off'}`)
      .setStyle(misoyanSettings.fihReplies ? ButtonStyle.Primary : ButtonStyle.Secondary)
  );

  const row2 = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder()
      .setCustomId('m_join')
      .setLabel(`vc join: ${misoyanSettings.vcJoining ? 'on' : 'off'}`)
      .setStyle(misoyanSettings.vcJoining ? ButtonStyle.Primary : ButtonStyle.Secondary),
    new ButtonBuilder()
      .setCustomId('m_leave')
      .setLabel(`vc leave: ${misoyanSettings.vcLeaving ? 'on' : 'off'}`)
      .setStyle(misoyanSettings.vcLeaving ? ButtonStyle.Primary : ButtonStyle.Secondary)
  );

  const row3 = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder()
      .setCustomId('m_status')
      .setLabel(`statuses: ${misoyanSettings.statusChanges ? 'on' : 'off'}`)
      .setStyle(misoyanSettings.statusChanges ? ButtonStyle.Primary : ButtonStyle.Secondary),
    new ButtonBuilder()
      .setCustomId('m_delay')
      .setLabel(`cycle rate: ${misoyanSettings.statusChangeDelay ? 'fast (1m)' : 'normal (2.5m)'}`)
      .setStyle(misoyanSettings.statusChangeDelay ? ButtonStyle.Primary : ButtonStyle.Secondary)
  );

  return { embeds: [embed], components: [row1, row2, row3] };
}

// status rotation loop
function startStatusLoop() {
  const run = () => {
    if (misoyanSettings.allFeatures && misoyanSettings.statusChanges && client.user) {
      const target = statusPool[Math.floor(Math.random() * statusPool.length)];
      client.user.setPresence({
        status: target.status,
        activities: [{ name: target.name, type: ActivityType.Custom }]
      });
    }
    const interval = misoyanSettings.statusChangeDelay ? 60000 : 150000;
    setTimeout(run, interval);
  };
  run();
}

// voice sentinel loop
setInterval(async () => {
  if (!misoyanSettings.allFeatures || !misoyanSettings.vcJoining) return;
  if (misoyanSettings.isConnecting) return;

  const channel = client.channels.cache.get(targetVoiceChannelId) as VoiceChannel;
  if (!channel || !channel.isVoiceBased()) return;

  const player = manager.players.get(channel.guild.id);
  const isDisconnected = !player || !player.connected;

  if (isDisconnected || misoyanSettings.needReconnection) {
    misoyanSettings.needReconnection = false;
    misoyanSettings.isConnecting = true;
    console.log('\x1b[1;38;2;88;101;242m[discord - vc]\x1b[0m a disconnection has occured & will attempt to reconnect.');

    try {
      if (player) player.destroy();
      const newPlayer = manager.players.create({
        guildId: channel.guild.id,
        voiceChannelId: channel.id,
        textChannelId: channel.id,
        autoPlay: true
      });
      await newPlayer.connect();
      console.log('\x1b[1;38;2;88;101;242m[discord - vc]\x1b[0m connection reestablished');
    } catch (e) {
      console.log(`\x1b[1;38;2;88;101;242m[discord - vc]\x1b[0m \x1b[31man error occured while reconnecting: \x1b[1;4;31m${e}\x1b[0m`);
    } finally {
      misoyanSettings.isConnecting = false;
    }
  }
}, 15000);

// event handlers
client.on('ready', async () => {
  console.log(`\x1b[1;38;2;88;101;242m[discord - sign-in]\x1b[0m signing in as \x1b[1m${client.user?.tag}\x1b[0m`);
  startWebServer();
  manager.init(client.user!.id);
  startStatusLoop();

  // register slash commands
  const commands = [
    new SlashCommandBuilder().setName('afk').setDescription("tell people you're busy").addStringOption((o) => o.setName('reason').setDescription("why you're away")),
    new SlashCommandBuilder().setName('ping').setDescription("check misoyan's reflexes"),
    new SlashCommandBuilder().setName('join').setDescription('i wanna join the vc :3'),
    new SlashCommandBuilder().setName('leave').setDescription('pls let me go :c'),
    new SlashCommandBuilder().setName('play').setDescription('use my speakers :3').addStringOption((o) => o.setName('search').setDescription('the title or link').setRequired(true)).addStringOption((o) => o.setName('timing').setDescription('queue priority').addChoices({ name: 'add to queue (default)', value: 'queue' }, { name: 'play next', value: 'next' }, { name: 'replace current track', value: 'replace' })),
    new SlashCommandBuilder().setName('now-playing').setDescription('see what track is currently playing'),
    new SlashCommandBuilder().setName('playback').setDescription('pause or unpause the current music playback'),
    new SlashCommandBuilder().setName('skip').setDescription("skip this track if it's bad bleh"),
    new SlashCommandBuilder().setName('previous').setDescription('play the previous song if you like it :3'),
    new SlashCommandBuilder().setName('replay').setDescription('restart the current song from the beginning'),
    new SlashCommandBuilder().setName('queue').setDescription('see what songs are lined up next'),
    new SlashCommandBuilder().setName('loop').setDescription('change the loop mode for the player').addStringOption((o) => o.setName('mode').setDescription('loop target').setRequired(true).addChoices({ name: 'current song', value: 'current' }, { name: 'queue', value: 'queue' }, { name: 'off', value: 'off' })),
    new SlashCommandBuilder().setName('status').setDescription('check out my internal self :d'),
    new SlashCommandBuilder().setName('timer').setDescription('set a timer').addStringOption((o) => o.setName('duration').setDescription('ex: 1h 30m').setRequired(true)).addStringOption((o) => o.setName('message').setDescription('what to remind you of')),
    new SlashCommandBuilder().setName('suicide').setDescription('[blasie-only] completely kills misoyan.'),
    new SlashCommandBuilder().setName('say').setDescription('[admin/owner] make misoyan speak :d').addStringOption((o) => o.setName('message').setDescription('text to send').setRequired(true)),
    new SlashCommandBuilder().setName('settings').setDescription('[admin/owner] change my internal organs :3'),
    new SlashCommandBuilder().setName('restrict').setDescription("[admin/owner] don't end up in this list.").addUserOption((o) => o.setName('target').setDescription('target user').setRequired(true)),
    new SlashCommandBuilder().setName('webhook').setDescription('[blasie-only] create a new webhook :o').addStringOption((o) => o.setName('message').setDescription('webhook name'))
  ];

  const rest = new REST().setToken(BOT_TOKEN);
  try {
    await rest.put(Routes.applicationCommands(client.user!.id), { body: commands });
    console.log('\x1b[1;38;2;88;101;242m[discord - commands]\x1b[0m commands were synchronized.');
  } catch (e) {
    console.error('failed to sync commands:', e);
  }
});

client.on('raw', (data: any) => {
  manager.packetUpdate(data);
});

manager.on('nodeCreate', (node: any) => {
  console.log(`\x1b[1;32m[lavalink] node '${node.identifier}' is ready!\x1b[0m`);
});

client.on('voiceStateUpdate', (oldState: VoiceState, newState: VoiceState) => {
  if (oldState.member?.id !== client.user?.id) return;

  if (oldState.channelId === targetVoiceChannelId && newState.channelId !== targetVoiceChannelId) {
    console.log('\x1b[1;38;2;88;101;242m[discord - vc]\x1b[0m a disconnection has occured & will attempt to reconnect.');
    if (misoyanSettings.allFeatures && misoyanSettings.vcJoining && !misoyanSettings.isConnecting) {
      misoyanSettings.needReconnection = true;
    }
  }
});

client.on('messageCreate', async (message: Message) => {
  if (message.author.bot) return;

  // afk check
  if (afkUsers.has(message.author.id)) {
    const data = afkUsers.get(message.author.id)!;
    afkUsers.delete(message.author.id);
    try {
      await message.member?.setNickname(data.originalNick);
    } catch {}
    if (message.channel && 'send' in message.channel) {
      await (message.channel as TextChannel).send(`welcome back, ${message.author}. you're no longer afk.`);
    }
  }

  for (const [, user] of message.mentions.users) {
    if (afkUsers.has(user.id)) {
      const data = afkUsers.get(user.id)!;
      if (message.channel && 'send' in message.channel) {
        await (message.channel as TextChannel).send(`hey, ${user.username}'s afk.\n~> reason: '*${data.reason}*'`);
      }
    }
  }

  if (!misoyanSettings.allFeatures || misoyanSettings.blacklist.has(message.author.id)) return;
  if (!misoyanSettings.fihReplies) return;

  if (message.content.toLowerCase().includes('misoyan') || message.mentions.has(client.user!)) {
    const reply = replyList[Math.floor(Math.random() * replyList.length)];
    await message.reply({ content: reply, allowedMentions: { parse: [] } }).catch(() => {});
  }
});

// slash command handler
client.on('interactionCreate', async (interaction: Interaction) => {
  if (interaction.isButton()) {
    if (!['m_all', 'm_fih', 'm_join', 'm_leave', 'm_status', 'm_delay'].includes(interaction.customId)) return;

    if (interaction.customId === 'm_all') misoyanSettings.allFeatures = !misoyanSettings.allFeatures;
    if (interaction.customId === 'm_fih') misoyanSettings.fihReplies = !misoyanSettings.fihReplies;
    if (interaction.customId === 'm_join') misoyanSettings.vcJoining = !misoyanSettings.vcJoining;
    if (interaction.customId === 'm_leave') misoyanSettings.vcLeaving = !misoyanSettings.vcLeaving;
    if (interaction.customId === 'm_status') misoyanSettings.statusChanges = !misoyanSettings.statusChanges;
    if (interaction.customId === 'm_delay') misoyanSettings.statusChangeDelay = !misoyanSettings.statusChangeDelay;

    await interaction.update(generateDashboard());
    return;
  }

  if (!interaction.isChatInputCommand()) return;

  const { commandName, options, member, guild, user } = interaction;

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
    if (!misoyanSettings.allFeatures || !misoyanSettings.vcJoining) {
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
    misoyanSettings.needReconnection = false;
    await interaction.followUp('im in your vc now :d');
  }

  if (commandName === 'leave') {
    if (!misoyanSettings.allFeatures || !misoyanSettings.vcLeaving) {
      return interaction.reply({ content: 'you are not making me leave lmaooo (disabled)', ephemeral: true });
    }

    const player = manager.players.get(guild!.id);
    if (player && player.connected) {
      player.destroy();
      misoyanSettings.needReconnection = false;
      await interaction.reply({ content: 'i am free!! (yay :3)', ephemeral: true });
    } else {
      await interaction.reply({ content: 'you want me to leave...? im not connected to a vc', ephemeral: true });
    }
  }

  if (commandName === 'play') {
    if (!misoyanSettings.allFeatures) return interaction.reply({ content: 'my speakers are off rn (disabled)', ephemeral: true });
    if (misoyanSettings.blacklist.has(user.id)) return interaction.reply({ content: "hey, don't touch that.", ephemeral: true });

    const voiceChannel = (member as GuildMember)?.voice?.channel;
    if (!voiceChannel) return interaction.reply({ content: 'join a voice channel first, you dummy! i need an audience. :c', ephemeral: true });

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
      return interaction.followUp({ content: "i couldn't find anything with that search query :c", ephemeral: true });
    }

    const track = res.tracks[0];

    if (!player.playing && !player.paused) {
      player.queue.add(track);
      player.play();
      const embed = new EmbedBuilder()
        .setTitle(track.title)
        .setDescription(`artist: **${track.author}**`)
        .setColor(0xe6ba81);
      return interaction.followUp({ content: `-# now playing! - requested by @${user.username} :3`, embeds: [embed] });
    }

    if (timing === 'replace') {
      player.queue.add(track);
      player.skip();
      return interaction.followUp(`now playing **${track.title}** (replaced)`);
    } else {
      player.queue.add(track);
      return interaction.followUp(`added **${track.title}** to queue!`);
    }
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

    const mode = options.getString('mode', true);
    if (mode === 'current') player.setLoop('track');
    else if (mode === 'queue') player.setLoop('queue');
    else player.setLoop('off');

    await interaction.reply(`loop mode updated to: **${mode}**`);
  }

  if (commandName === 'queue') {
    const player = manager.players.get(guild!.id);
    if (!player || (!player.current && player.queue.tracks.length === 0)) {
      return interaction.reply({ content: 'the queue is completely empty!', ephemeral: true });
    }

    const currentText = player.current ? `playing: **${player.current.title}**\n` : '';
    const queueList = player.queue.tracks.slice(0, 5).map((t: any, i: number) => `#${i + 1} - ${t.title}`).join('\n');

    const embed = new EmbedBuilder()
      .setTitle('song queue')
      .setDescription(`${currentText}\n${queueList}`)
      .setColor(0x2c2c2c);

    await interaction.reply({ embeds: [embed] });
  }

  if (commandName === 'status') {
    const player = manager.players.get(guild!.id);
    const activeVcs = player && player.connected ? 1 : 0;

    const embed = new EmbedBuilder()
      .setTitle("misoyan's internal brain :3")
      .setDescription('very simple stuff')
      .setColor(0x2b2d31)
      .setThumbnail(client.user?.displayAvatarURL() || null)
      .addFields(
        { name: 'reflex times: ', value: `\`${client.ws.ping}ms\``, inline: false },
        { name: "servers i'm in: ", value: `\`${client.guilds.cache.size} servers\``, inline: false },
        { name: "vcs i'm in right now: ", value: `\`${activeVcs} active vcs\``, inline: false }
      )
      .setFooter({ text: 'created by blasie :3' });

    await interaction.reply({ embeds: [embed] });
  }

  if (commandName === 'timer') {
    const duration = options.getString('duration', true);
    const msg = options.getString('message');

    // simple time parser
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

  if (commandName === 'suicide') {
    if (user.id !== CREATOR_ID) return interaction.reply({ content: "you're not blasie, get away", ephemeral: true });
    await interaction.reply('ouch d:');
    process.exit(0);
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

    if (misoyanSettings.blacklist.has(target.id)) {
      misoyanSettings.blacklist.delete(target.id);
      await interaction.reply({ content: `yay! ${target} is now allowed to speak to me again :3`, ephemeral: true });
    } else {
      misoyanSettings.blacklist.add(target.id);
      await interaction.reply({ content: `get lost! ${target} has been blacklisted.`, ephemeral: true });
    }
  }

  if (commandName === 'webhook') {
    if (user.id !== CREATOR_ID) return interaction.reply({ content: "you're not blasie, get away", ephemeral: true });

    const name = options.getString('message') || 'a webhook - misoyan';
    if (interaction.channel && 'createWebhook' in interaction.channel) {
      try {
        const webhook = await (interaction.channel as TextChannel).createWebhook({
          name,
          reason: 'created by blasie using misoyan :o'
        });
        await interaction.reply({ content: `done! your webhook url is: ||${webhook.url}|| | name: ${webhook.name}`, ephemeral: true });
      } catch {
        await interaction.reply({ content: "i don't have permission or it failed :p", ephemeral: true });
      }
    }
  }
});

// skip actual login during ci syntax testing
if (process.env.NODE_ENV === 'test') {
  console.log('ci syntax test passed, skipping login!');
  process.exit(0);
}

client.login(BOT_TOKEN);