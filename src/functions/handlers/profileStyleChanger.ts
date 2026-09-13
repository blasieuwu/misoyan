const STYLE = {
    font_id: 8,
    effect_id: 4,
    colors: [1710618]
};

async function applyDisplayNameStyle(client: any) {
    const guildIds = client.guilds.cache.map((g: any) => g.id);
    if (!guildIds.length) return;

    const body = {
        display_name_font_id: STYLE.font_id,
        display_name_effect_id: STYLE.effect_id,
        display_name_colors: STYLE.colors
    };

    for (const guildId of guildIds) {
        try {
            const res = await client.rest.patch(`/guilds/${guildId}/members/@me`, { body });
            console.log(`applied display name style for guild ${guildId} | response:`, JSON.stringify(res));
        } catch (error) {
            console.error(`failed to apply display name style for guild ${guildId}`, error);
        }
    }
    console.log('finished applying display name style for all guilds');
}

module.exports = { applyDisplayNameStyle };