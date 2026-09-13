const STYLE = {
    font_id: 8,
    effect_id: 4,
    colors: [2105376]
}

async function applyDisplayNameStyle(client) {
    const guilds = client.guilds.cache.map(g => g.id);
    if (!guilds.length) return;

    const body = {
        display_name_font: STYLE.font_id,
        display_name_effect: STYLE.effect_id,
        display_name_colors: STYLE.colors
    }

    for (const guild of guilds) {
        try {
            await client.rest.patch(`/guilds/${guild}/members/@me`, { body });
            console.log(`applied display name style for guild ${guild}`)
        } catch (error) {
            console.error(`failed to apply display name style for guild ${guild} | error: ${error}`);
        }
    }
    console.log('finished applying display name style for all guilds');
}

module.exports = { applyDisplayNameStyle };